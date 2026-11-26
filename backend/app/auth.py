import hashlib
import secrets
from typing import Annotated

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.access import access_for, audit, available_tenants
from app.db import write_transaction
from app.mfa import verify_mfa
from app.models import AuditLog, LoginLimit, LoginSession, PasswordReset, RefreshToken, User, now
from app.platform_access import platform_grants
from app.schemas import ChooseTenant, Identity, LoginInput, ResetInput

router = APIRouter(prefix="/auth", tags=["Autenticación"])
hasher = PasswordHasher()
dummy_hash = hasher.hash(secrets.token_urlsafe(32))
ACCESS = "rf_access"
REFRESH = "rf_refresh"


def get_db(request: Request):
    with Session(request.app.state.engine, expire_on_commit=False) as db:
        yield db


DB = Annotated[Session, Depends(get_db)]


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def unauthorized():
    return HTTPException(401, "Sesión inválida o vencida")


def verify(encoded: str, value: str) -> bool:
    try:
        return hasher.verify(encoded, value)
    except (VerificationError, InvalidHashError):
        return False


def credentials(request: Request, db: Session) -> tuple[LoginSession, User]:
    settings = request.app.state.settings
    try:
        claims = jwt.decode(
            request.cookies.get(ACCESS, ""),
            settings.jwt_secret_key.get_secret_value(),
            algorithms=["HS256"],
            audience="raizfood",
            issuer="raizfood",
            options={"require": ["exp", "iat", "sub", "sid", "ver"]},
        )
    except jwt.InvalidTokenError as error:
        raise unauthorized() from error
    session = db.get(LoginSession, claims["sid"])
    if (
        not session
        or session.revoked
        or session.expires_at <= now()
        or session.user_id != claims["sub"]
        or session.version != claims["ver"]
    ):
        raise unauthorized()
    user = db.get(User, session.user_id)
    if (
        not user
        or not user.active
        or (settings.app_env == "production" and user.platform_admin and not session.mfa_verified)
    ):
        raise unauthorized()
    return session, user


def issue_access(request: Request, response: Response, session: LoginSession):
    settings = request.app.state.settings
    lifetime = min(session.expires_at - now(), settings.access_token_expire_minutes * 60)
    timestamp = now()
    token = jwt.encode(
        {
            "sub": session.user_id,
            "sid": session.id,
            "ver": session.version,
            "iat": timestamp,
            "exp": timestamp + lifetime,
            "aud": "raizfood",
            "iss": "raizfood",
        },
        settings.jwt_secret_key.get_secret_value(),
        algorithm="HS256",
    )
    response.set_cookie(
        ACCESS,
        token,
        httponly=True,
        secure=settings.app_env == "production",
        samesite="lax",
        max_age=lifetime if session.remember else None,
    )


def issue_refresh(request: Request, response: Response, db: Session, session: LoginSession):
    token = secrets.token_urlsafe(32)
    db.add(RefreshToken(digest=digest(token), session_id=session.id))
    response.set_cookie(
        REFRESH,
        token,
        path="/api/auth",
        httponly=True,
        secure=request.app.state.settings.app_env == "production",
        samesite="lax",
        max_age=session.expires_at - now() if session.remember else None,
    )


def identity(db: Session, session: LoginSession, user: User):
    active = access_for(db, user, session.tenant_id)
    return {
        "name": user.name,
        "email": user.email,
        "platform_admin": user.platform_admin,
        "platform_permissions": sorted(platform_grants(db, user)),
        "tenant": active.tenant if active else None,
        "restaurants": available_tenants(db, user),
        "permissions": sorted(active.permissions) if active else [],
    }


def reserve_attempt(db: Session, email: str, ip: str):
    with write_transaction(db):
        timestamp = now()
        db.execute(delete(LoginLimit).where(LoginLimit.expires_at <= timestamp))
        for key, limit in ((digest(f"email:{email}"), 10), (digest(f"ip:{ip}"), 100)):
            row = db.get(LoginLimit, key)
            if row and row.attempts >= limit:
                raise HTTPException(
                    429,
                    "Demasiados intentos. Intenta más tarde.",
                    headers={"Retry-After": str(row.expires_at - timestamp)},
                )
            if row:
                row.attempts += 1
            else:
                db.add(LoginLimit(key=key, attempts=1, expires_at=timestamp + 900))


