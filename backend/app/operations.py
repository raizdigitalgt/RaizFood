from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import func, select

from app.access import RestaurantAccess, access_for, add_member, audit, create_restaurant, usage
from app.auth import DB, credentials, hasher
from app.db import write_transaction
from app.entitlements import contracted_plan
from app.mailer_queue import enqueue
from app.models import Membership, Plan, Role, Tenant, User
from app.platform_access import platform_user
from app.schemas import (
    MemberInput,
    MemberResponse,
    PlanResponse,
    PlatformDashboard,
    RestaurantInput,
    RestaurantPage,
    RestaurantResponse,
    TeamPage,
)

platform = APIRouter(prefix="/platform", tags=["Plataforma"])
restaurant = APIRouter(prefix="/restaurants/{slug}", tags=["Restaurante"])


def restaurant_user(request: Request, db: DB, slug: str, permission: str | None):
    session, user = credentials(request, db)
    access = access_for(db, user, session.tenant_id)
    if not access or access.tenant.slug != slug:
        raise HTTPException(404, "Restaurante no disponible")
    if permission:
        access.require(permission)
    return user, access


def pack_restaurants(db: DB, rows):
    counts = usage(db, [tenant.id for tenant, _ in rows])
    return [
        {
            "slug": tenant.slug,
            "name": tenant.name,
            "active": tenant.active,
            "created_at": tenant.created_at,
            "plan": {
                **{
                    field: getattr(contract, field)
                    for field in (
                        "name",
                        "monthly_cents",
                        "max_admins",
                        "max_staff",
                        "max_total",
                        "fel_enabled",
                    )
                },
                "code": plan.code,
            },
            "usage": counts[tenant.id],
        }
        for tenant, plan in rows
        for contract in (contracted_plan(db, tenant),)
    ]


def restaurant_query():
    return select(Tenant, Plan).join(Plan, Plan.id == Tenant.plan_id)


@platform.get("/dashboard", response_model=PlatformDashboard)
def platform_dashboard(request: Request, db: DB):
    platform_user(request, db)
    recent = db.execute(restaurant_query().order_by(Tenant.created_at.desc(), Tenant.id).limit(6))
    return {
        "restaurants": db.scalar(select(func.count()).select_from(Tenant)),
        "active": db.scalar(
            select(func.count()).select_from(Tenant).where(Tenant.active.is_(True))
        ),
        "users": db.scalar(select(func.count()).select_from(User).where(User.active.is_(True))),
        "plans": db.scalar(select(func.count()).select_from(Plan)),
        "recent": pack_restaurants(db, recent.all()),
    }


@platform.get("/plans", response_model=list[PlanResponse])
def list_plans(request: Request, db: DB):
    platform_user(request, db, "plans")
    return db.scalars(
        select(Plan).where(Plan.active.is_(True)).order_by(Plan.monthly_cents, Plan.code)
    ).all()


@platform.get("/restaurants", response_model=RestaurantPage)
def list_restaurants(
    request: Request,
    db: DB,
    q: Annotated[str, Query(max_length=100)] = "",
    page: Annotated[int, Query(ge=1, le=10000)] = 1,
    state: Literal["", "active", "suspended"] = "",
    plan_code: Annotated[str, Query(max_length=30)] = "",
):
    platform_user(request, db, "restaurants")
    match = Tenant.name.icontains(q, autoescape=True) | Tenant.slug.icontains(q, autoescape=True)
    if state:
        match &= Tenant.active.is_(state == "active")
    if plan_code:
        match &= Tenant.plan_id.in_(select(Plan.id).where(Plan.code == plan_code))
    rows = db.execute(
        restaurant_query()
        .where(match)
        .order_by(Tenant.name, Tenant.id)
        .offset((page - 1) * 12)
        .limit(12)
    ).all()
    total = db.scalar(select(func.count()).select_from(Tenant).where(match))
    return {"items": pack_restaurants(db, rows), "total": total}


