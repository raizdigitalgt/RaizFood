import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr
from secrets import token_urlsafe
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response
from sqlalchemy import delete, func, select, update

from app.access import add_member, audit
from app.auth import DB, digest, hasher, reserve_attempt
from app.commercial import DEFAULT_METHODS, options, save_option, tenant_lookup, values
from app.commercial_models import Invitation, PlatformAsset
from app.commercial_schemas import (
    AssetInput,
    BrandingInput,
    GeneralInput,
    InvitationInput,
    MailTest,
    PermissionInput,
    PlatformRole,
    PlatformUserEdit,
    PlatformUserInput,
    SmtpInput,
)
from app.db import write_transaction
from app.images import image_data
from app.mailer_queue import enqueue
from app.mfa import cipher
from app.models import AuditLog, LoginSession, PasswordReset, Role, Tenant, User, now
from app.platform_access import PERMISSIONS, ROLE_GRANTS, platform_user
from app.schemas import ResetInput

router = APIRouter(prefix="/platform", tags=["Administración"])
public = APIRouter(tags=["Personalización e invitaciones"])
Asset = Literal["logo", "favicon", "login-logo", "login-background"]

DEFAULT_BRAND = {
    "name": "Raíz Food",
    "support_email": "",
    "contact": "",
    "footer": "",
    "primary": "#EA580C",
}


def platform_account(db, key):
    user = db.get(User, key)
    if not user or not user.platform_admin:
        raise HTTPException(404, "Usuario de plataforma no disponible")
    return user


def public_account(user):
    return {
        **values(user, ("id", "email", "name", "active", "created_at")),
        "role": user.platform_role or "super",
    }


@router.get("/users")
def users(request: Request, db: DB):
    platform_user(request, db, "users")
    return [
        public_account(user)
        for user in db.scalars(
            select(User).where(User.platform_admin.is_(True)).order_by(User.name, User.id)
        )
    ]


@router.post("/users", status_code=201)
def new_user(data: PlatformUserInput, request: Request, db: DB):
    platform_user(request, db, "users")
    db.rollback()
    encoded = hasher.hash(data.password)
    with write_transaction(db):
        actor = platform_user(request, db, "users")
        email = data.email.lower()
        if db.scalar(select(User.id).where(User.email == email)):
            raise HTTPException(409, "El correo ya está registrado")
        user = User(
            email=email,
            name=data.name,
            password_hash=encoded,
            platform_admin=True,
            platform_role=data.role,
        )
        db.add(user)
        db.flush()
        audit(db, actor, "platform.user_create", user.id)
        return public_account(user)


@router.put("/users/{key}")
def edit_user(key: str, data: PlatformUserEdit, request: Request, db: DB):
    with write_transaction(db):
        actor = platform_user(request, db, "users")
        user = platform_account(db, key)
        role = user.platform_role or "super"
        if user.active and role == "super" and (data.role != "super" or not data.active):
            another = db.scalar(
                select(User.id)
                .where(
                    User.id != user.id,
                    User.platform_admin.is_(True),
                    User.active.is_(True),
                    (User.platform_role == "super") | User.platform_role.is_(None),
                )
                .limit(1)
            )
            if not another:
                raise HTTPException(409, "Debe quedar un superadministrador activo")
        if user.active != data.active or role != data.role:
            db.execute(
                update(LoginSession).where(LoginSession.user_id == user.id).values(revoked=True)
            )
            audit(db, actor, "platform.user_access", user.id)
        user.name, user.platform_role, user.active = data.name, data.role, data.active
        audit(db, actor, "platform.user_edit", user.id)
        return public_account(user)


@router.get("/users/{key}/sessions")
def sessions(key: str, request: Request, db: DB):
    platform_user(request, db, "users")
    platform_account(db, key)
    return [
        values(row, ("id", "expires_at", "revoked", "mfa_verified"))
        for row in db.scalars(
            select(LoginSession)
            .where(LoginSession.user_id == key)
            .order_by(LoginSession.expires_at.desc())
            .limit(100)
        )
    ]


