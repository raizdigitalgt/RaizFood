from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app import restaurant_models as m
from app.access import (
    ALL_PERMISSIONS,
    audit,
    effective_grants,
    enforce_capacity,
    grants,
    seat_usage,
    usage,
)
from app.auth import DB
from app.commercial_models import Invitation
from app.commercial_schemas import InvitationInput, MailTest
from app.db import write_transaction
from app.entitlements import contracted_plan
from app.models import AuditLog, LoginSession, Membership, Role, RolePermission, User, now, uuid
from app.operations import restaurant_user
from app.platform_admin import deliver_invitation, issue_invitation, read_smtp, recover
from app.restaurant_records import normalized
from app.restaurant_schemas import MemberEdit, RoleEdit

router = APIRouter(prefix="/restaurants/{slug}", tags=["Equipo del restaurante"])


def authorize(request, db, slug, *scopes):
    actor, access = restaurant_user(request, db, slug, None)
    if not set(scopes) & access.permissions:
        raise HTTPException(403, "Permiso de equipo insuficiente")
    return actor, access


def role_by_code(db, tenant_id, code):
    role = db.scalar(select(Role).where(Role.tenant_id == tenant_id, Role.code == code))
    if not role:
        raise HTTPException(404, "Rol no disponible")
    return role


def target_member(db, access, key):
    tenant = access.tenant
    member = db.get(Membership, (key, tenant.id))
    if not member:
        raise HTTPException(404, "Integrante no disponible")
    role = db.scalar(select(Role).where(Role.tenant_id == tenant.id, Role.id == member.role_id))
    if not effective_grants(db, tenant, role) <= access.permissions:
        raise HTTPException(403, "El rol del integrante requiere más permisos")
    return member, role


def verify_staff(db, tenant):
    db.flush()
    if usage(db, [tenant.id])[tenant.id]["admins"] < 1:
        raise HTTPException(409, "Debe quedar al menos un administrador activo")
    committed = seat_usage(db, tenant.id)
    enforce_capacity(contracted_plan(db, tenant), committed["admins"], committed["staff"])


@router.get("/staff")
def staff(slug: str, request: Request, db: DB):
    _, access = authorize(request, db, slug, "users.manage")
    tenant = access.tenant
    last = (
        select(AuditLog.user_id.label("uid"), func.max(AuditLog.created_at).label("seen"))
        .where(
            AuditLog.tenant_id == tenant.id,
            AuditLog.action.in_(["session.login", "session.select_tenant"]),
        )
        .group_by(AuditLog.user_id)
        .subquery()
    )
    profiles = m.member_profiles
    rows = db.execute(
        select(
            User.id,
            User.email,
            User.name,
            profiles.c.display_name,
            (Membership.active & User.active).label("active"),
            Role.code,
            Role.name,
            last.c.seen,
        )
        .join(Membership, Membership.user_id == User.id)
        .join(Role, (Role.id == Membership.role_id) & (Role.tenant_id == Membership.tenant_id))
        .outerjoin(
            profiles,
            (profiles.c.user_id == User.id) & (profiles.c.tenant_id == Membership.tenant_id),
        )
        .outerjoin(last, last.c.uid == User.id)
        .where(Membership.tenant_id == tenant.id)
        .order_by(func.coalesce(profiles.c.display_name, User.name), User.id)
    )
    members = [
        {
            "id": key,
            "email": email,
            "name": local or name,
            "active": active,
            "role_code": code,
            "role": role,
            "last_access": seen,
        }
        for key, email, name, local, active, code, role, seen in rows
    ]
    plan = contracted_plan(db, tenant)
    return {
        "items": members,
        "usage": usage(db, [tenant.id])[tenant.id],
        "held": seat_usage(db, tenant.id),
        "limits": {key: getattr(plan, key) for key in ("max_admins", "max_staff", "max_total")},
    }


