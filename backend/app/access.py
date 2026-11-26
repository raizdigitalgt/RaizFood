from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.commercial_models import Invitation, OnboardingPlan, PlanVersion
from app.config import Settings
from app.entitlements import contracted_plan, operational
from app.models import (
    AuditLog,
    Membership,
    Permission,
    Plan,
    Role,
    RolePermission,
    Tenant,
    User,
    now,
)

NEW_PERMISSIONS = {
    "categories.view",
    "categories.create",
    "categories.edit",
    "categories.archive",
    "menu.create",
    "menu.edit",
    "menu.archive",
    "customers.view",
    "customers.create",
    "customers.edit",
    "customers.archive",
    "customers.export",
    "users.invite",
    "users.sessions",
    "users.recover",
}
ADMIN_PERMISSIONS = {
    "users.manage",
    "roles.manage",
    "settings.manage",
    "users.invite",
    "users.sessions",
    "users.recover",
}
ROLE_NAMES = {
    "admin": "Administrador",
    "cashier": "Cajero",
    "waiter": "Mesero",
    "cook": "Cocinero",
    "inventory": "Encargado de inventario",
}
ROLE_GRANTS = {
    "cashier": {
        "pos.access",
        "orders.view",
        "orders.checkout",
        "cash.open",
        "cash.close",
        "cash.movements",
        "receipts.print",
        "receipts.reprint",
    },
    "waiter": {"pos.access", "orders.create", "orders.view", "orders.update", "tables.view"},
    "cook": {"kitchen.view", "kitchen.update"},
    "inventory": {"inventory.view", "inventory.manage", "inventory.adjust", "purchases.manage"},
}
ALL_PERMISSIONS = (
    ADMIN_PERMISSIONS
    | NEW_PERMISSIONS
    | set.union(*ROLE_GRANTS.values())
    | {
        "dashboard.view",
        "orders.cancel",
        "orders.discount",
        "tables.manage",
        "menu.view",
        "menu.manage",
        "recipes.manage",
        "suppliers.manage",
        "customers.manage",
        "fel.issue",
        "fel.cancel",
        "fel.view",
        "reports.view",
        "reports.export",
        "printers.manage",
        "media.manage",
        "subscription.view",
        "audit.view",
    }
)


@dataclass(frozen=True)
class RestaurantAccess:
    tenant: Tenant
    role: Role
    permissions: set[str]

    def require(self, permission: str):
        if permission not in self.permissions:
            raise HTTPException(403, "Permiso insuficiente")


def grants(db: Session, role: Role) -> set[str]:
    return set(
        db.scalars(
            select(RolePermission.permission).where(
                RolePermission.tenant_id == role.tenant_id, RolePermission.role_id == role.id
            )
        )
    )


def access_for(db: Session, user: User, tenant_id: str | None) -> RestaurantAccess | None:
    if tenant_id is None or user.platform_admin:
        return None
    membership = db.get(Membership, (user.id, tenant_id))
    tenant = db.get(Tenant, tenant_id)
    if not membership or not membership.active or not tenant or not tenant.active:
        return None
    role = db.scalar(select(Role).where(Role.tenant_id == tenant.id, Role.id == membership.role_id))
    if not role:
        return None
    permissions = grants(db, role)
    plan = contracted_plan(db, tenant)
    if not plan.fel_enabled:
        permissions -= {"fel.issue", "fel.cancel", "fel.view"}
    if not operational(db, tenant.id):
        permissions &= {"dashboard.view", "subscription.view", "fel.view"}
    return RestaurantAccess(tenant, role, permissions)


def available_tenants(db: Session, user: User):
    if user.platform_admin:
        return []
    return list(
        db.scalars(
            select(Tenant)
            .join(Membership)
            .where(
                Membership.user_id == user.id, Membership.active.is_(True), Tenant.active.is_(True)
            )
            .order_by(Tenant.name, Tenant.id)
        )
    )


def seed_plans(db: Session, settings: Settings):
    defaults = (
        ("basic", "Básico", settings.basic_monthly_cents, 1, 4, False),
        ("pro", "Pro", settings.pro_monthly_cents, 2, 8, True),
    )
    for code, name, price, admins, staff, fel in defaults:
        if not db.scalar(select(Plan.id).where(Plan.code == code)):
            terms = {
                "name": name,
                "monthly_cents": price,
                "max_admins": admins,
                "max_staff": staff,
                "max_total": admins + staff,
                "fel_enabled": fel,
            }
            plan = Plan(code=code, **terms)
            db.add(plan)
            db.flush()
            db.add(
                PlanVersion(
                    plan_id=plan.id,
                    revision=1,
                    description="",
                    features=[],
                    trial_days=0,
                    grace_days=0,
                    **terms,
                )
            )
    existing = set(db.scalars(select(Permission.code)))
    db.add_all(Permission(code=code) for code in sorted(ALL_PERMISSIONS - existing))
    db.flush()