@router.post("/users/{key}/sessions/{session_id}/revoke")
def revoke(key: str, session_id: str, request: Request, db: DB):
    with write_transaction(db):
        actor = platform_user(request, db, "users")
        platform_account(db, key)
        session = db.get(LoginSession, session_id)
        if not session or session.user_id != key:
            raise HTTPException(404, "Sesión no disponible")
        session.revoked = True
        audit(db, actor, "platform.session_revoke", session.id)
    return {"ok": True}


@router.get("/roles")
def role_permissions(request: Request, db: DB):
    platform_user(request, db, "users")
    return {
        role: options(db, f"role:{role}", {"permissions": sorted(default)})["permissions"]
        for role, default in ROLE_GRANTS.items()
    }


@router.put("/roles/{role}")
def edit_role(role: PlatformRole, data: PermissionInput, request: Request, db: DB):
    with write_transaction(db):
        actor = platform_user(request, db, "users")
        scope = set(data.permissions) | {"dashboard"}
        if role == "super" or not scope <= PERMISSIONS - {"users", "smtp", "backups.download"}:
            raise HTTPException(422, "Estos permisos están reservados al superadministrador")
        save_option(db, f"role:{role}", {"permissions": sorted(scope)})
        audit(db, actor, "platform.role_permissions", role)
    return {"permissions": sorted(scope)}


def read_smtp(db):
    return options(db, "smtp", {"enabled": False})


def smtp_key(settings):
    if not settings.encryption_key:
        raise HTTPException(409, "Configura ENCRYPTION_KEY para guardar credenciales SMTP")
    return cipher(settings)


def allowed_host(settings, host):
    allowed = {
        value.strip().lower().rstrip(".") for value in settings.smtp_allowed_hosts.split(",")
    }
    return settings.smtp_mode == "mock" or host.lower().rstrip(".") in allowed - {""}


def deliver(settings, config, to, title, body):
    if not config.get("enabled"):
        raise HTTPException(409, "El servicio de correo está deshabilitado")
    if not allowed_host(settings, config["host"]):
        raise HTTPException(409, "Autoriza el servidor mediante SMTP_ALLOWED_HOSTS")
    if settings.smtp_mode == "mock":
        return "simulated"
    message = EmailMessage()
    message["From"] = formataddr((config["sender_name"], config["sender_email"]))
    message["To"], message["Subject"] = to, title
    message.set_content(body)
    context = ssl.create_default_context()
    try:
        if config["security"] == "ssl":
            connection = smtplib.SMTP_SSL(
                config["host"], config["port"], timeout=8, context=context
            )
        else:
            connection = smtplib.SMTP(config["host"], config["port"], timeout=8)
        with connection:
            if config["security"] == "starttls":
                connection.starttls(context=context)
            if config["username"]:
                password = (
                    smtp_key(settings).decrypt(config["encrypted_password"].encode()).decode()
                )
                connection.login(config["username"], password)
            connection.send_message(message)
    except (OSError, smtplib.SMTPException) as error:
        raise HTTPException(502, "El servidor SMTP rechazó o no pudo completar el envío") from error
    return "sent"


def mail_settings(request: Request):
    return request.app.state.settings


@router.get("/smtp")
def smtp_view(request: Request, db: DB):
    platform_user(request, db, "smtp")
    config = read_smtp(db)
    return {
        **{key: value for key, value in config.items() if key != "encrypted_password"},
        "has_password": bool(config.get("encrypted_password")),
        "mode": mail_settings(request).smtp_mode,
    }