@router.put("/staff/{key}")
def edit_staff(slug: str, key: str, data: MemberEdit, request: Request, db: DB):
    with write_transaction(db):
        actor, access = authorize(request, db, slug, "users.manage")
        tenant = access.tenant
        member, current = target_member(db, access, key)
        role = role_by_code(db, tenant.id, data.role_code)
        if not effective_grants(db, tenant, role) <= access.permissions:
            raise HTTPException(403, "No puedes asignar permisos que no posees")
        changed = current.id != role.id or member.active != data.active
        member.role_id, member.active = role.id, data.active
        profile = sqlite_insert(m.member_profiles).values(
            tenant_id=tenant.id,
            user_id=key,
            display_name=data.display_name,
        )
        db.execute(
            profile.on_conflict_do_update(
                index_elements=["tenant_id", "user_id"],
                set_={"display_name": profile.excluded.display_name},
            )
        )
        verify_staff(db, tenant)
        if changed:
            db.execute(
                update(LoginSession)
                .where(LoginSession.tenant_id == tenant.id, LoginSession.user_id == key)
                .values(revoked=True)
            )
        audit(db, actor, "restaurant.staff.edit", key, tenant.id)
        return {"ok": True}


@router.get("/staff/{key}/sessions")
def staff_sessions(slug: str, key: str, request: Request, db: DB):
    _, access = authorize(request, db, slug, "users.sessions", "users.manage")
    target_member(db, access, key)
    return [
        {"id": row.id, "expires_at": row.expires_at, "revoked": row.revoked}
        for row in db.scalars(
            select(LoginSession)
            .where(LoginSession.tenant_id == access.tenant.id, LoginSession.user_id == key)
            .order_by(LoginSession.expires_at.desc())
            .limit(100)
        )
    ]


@router.post("/staff/{key}/sessions/{session_id}/revoke")
def revoke_session(slug: str, key: str, session_id: str, request: Request, db: DB):
    with write_transaction(db):
        actor, access = authorize(request, db, slug, "users.sessions", "users.manage")
        target_member(db, access, key)
        tenant = access.tenant.id
        session = db.scalar(
            select(LoginSession).where(
                LoginSession.id == session_id,
                LoginSession.tenant_id == tenant,
                LoginSession.user_id == key,
            )
        )
        if not session:
            raise HTTPException(404, "Sesión no disponible")
        session.revoked = True
        audit(db, actor, "restaurant.staff.revoke", key, tenant)
    return {"ok": True}


@router.post("/staff/{key}/recover", status_code=202)
def recover_staff(slug: str, key: str, request: Request, background: BackgroundTasks, db: DB):
    _, access = authorize(request, db, slug, "users.recover", "users.manage")
    target_member(db, access, key)
    email = db.get(User, key).email
    db.rollback()
    return recover(MailTest(email=email), request, background, db)


@router.get("/roles")
def roles(slug: str, request: Request, db: DB):
    _, access = authorize(request, db, slug, "users.manage", "roles.manage", "users.invite")
    tenant = access.tenant.id
    role_rows = db.scalars(select(Role).where(Role.tenant_id == tenant).order_by(Role.name))
    permissions = {}
    for key, scope in db.execute(
        select(RolePermission.role_id, RolePermission.permission).where(
            RolePermission.tenant_id == tenant
        )
    ):
        permissions.setdefault(key, set()).add(scope)
    plan = contracted_plan(db, access.tenant)
    permitted = set(access.permissions)
    output = []
    for role in role_rows:
        raw = permissions.get(role.id, set())
        effective = raw if plan.fel_enabled else {key for key in raw if not key.startswith("fel.")}
        output.append(
            {
                "name": role.name,
                "code": role.code,
                "permissions": sorted(effective),
                "editable": role.code.startswith("r-") and effective <= permitted,
                "assignable": effective <= permitted,
            }
        )
    return {"items": output, "permissions": sorted(permitted)}