def create_restaurant(db: Session, slug: str, name: str, plan: Plan):
    tenant = Tenant(slug=slug, name=name, plan_id=plan.id)
    db.add(tenant)
    db.flush()
    version_id = db.scalar(
        select(PlanVersion.id)
        .where(PlanVersion.plan_id == plan.id)
        .order_by(PlanVersion.revision.desc())
        .limit(1)
    )
    if version_id:
        db.add(OnboardingPlan(tenant_id=tenant.id, plan_version_id=version_id))
    roles = {}
    for code, name in ROLE_NAMES.items():
        role = Role(tenant_id=tenant.id, code=code, name=name)
        db.add(role)
        roles[code] = role
    db.flush()
    for code, role in roles.items():
        permissions = ALL_PERMISSIONS if code == "admin" else ROLE_GRANTS[code] | {"dashboard.view"}
        db.add_all(
            RolePermission(tenant_id=tenant.id, role_id=role.id, permission=permission)
            for permission in sorted(permissions)
        )
    return tenant


def usage(db: Session, tenant_ids: list[str]):
    # Distinct role IDs prevent counting an administrator once per permission.
    admin_roles = select(RolePermission.role_id).where(
        RolePermission.tenant_id.in_(tenant_ids),
        RolePermission.permission.in_(ADMIN_PERMISSIONS),
    )
    rows = db.execute(
        select(Membership.tenant_id, Membership.role_id.in_(admin_roles), func.count())
        .join(User, User.id == Membership.user_id)
        .where(
            Membership.tenant_id.in_(tenant_ids),
            Membership.active.is_(True),
            User.active.is_(True),
            User.platform_admin.is_(False),
        )
        .group_by(Membership.tenant_id, Membership.role_id.in_(admin_roles))
    )
    counts = {tenant_id: {"admins": 0, "staff": 0, "total": 0} for tenant_id in tenant_ids}
    for tenant_id, administrator, count in rows:
        counts[tenant_id]["admins" if administrator else "staff"] = count
        counts[tenant_id]["total"] += count
    return counts


def effective_grants(db, tenant, role):
    permissions = grants(db, role)
    if not contracted_plan(db, tenant).fel_enabled:
        permissions = {
            permission for permission in permissions if not permission.startswith("fel.")
        }
    return permissions


def seat_usage(db, tenant_id):
    count = usage(db, [tenant_id])[tenant_id]
    admin_roles = select(RolePermission.role_id).where(
        RolePermission.tenant_id == tenant_id,
        RolePermission.permission.in_(ADMIN_PERMISSIONS),
    )
    held = db.execute(
        select(Invitation.role_id.in_(admin_roles), func.count())
        .where(
            Invitation.tenant_id == tenant_id,
            Invitation.accepted_at.is_(None),
            Invitation.expires_at > now(),
        )
        .group_by(Invitation.role_id.in_(admin_roles))
    )
    for admin, n in held:
        count["admins" if admin else "staff"] += n
        count["total"] += n
    return count


def reserve_seat(db, tenant, permissions):
    plan = contracted_plan(db, tenant)
    count = seat_usage(db, tenant.id)
    admin = bool(permissions & ADMIN_PERMISSIONS)
    enforce_capacity(plan, count["admins"] + int(admin), count["staff"] + int(not admin))


def enforce_capacity(plan, admins, staff):
    if admins > plan.max_admins or staff > plan.max_staff or admins + staff > plan.max_total:
        raise HTTPException(409, "Se alcanzó el límite de usuarios de este plan")


def add_member(
    db: Session, tenant: Tenant, user: User, role: Role, actor: RestaurantAccess | None = None
):
    if role.tenant_id != tenant.id or user.platform_admin or not user.active:
        raise HTTPException(409, "La cuenta o el rol no se puede asociar")
    if db.get(Membership, (user.id, tenant.id)):
        raise HTTPException(409, "La cuenta ya pertenece al restaurante")
    role_permissions = effective_grants(db, tenant, role)
    if actor and not role_permissions <= actor.permissions:
        raise HTTPException(403, "No puedes asignar permisos que no posees")
    reserve_seat(db, tenant, role_permissions)
    db.add(Membership(user_id=user.id, tenant_id=tenant.id, role_id=role.id))


def audit(db: Session, user: User, action: str, subject: str, tenant_id: str | None = None):
    db.add(AuditLog(user_id=user.id, tenant_id=tenant_id, action=action, subject=subject))