@router.put("/smtp")
def edit_smtp(data: SmtpInput, request: Request, db: DB):
    settings = mail_settings(request)
    with write_transaction(db):
        actor = platform_user(request, db, "smtp")
        if data.enabled and not allowed_host(settings, data.host):
            raise HTTPException(422, "Autoriza el servidor mediante SMTP_ALLOWED_HOSTS")
        previous = read_smtp(db)
        encrypted = (
            previous.get("encrypted_password", "")
            if data.password is None
            else (
                smtp_key(settings).encrypt(data.password.encode()).decode() if data.password else ""
            )
        )
        if data.enabled and data.username and not encrypted:
            raise HTTPException(422, "Ingresa una contraseña para el usuario SMTP")
        save_option(
            db, "smtp", {**data.model_dump(exclude={"password"}), "encrypted_password": encrypted}
        )
        audit(db, actor, "smtp.configure", "smtp")
    return smtp_view(request, db)


@router.post("/smtp/test")
def test_mail(data: MailTest, request: Request, db: DB):
    with write_transaction(db):
        actor = platform_user(request, db, "smtp")
        if now() - options(db, "smtp_test", {"last": 0})["last"] < 60:
            raise HTTPException(429, "Espera un minuto antes de enviar otro correo")
        save_option(db, "smtp_test", {"last": now()})
        config = read_smtp(db)
        actor_id = actor.id
    try:
        result = deliver(
            mail_settings(request),
            config,
            data.email,
            "Prueba de Raíz Food",
            "Mensaje de prueba solicitado desde el panel de plataforma.",
        )
    except HTTPException:
        with write_transaction(db):
            db.add(AuditLog(user_id=actor_id, action="smtp.test", subject="smtp", result="failed"))
        raise
    with write_transaction(db):
        db.add(AuditLog(user_id=actor_id, action="smtp.test", subject="smtp", result=result))
    return {"status": result}


def issue_invitation(db, data, actor, tenant):
    if not read_smtp(db).get("enabled"):
        raise HTTPException(409, "Habilita el correo SMTP para enviar invitaciones")
    email = data.email.lower()
    if db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(409, "La cuenta ya existe. Usa la asociación de usuarios existentes.")
    role = (
        db.scalar(select(Role).where(Role.tenant_id == tenant.id, Role.code == data.role))
        if tenant
        else None
    )
    if (tenant and (not tenant.active or role is None)) or (
        not tenant and data.role not in ROLE_GRANTS
    ):
        raise HTTPException(422, "Rol o restaurante no disponible")
    tenant_id = tenant.id if tenant else None
    current = db.scalars(
        select(Invitation).where(
            Invitation.email == email,
            Invitation.tenant_id == tenant_id,
            Invitation.accepted_at.is_(None),
            Invitation.expires_at > now(),
        )
    ).all()
    if any(invitation.expires_at > now() + 86400 - 60 for invitation in current):
        raise HTTPException(429, "Espera un minuto para reenviar la invitación")
    for invitation in current:
        invitation.expires_at = now()
    token = token_urlsafe(32)
    db.add(
        Invitation(
            digest=digest(token),
            email=email,
            name=data.name,
            tenant_id=tenant_id,
            role_id=role.id if role else None,
            platform_role=None if tenant else data.role,
            actor_id=actor.id,
            expires_at=now() + 86400,
        )
    )
    audit(db, actor, "invitation.create", tenant_id or "platform", tenant_id)
    return token


def invite(request, db, data, slug=None):
    with write_transaction(db):
        actor = platform_user(request, db, "restaurants" if slug else "users")
        tenant = tenant_lookup(db, slug) if slug else None
        token = issue_invitation(db, data, actor, tenant)
        config = read_smtp(db)
    settings = mail_settings(request)
    link = f"{settings.frontend_url.rstrip('/')}/accept-invitation#token={token}"
    return {
        "status": deliver(
            settings,
            config,
            data.email,
            "Invitación a Raíz Food",
            f"Activa tu cuenta en las próximas 24 horas: {link}",
        )
    }


@router.post("/restaurants/{slug}/invitations", status_code=201)
def invite_restaurant(slug: str, data: InvitationInput, request: Request, db: DB):
    return invite(request, db, data, slug)