def save_role(slug, request, db, data, code=None):
    scopes = set(data.permissions)
    with write_transaction(db):
        actor, access = authorize(request, db, slug, "roles.manage")
        tenant = access.tenant
        if not scopes <= ALL_PERMISSIONS & access.permissions:
            raise HTTPException(403, "No puedes conceder permisos que no posees")
        internal = code or f"r-{uuid()}"
        existing = db.scalars(select(Role).where(Role.tenant_id == tenant.id)).all()
        if any(
            role.code != internal and normalized(role.name) == normalized(data.name)
            for role in existing
        ):
            raise HTTPException(409, "Ya existe un rol con ese nombre")
        if code:
            role = role_by_code(db, tenant.id, code)
            if (
                not role.code.startswith("r-")
                or not effective_grants(db, tenant, role) <= access.permissions
            ):
                raise HTTPException(403, "El rol está protegido")
            # A Basic administrator cannot change hidden Pro privileges assigned before a downgrade.
            scopes |= grants(db, role) - effective_grants(db, tenant, role)
        else:
            role = Role(tenant_id=tenant.id, code=internal, name=data.name)
            db.add(role)
            db.flush()
        role.name = data.name
        db.execute(
            delete(RolePermission).where(
                RolePermission.tenant_id == tenant.id,
                RolePermission.role_id == role.id,
            )
        )
        if scopes:
            db.execute(
                insert(RolePermission),
                [
                    {"tenant_id": tenant.id, "role_id": role.id, "permission": permission}
                    for permission in sorted(scopes)
                ],
            )
        verify_staff(db, tenant)
        audit(
            db,
            actor,
            "restaurant.roles.edit" if code else "restaurant.roles.create",
            role.id,
            tenant.id,
        )
        return {"code": role.code, "name": role.name}


@router.post("/roles", status_code=201)
def create_role(slug: str, data: RoleEdit, request: Request, db: DB):
    return save_role(slug, request, db, data)


@router.put("/roles/{code}")
def edit_role(slug: str, code: str, data: RoleEdit, request: Request, db: DB):
    return save_role(slug, request, db, data, code)


@router.get("/staff-invitations")
def invitations(slug: str, request: Request, db: DB):
    _, access = authorize(request, db, slug, "users.manage", "users.invite")
    rows = db.execute(
        select(Invitation, Role.code)
        .join(Role, (Invitation.role_id == Role.id) & (Invitation.tenant_id == Role.tenant_id))
        .where(Invitation.tenant_id == access.tenant.id)
        .order_by(Invitation.expires_at.desc())
        .limit(100)
    )
    result = []
    for row, role in rows:
        state = (
            "accepted"
            if row.accepted_at
            else "cancelled"
            if row.cancelled_at
            else ("pending" if row.expires_at > now() else "expired")
        )
        result.append(
            {
                "email": row.email,
                "name": row.name,
                "role": role,
                "state": state,
                "expires_at": row.expires_at,
            }
        )
    return result


@router.post("/staff-invitations", status_code=201)
def invite_staff(slug: str, data: InvitationInput, request: Request, db: DB):
    with write_transaction(db):
        actor, access = authorize(request, db, slug, "users.manage", "users.invite")
        token = issue_invitation(db, data, actor, access.tenant, access)
        config = read_smtp(db)
    return deliver_invitation(request.app.state.settings, config, data.email, token)


@router.post("/staff-invitations/cancel")
def cancel_invitation(slug: str, data: MailTest, request: Request, db: DB):
    with write_transaction(db):
        actor, access = authorize(request, db, slug, "users.manage", "users.invite")
        tenant = access.tenant
        invitations = db.scalars(
            select(Invitation).where(
                Invitation.tenant_id == tenant.id,
                Invitation.email == data.email.lower(),
                Invitation.accepted_at.is_(None),
                Invitation.expires_at > now(),
            )
        ).all()
        if not invitations:
            raise HTTPException(404, "Invitación pendiente no disponible")
        for invitation in invitations:
            role = db.get(Role, invitation.role_id)
            if not effective_grants(db, tenant, role) <= access.permissions:
                raise HTTPException(403, "La invitación requiere más permisos")
            invitation.cancelled_at = invitation.expires_at = now()
        audit(db, actor, "restaurant.invitation.cancel", tenant.id, tenant.id)
    return {"ok": True}