@router.post("/login", response_model=Identity)
def login(data: LoginInput, request: Request, response: Response, db: DB):
    email = data.email.lower()
    reserve_attempt(db, email, request.client.host if request.client else "unknown")
    user = db.scalar(select(User).where(User.email == email))
    valid = verify(user.password_hash if user else dummy_hash, data.password)
    if not valid or not user or not user.active:
        user_id = user.id if user else None
        db.rollback()
        with write_transaction(db):
            db.add(
                AuditLog(
                    user_id=user_id,
                    action="session.login_failed",
                    subject=user_id or "unknown",
                    result="failed",
                )
            )
        raise HTTPException(401, "Correo o contraseña incorrectos")
    user_id, verified_hash = user.id, user.password_hash
    db.rollback()
    with write_transaction(db):
        user = db.get(User, user_id)
        if not user or not user.active or user.password_hash != verified_hash:
            raise unauthorized()
        settings = request.app.state.settings
        mfa_required = user.platform_admin and settings.app_env == "production"
        if mfa_required:
            verify_mfa(db, settings, user.id, data.otp)
        db.execute(delete(LoginLimit).where(LoginLimit.key == digest(f"email:{email}")))
        tenants = available_tenants(db, user)
        session = LoginSession(
            user_id=user.id,
            tenant_id=tenants[0].id if len(tenants) == 1 else None,
            remember=data.remember,
            mfa_verified=mfa_required,
            expires_at=now()
            + (
                request.app.state.settings.refresh_token_expire_days * 86400
                if data.remember
                else 43200
            ),
        )
        db.add(session)
        db.flush()
        audit(db, user, "session.login", session.id, session.tenant_id)
        issue_refresh(request, response, db, session)
        issue_access(request, response, session)
        return identity(db, session, user)


@router.get("/me", response_model=Identity)
def me(request: Request, db: DB):
    session, user = credentials(request, db)
    return identity(db, session, user)


@router.post("/tenant", response_model=Identity)
def choose(data: ChooseTenant, request: Request, response: Response, db: DB):
    with write_transaction(db):
        session, user = credentials(request, db)
        tenant = next((row for row in available_tenants(db, user) if row.slug == data.slug), None)
        if not tenant:
            raise HTTPException(404, "Restaurante no disponible")
        session.tenant_id = tenant.id
        audit(db, user, "session.select_tenant", session.id, tenant.id)
        session.version += 1
        issue_access(request, response, session)
        return identity(db, session, user)


@router.post("/refresh", response_model=Identity)
def refresh(request: Request, response: Response, db: DB):
    raw = request.cookies.get(REFRESH, "")
    if not raw:
        raise unauthorized()
    with write_transaction(db):
        token = db.get(RefreshToken, digest(raw))
        session = db.get(LoginSession, token.session_id) if token else None
        if not session or session.revoked or session.expires_at <= now():
            raise unauthorized()
        user = db.get(User, session.user_id)
        if (
            not user
            or not user.active
            or (
                request.app.state.settings.app_env == "production"
                and user.platform_admin
                and not session.mfa_verified
            )
        ):
            raise unauthorized()
        if token.used:
            session.revoked = True
            audit(db, user, "session.refresh_reuse", session.id, session.tenant_id)
        else:
            token.used = True
            issue_refresh(request, response, db, session)
            issue_access(request, response, session)
            return identity(db, session, user)
    raise unauthorized()


@router.post("/logout")
def logout(request: Request, response: Response, db: DB):
    with write_transaction(db):
        raw = request.cookies.get(REFRESH, "")
        token = db.get(RefreshToken, digest(raw)) if raw else None
        session = db.get(LoginSession, token.session_id) if token else None
        if session and not session.revoked:
            session.revoked = True
            audit(
                db, db.get(User, session.user_id), "session.logout", session.id, session.tenant_id
            )
    secure = request.app.state.settings.app_env == "production"
    response.delete_cookie(ACCESS, httponly=True, secure=secure)
    response.delete_cookie(REFRESH, path="/api/auth", httponly=True, secure=secure)
    return {"ok": True}


@router.post("/reset")
def reset(data: ResetInput, db: DB):
    token_hash = digest(data.token)
    candidate = db.get(PasswordReset, token_hash)
    if not candidate or candidate.expires_at <= now():
        raise HTTPException(400, "Enlace inválido o vencido")
    db.rollback()
    encoded = hasher.hash(data.password)
    with write_transaction(db):
        token = db.get(PasswordReset, token_hash)
        user = db.get(User, token.user_id) if token else None
        if not token or token.expires_at <= now() or not user or not user.active:
            raise HTTPException(400, "Enlace inválido o vencido")
        user.password_hash = encoded
        db.execute(delete(PasswordReset).where(PasswordReset.user_id == user.id))
        db.execute(update(LoginSession).where(LoginSession.user_id == user.id).values(revoked=True))
        audit(db, user, "user.password_reset", user.id)
    return {"ok": True}