@router.post("/users/invitations", status_code=201)
def invite_platform(data: InvitationInput, request: Request, db: DB):
    return invite(request, db, data)


@public.post("/auth/invitations/accept")
def accept_invitation(data: ResetInput, db: DB):
    key = digest(data.token)
    invitation = db.get(Invitation, key)
    if not invitation or invitation.accepted_at or invitation.expires_at <= now():
        raise HTTPException(400, "La invitación no está disponible")
    db.rollback()
    encoded = hasher.hash(data.password)
    with write_transaction(db):
        invitation = db.get(Invitation, key)
        if not invitation or invitation.accepted_at or invitation.expires_at <= now():
            raise HTTPException(400, "La invitación no está disponible")
        if db.scalar(select(User.id).where(User.email == invitation.email)):
            raise HTTPException(409, "El correo ya está registrado")
        actor = db.get(User, invitation.actor_id)
        from app.platform_access import platform_grants

        if not actor.active or (
            "restaurants" if invitation.tenant_id else "users"
        ) not in platform_grants(db, actor):
            raise HTTPException(409, "La invitación requiere una nueva autorización")
        user = User(
            name=invitation.name,
            email=invitation.email,
            password_hash=encoded,
            platform_admin=bool(invitation.platform_role),
            platform_role=invitation.platform_role,
        )
        db.add(user)
        db.flush()
        if invitation.tenant_id:
            tenant = db.get(Tenant, invitation.tenant_id)
            if not tenant.active:
                raise HTTPException(409, "El restaurante está suspendido")
            add_member(db, tenant, user, db.get(Role, invitation.role_id))
        invitation.accepted_at = now()
        audit(db, user, "invitation.accept", user.id, invitation.tenant_id)
        enqueue(
            db,
            f"account:{user.id}",
            user.email,
            "Cuenta activada en Raíz Food",
            "Tu cuenta fue activada.",
            invitation.tenant_id,
        )
    return {"ok": True}


@public.post("/auth/recover", status_code=202)
def recover(data: MailTest, request: Request, background: BackgroundTasks, db: DB):
    ip = request.client.host if request.client else "unknown"
    reserve_attempt(db, f"recover:{data.email.lower()}", f"recover:{ip}")
    with write_transaction(db):
        config = read_smtp(db)
        user = db.scalar(
            select(User).where(User.email == data.email.lower(), User.active.is_(True))
        )
        token = None
        if user and config.get("enabled"):
            current = db.scalar(
                select(PasswordReset)
                .where(
                    PasswordReset.user_id == user.id,
                    PasswordReset.expires_at > now() + 840,
                )
                .limit(1)
            )
            if not current:
                token = token_urlsafe(32)
                db.execute(delete(PasswordReset).where(PasswordReset.user_id == user.id))
                db.add(PasswordReset(digest=digest(token), user_id=user.id, expires_at=now() + 900))
    if token:
        background.add_task(deliver_reset, mail_settings(request), config, data.email, token)
    return {"ok": True}


def deliver_reset(settings, config, email, token):
    from app.cli import connect

    link = f"{settings.frontend_url.rstrip('/')}/reset-password#token={token}"
    try:
        deliver(
            settings,
            config,
            email,
            "Recuperación de Raíz Food",
            f"Cambia tu contraseña en los próximos 15 minutos: {link}",
        )
    except HTTPException:
        with connect(settings) as db, write_transaction(db):
            db.execute(delete(PasswordReset).where(PasswordReset.digest == digest(token)))
            db.add(AuditLog(action="smtp.recovery", subject="recovery", result="failed"))


@router.get("/settings")
def general(request: Request, db: DB):
    platform_user(request, db, "settings")
    return options(
        db, "general", {"payment_methods": DEFAULT_METHODS, "platform_name": "Raíz Food"}
    )