@platform.post("/restaurants", response_model=RestaurantResponse, status_code=201)
def new_restaurant(data: RestaurantInput, request: Request, db: DB):
    with write_transaction(db):
        actor = platform_user(request, db, "restaurants")
        if db.scalar(select(Tenant.id).where(Tenant.slug == data.slug)):
            raise HTTPException(409, "El identificador ya está en uso")
        plan = db.scalar(select(Plan).where(Plan.code == data.plan_code))
        if not plan or not plan.active:
            raise HTTPException(404, "Plan no disponible")
        tenant = create_restaurant(db, data.slug, data.name, plan)
        audit(db, actor, "restaurant.create", tenant.id, tenant.id)
        return pack_restaurants(db, [(tenant, plan)])[0]


def member_create(
    db: DB,
    data: MemberInput,
    actor: User,
    tenant: Tenant,
    encoded: str | None,
    access: RestaurantAccess | None = None,
):
    role = db.scalar(select(Role).where(Role.tenant_id == tenant.id, Role.code == data.role_code))
    if not role:
        raise HTTPException(404, "Rol no disponible")
    email = data.email.lower()
    user = db.scalar(select(User).where(User.email == email))
    if not user:
        if not encoded or not data.name:
            raise HTTPException(422, "Ingresa nombre y contraseña inicial para la cuenta nueva")
        user = User(email=email, name=data.name, password_hash=encoded)
        db.add(user)
        db.flush()
    elif access or encoded or data.name:
        raise HTTPException(409, "La cuenta ya existe. Contacta a la administración de plataforma")
    add_member(db, tenant, user, role, access)
    audit(db, actor, "membership.create", user.id, tenant.id)
    if encoded:
        enqueue(
            db,
            f"account:{user.id}",
            user.email,
            "Cuenta de Raíz Food",
            f"Tu cuenta para {tenant.name} fue registrada.",
            tenant.id,
        )
    return {"name": user.name, "email": user.email, "role": role.name, "active": True}


@platform.post("/restaurants/{slug}/members", response_model=MemberResponse, status_code=201)
def platform_add_member(slug: str, data: MemberInput, request: Request, db: DB):
    platform_user(request, db, "restaurants")
    db.rollback()
    encoded = hasher.hash(data.password) if data.password else None
    with write_transaction(db):
        actor = platform_user(request, db, "restaurants")
        tenant = db.scalar(select(Tenant).where(Tenant.slug == slug, Tenant.active.is_(True)))
        if not tenant:
            raise HTTPException(404, "Restaurante no disponible")
        return member_create(db, data, actor, tenant, encoded)


@restaurant.get("/dashboard", response_model=RestaurantResponse)
def restaurant_dashboard(slug: str, request: Request, db: DB):
    _, access = restaurant_user(request, db, slug, "dashboard.view")
    tenant = access.tenant
    return pack_restaurants(db, [(tenant, db.get(Plan, tenant.plan_id))])[0]


@restaurant.get("/members", response_model=TeamPage)
def list_members(slug: str, request: Request, db: DB):
    _, access = restaurant_user(request, db, slug, "users.manage")
    return list_team(db, access.tenant.id)


def list_team(db: DB, tenant_id: str):
    rows = (
        db.execute(
            select(
                User.name,
                User.email,
                Role.name.label("role"),
                (Membership.active & User.active).label("active"),
            )
            .join(Membership, Membership.user_id == User.id)
            .join(Role, (Role.id == Membership.role_id) & (Role.tenant_id == Membership.tenant_id))
            .where(Membership.tenant_id == tenant_id)
            .order_by(User.name, User.id)
        )
        .mappings()
        .all()
    )
    roles = db.scalars(select(Role).where(Role.tenant_id == tenant_id).order_by(Role.name)).all()
    return {"items": rows, "roles": roles}


@restaurant.post("/members", response_model=MemberResponse, status_code=201)
def restaurant_add_member(slug: str, data: MemberInput, request: Request, db: DB):
    restaurant_user(request, db, slug, "users.manage")
    db.rollback()
    encoded = hasher.hash(data.password) if data.password else None
    with write_transaction(db):
        actor, access = restaurant_user(request, db, slug, "users.manage")
        return member_create(db, data, actor, access.tenant, encoded, access)