@router.get("/payment-methods")
def payment_methods(request: Request, db: DB):
    platform_user(request, db, "payments")
    return options(db, "general", {"payment_methods": DEFAULT_METHODS})["payment_methods"]


@router.put("/settings")
def edit_general(data: GeneralInput, request: Request, db: DB):
    with write_transaction(db):
        actor = platform_user(request, db, "settings")
        if not all(data.payment_methods):
            raise HTTPException(422, "Ingresa nombres de métodos de pago")
        payload = data.model_dump()
        payload["payment_methods"] = list(dict.fromkeys(data.payment_methods))
        save_option(db, "general", payload)
        audit(db, actor, "platform.settings", "general")
        return payload


@public.get("/branding")
def branding(db: DB):
    brand = options(db, "branding", DEFAULT_BRAND)
    return {**brand, "assets": list(db.scalars(select(PlatformAsset.key)))}


@router.put("/branding")
def edit_branding(data: BrandingInput, request: Request, db: DB):
    with write_transaction(db):
        actor = platform_user(request, db, "branding")
        save_option(db, "branding", data.model_dump())
        audit(db, actor, "branding.configure", "branding")
        return branding(db)


@public.get("/branding/assets/{key}")
def get_asset(key: Asset, db: DB):
    asset = db.get(PlatformAsset, key)
    if not asset:
        raise HTTPException(404, "Imagen no disponible")
    return Response(asset.content, media_type=asset.content_type)


@router.put("/branding/assets/{key}")
def put_asset(key: Asset, data: AssetInput, request: Request, db: DB):
    platform_user(request, db, "branding")
    db.rollback()
    content, content_type = image_data(data.content)
    with write_transaction(db):
        actor = platform_user(request, db, "branding")
        db.merge(PlatformAsset(key=key, content=content, content_type=content_type))
        audit(db, actor, "branding.asset_update", key)
    return {"ok": True}


@router.delete("/branding/assets/{key}")
def delete_asset(key: Asset, request: Request, db: DB):
    with write_transaction(db):
        actor = platform_user(request, db, "branding")
        db.execute(delete(PlatformAsset).where(PlatformAsset.key == key))
        audit(db, actor, "branding.asset_restore", key)
    return {"ok": True}


@router.get("/audit")
def audit_log(
    request: Request,
    db: DB,
    q: str = "",
    restaurant: str = "",
    result: str = "",
    start: int | None = None,
    end: int | None = None,
):
    platform_user(request, db, "audit")
    query = (
        select(AuditLog, User.name, Tenant.name)
        .outerjoin(User, User.id == AuditLog.user_id)
        .outerjoin(Tenant, Tenant.id == AuditLog.tenant_id)
    )
    if q:
        query = query.where(
            AuditLog.action.icontains(q, autoescape=True) | User.name.icontains(q, autoescape=True)
        )
    if restaurant:
        query = query.where(Tenant.slug == restaurant)
    if result:
        query = query.where(AuditLog.result == result)
    if start is not None:
        query = query.where(AuditLog.created_at >= start)
    if end is not None:
        query = query.where(AuditLog.created_at <= end)
    return [
        {
            **values(entry, ("id", "action", "subject", "created_at", "result", "detail")),
            "user": user or "Sistema",
            "restaurant": name,
        }
        for entry, user, name in db.execute(
            query.order_by(AuditLog.created_at.desc(), AuditLog.id).limit(300)
        )
    ]


@router.get("/security")
def security(request: Request, db: DB):
    platform_user(request, db, "settings")
    settings = mail_settings(request)
    sessions_count = db.scalar(
        select(func.count())
        .select_from(LoginSession)
        .where(
            LoginSession.revoked.is_(False),
            LoginSession.expires_at > now(),
        )
    )
    return {
        "environment": settings.app_env,
        "platform_mfa_required": settings.app_env == "production",
        "active_sessions": sessions_count,
        "encryption_configured": bool(settings.encryption_key),
    }
