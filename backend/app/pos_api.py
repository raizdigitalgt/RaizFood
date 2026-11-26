from collections import Counter
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import delete, func, insert, literal_column, or_, select, update

from app import pos_models as p
from app import restaurant_models as m
from app.auth import DB
from app.db import write_transaction
from app.entitlements import BUSINESS_TZ, today
from app.models import Membership, RolePermission, User, now
from app.operations import restaurant_user
from app.pos_kitchen import authorized_areas, check_area, kitchen_view, update_kitchen
from app.pos_orders import RIGHTS, mutate_order
from app.pos_schemas import Command, CreateOrder, KitchenAction, KitchenConfig, PosConfig
from app.pos_service import (
    account_breakdown,
    begin_order,
    idempotent,
    notify,
    order_lines,
    pos_config,
    rows,
    settings,
    table_name,
    totals,
    waiter_name,
)
from app.restaurant_records import condition, get_row

router = APIRouter(prefix="/restaurants/{slug}", tags=["Punto de venta y cocina"])


def any_permission(request, db, slug, *scopes):
    actor, access = restaurant_user(request, db, slug, None)
    if not set(scopes) & access.permissions:
        raise HTTPException(403, "Permiso insuficiente")
    return actor, access


@router.post("/orders", status_code=201)
def create_order(slug: str, data: CreateOrder, request: Request, db: DB):
    with write_transaction(db):
        actor, access = restaurant_user(request, db, slug, "orders.create")
        return idempotent(
            db,
            access.tenant.id,
            actor,
            "order:create",
            data,
            lambda: begin_order(db, actor, access, data),
        )


@router.post("/orders/{key}/actions")
def order_action(slug: str, key: str, data: Command, request: Request, db: DB):
    with write_transaction(db):
        actor, access = restaurant_user(request, db, slug, RIGHTS[data.op])
        return idempotent(
            db,
            access.tenant.id,
            actor,
            f"order:{key}",
            data,
            lambda: mutate_order(db, actor, access, key, data),
        )


@router.get("/orders")
def orders(
    slug: str,
    request: Request,
    db: DB,
    q: Annotated[str, Query(max_length=100)] = "",
    status: str = "",
    mode: str = "",
    table_id: str = "",
    user_id: str = "",
    active: bool = False,
    after: int | None = None,
    before: int | None = None,
    page: Annotated[int, Query(ge=1, le=10000)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
):
    _, access = restaurant_user(request, db, slug, "orders.view")
    table = p.orders
    tenant = access.tenant.id
    conditions = [condition(table, tenant)]
    for key, value in (
        ("status", status),
        ("mode", mode),
        ("table_id", table_id),
        ("waiter_id", user_id),
    ):
        if value:
            conditions.append(table.c[key] == value)
    if after is not None:
        conditions.append(table.c.created_at >= after)
    if before is not None:
        conditions.append(table.c.created_at <= before)
    if active:
        conditions.extend(
            [table.c.status.in_(p.OPEN), table.c.financial_status.in_(("unpaid", "bill_requested"))]
        )
    q = q.strip().lstrip("#")
    if q.isascii() and q.isdigit() and len(q) <= 12:
        conditions.append(table.c.number == int(q))
    elif q:
        needle = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        conditions.append(
            or_(
                table.c.notes.icontains(q, autoescape=True),
                table.c.contact["name"].as_string().ilike(f"%{needle}%", escape="\\"),
            )
        )
    results = db.execute(
        select(
            *[col for col in table.c if col.name not in {"tenant_id", "contact"}],
            m.tables.c.number.label("table_number"),
            User.name.label("waiter_name"),
        )
        .outerjoin(
            m.tables,
            (m.tables.c.tenant_id == table.c.tenant_id) & (m.tables.c.id == table.c.table_id),
        )
        .outerjoin(User, User.id == table.c.waiter_id)
        .where(*conditions)
        .order_by(table.c.number.desc())
        .offset((page - 1) * size)
        .limit(size)
    ).mappings()
    return {
        "items": [dict(row) for row in results],
        "total": db.scalar(select(func.count()).select_from(table).where(*conditions)),
    }


def detail(db, tenant, key):
    order = get_row(db, p.orders, tenant, key)
    lines = order_lines(db, tenant, key)
    active = [line for line in lines if line["status"] != "cancelled"]
    _, deductions = totals(db, tenant, order, active)
    for line in lines:
        line["discount_cents"] = deductions.get(line["id"], 0)
        line["total_cents"] = line["quantity"] * line["unit_cents"] - line["discount_cents"]
    return {
        **order,
        "lines": lines,
        "accounts": account_breakdown(db, tenant, order, active, deductions),
        "table_name": table_name(db, tenant, order["table_id"]),
        "waiter_name": waiter_name(db, tenant, order["waiter_id"]),
    }


@router.get("/orders/filters")
def order_filters(slug: str, request: Request, db: DB):
    _, access = restaurant_user(request, db, slug, "orders.view")
    tenant = access.tenant.id
    order = p.orders
    waiter_ids = select(order.c.waiter_id).where(condition(order, tenant))
    table_ids = select(order.c.table_id).where(condition(order, tenant))
    staff = db.execute(
        select(User.id, func.coalesce(m.member_profiles.c.display_name, User.name).label("name"))
        .outerjoin(
            m.member_profiles,
            (m.member_profiles.c.tenant_id == tenant) & (m.member_profiles.c.user_id == User.id),
        )
        .where(User.id.in_(waiter_ids))
        .order_by(User.name, User.id)
    ).mappings()
    tables = db.execute(
        select(m.tables.c.id, m.tables.c.name, m.tables.c.number)
        .where(condition(m.tables, tenant), m.tables.c.id.in_(table_ids))
        .order_by(m.tables.c.position, m.tables.c.number)
    ).mappings()
    return {"waiters": [dict(row) for row in staff], "tables": [dict(row) for row in tables]}


@router.get("/orders/{key}")
def read_order(slug: str, key: str, request: Request, db: DB):
    _, access = restaurant_user(request, db, slug, "orders.view")
    return detail(db, access.tenant.id, key)


@router.get("/orders/{key}/history")
def order_history(slug: str, key: str, request: Request, db: DB):
    _, access = restaurant_user(request, db, slug, "orders.view")
    tenant = access.tenant.id
    get_row(db, p.orders, tenant, key)
    history = p.history
    query = (
        select(history, User.name.label("actor_name"))
        .join(User, User.id == history.c.actor_id)
        .where(condition(history, tenant), history.c.order_id == key)
        .order_by(literal_column("order_status_history.rowid").desc())
    )
    return [dict(row) for row in db.execute(query).mappings()]


@router.get("/orders/{key}/bill")
def bill(slug: str, key: str, request: Request, db: DB):
    _, access = restaurant_user(request, db, slug, "receipts.preview")
    tenant = access.tenant.id
    data = detail(db, tenant, key)
    company = db.execute(
        select(m.settings.c.logo_id, m.settings.c.profile).where(m.settings.c.tenant_id == tenant)
    ).first()
    return {
        "restaurant": (company.profile.get("display_name") if company else None)
        or access.tenant.name,
        "logo_id": company.logo_id if company else None,
        "order": data,
        "disclaimer": "CUENTA PRELIMINAR — NO ACREDITA PAGO Y NO ES FACTURA FISCAL.",
    }


@router.get("/orders/{key}/tickets")
def order_tickets(slug: str, key: str, request: Request, db: DB):
    actor, access = any_permission(request, db, slug, "orders.view", "kitchen.tickets.view")
    tenant = access.tenant.id
    get_row(db, p.orders, tenant, key)
    permitted = (
        authorized_areas(db, access, actor) if "orders.view" not in access.permissions else None
    )
    tickets = rows(
        db,
        p.tickets,
        tenant,
        p.tickets.c.order_id == key,
        *([p.tickets.c.preparation_id.in_(permitted)] if permitted is not None else []),
        order_by=(p.tickets.c.number,),
    )
    if permitted is not None and not tickets:
        raise HTTPException(404, "Pedido no disponible")
    return tickets


@router.get("/kitchen")
def kitchen(slug: str, request: Request, db: DB, area: str | None = None):
    actor, access = restaurant_user(request, db, slug, "kitchen.view")
    return {
        **kitchen_view(db, actor, access, area),
        "restaurant": access.tenant.name,
        "warning_minutes": pos_config(db, access.tenant.id).kitchen_warning_minutes,
    }


@router.get("/kitchen/tickets/{key}")
def kitchen_ticket(slug: str, key: str, request: Request, db: DB):
    actor, access = any_permission(request, db, slug, "orders.view", "kitchen.tickets.view")
    tenant = access.tenant.id
    ticket = get_row(db, p.tickets, tenant, key)
    if "orders.view" not in access.permissions:
        check_area(db, access, actor, ticket)
    return {**ticket, "items": rows(db, p.ticket_lines, tenant, p.ticket_lines.c.ticket_id == key)}


@router.post("/kitchen/tickets/{key}/state")
def kitchen_state(slug: str, key: str, data: KitchenAction, request: Request, db: DB):
    with write_transaction(db):
        actor, access = restaurant_user(request, db, slug, "kitchen.update")
        return idempotent(
            db,
            access.tenant.id,
            actor,
            f"kitchen:{key}",
            data,
            lambda: update_kitchen(db, actor, access, key, data),
        )


@router.get("/service-tables")
def service_tables(slug: str, request: Request, db: DB):
    _, access = restaurant_user(request, db, slug, "tables.view")
    tenant = access.tenant.id
    active = p.orders
    joined = select(
        *[col for col in m.tables.c if col.name not in {"tenant_id", "normalized_number"}],
        m.areas.c.name.label("area"),
        m.areas.c.active.label("area_active"),
        active.c.id.label("order_id"),
        active.c.number.label("order_number"),
        active.c.total_cents,
        active.c.status.label("preparation_status"),
        active.c.seated_at,
        func.coalesce(m.member_profiles.c.display_name, User.name).label("waiter_name"),
    ).join(
        m.areas,
        (m.areas.c.tenant_id == m.tables.c.tenant_id) & (m.areas.c.id == m.tables.c.area_id),
    )
    joined = joined.outerjoin(
        active,
        (active.c.tenant_id == m.tables.c.tenant_id)
        & (active.c.table_id == m.tables.c.id)
        & p.active_table,
    ).outerjoin(User, User.id == active.c.waiter_id)
    joined = joined.outerjoin(
        m.member_profiles,
        (m.member_profiles.c.tenant_id == active.c.tenant_id)
        & (m.member_profiles.c.user_id == active.c.waiter_id),
    )
    result = db.execute(
        joined.where(m.tables.c.tenant_id == tenant, m.areas.c.active).order_by(
            m.areas.c.position, m.areas.c.name, m.tables.c.position, m.tables.c.id
        )
    )
    return [dict(row) for row in result.mappings()]


@router.get("/pos/options")
def options(
    slug: str, request: Request, db: DB, customer: Annotated[str, Query(max_length=100)] = ""
):
    actor, access = any_permission(
        request, db, slug, "orders.create", "orders.assign", "settings.manage"
    )
    tenant = access.tenant.id
    users = (
        select(User.id, func.coalesce(m.member_profiles.c.display_name, User.name).label("name"))
        .join(Membership, Membership.user_id == User.id)
        .outerjoin(
            m.member_profiles,
            (m.member_profiles.c.tenant_id == tenant) & (m.member_profiles.c.user_id == User.id),
        )
        .where(
            Membership.tenant_id == tenant,
            Membership.active,
            User.active,
            User.platform_admin.is_(False),
        )
    )

    def with_scope(scope):
        return users.join(
            RolePermission,
            (RolePermission.tenant_id == tenant)
            & (RolePermission.role_id == Membership.role_id)
            & (RolePermission.permission == scope),
        ).order_by(User.name)

    waiter_query = with_scope("orders.create")
    if "orders.assign" not in access.permissions:
        waiter_query = waiter_query.where(User.id == actor.id)
    waiters = [dict(row) for row in db.execute(waiter_query).mappings()]
    station_staff = (
        [dict(row) for row in db.execute(with_scope("kitchen.view")).mappings()]
        if "settings.manage" in access.permissions
        else []
    )
    client_table = m.customers
    clients = db.execute(
        select(client_table.c.id, client_table.c.name)
        .where(
            condition(client_table, tenant),
            client_table.c.active,
            client_table.c.name.icontains(customer, autoescape=True),
        )
        .order_by(client_table.c.name)
        .limit(30)
    ).mappings()
    return {
        "waiters": waiters,
        "station_staff": station_staff,
        "customers": [dict(row) for row in clients]
        if "orders.create" in access.permissions
        else [],
        "mode_options": settings(db, tenant).get("order_modes", ["dine_in"]),
    }


@router.get("/pos/config")
def get_config(slug: str, request: Request, db: DB):
    _, access = restaurant_user(request, db, slug, "settings.manage")
    return pos_config(db, access.tenant.id)


@router.put("/pos/config")
def set_config(slug: str, data: PosConfig, request: Request, db: DB):
    with write_transaction(db):
        actor, access = restaurant_user(request, db, slug, "settings.manage")
        tenant = access.tenant.id
        prefs = {**settings(db, tenant), "pos": data.model_dump()}
        table = m.settings
        if db.scalar(select(table.c.tenant_id).where(table.c.tenant_id == tenant)):
            db.execute(
                update(table)
                .where(table.c.tenant_id == tenant)
                .values(preferences=prefs, updated_at=now())
            )
        else:
            db.execute(insert(table).values(tenant_id=tenant, preferences=prefs))
        notify(db, actor, tenant, "pos.settings.updated", tenant)
    return data


@router.get("/pos/stations/{user_id}")
def stations(slug: str, user_id: str, request: Request, db: DB):
    _, access = restaurant_user(request, db, slug, "settings.manage")
    tenant = access.tenant.id
    if not db.get(Membership, (user_id, tenant)):
        raise HTTPException(404, "Integrante no disponible")
    table = p.kitchen_access
    return {
        "preparation_ids": list(
            db.scalars(
                select(table.c.preparation_id).where(
                    table.c.tenant_id == tenant, table.c.user_id == user_id
                )
            )
        )
    }


@router.put("/pos/stations/{user_id}")
def set_stations(slug: str, user_id: str, data: KitchenConfig, request: Request, db: DB):
    with write_transaction(db):
        actor, access = restaurant_user(request, db, slug, "settings.manage")
        tenant = access.tenant.id
        member = db.get(Membership, (user_id, tenant))
        granted = (
            member
            and member.active
            and db.get(RolePermission, (tenant, member.role_id, "kitchen.view"))
        )
        if not granted:
            raise HTTPException(404, "Integrante de cocina no disponible")
        values = sorted(set(data.preparation_ids))
        for key in values:
            get_row(db, m.preparation, tenant, key)
        table = p.kitchen_access
        db.execute(delete(table).where(table.c.tenant_id == tenant, table.c.user_id == user_id))
        if values:
            db.execute(
                insert(table),
                [
                    {"tenant_id": tenant, "user_id": user_id, "preparation_id": key}
                    for key in values
                ],
            )
        notify(db, actor, tenant, "pos.settings.updated", user_id)
        return {"preparation_ids": values}


@router.get("/operational-summary")
def summary(slug: str, request: Request, db: DB):
    from datetime import datetime, time

    _, access = restaurant_user(request, db, slug, "reports.operational")
    tenant = access.tenant.id
    midnight = int(datetime.combine(today(), time.min, BUSINESS_TZ).timestamp())
    orders = p.orders
    recent_orders = rows(db, orders, tenant, orders.c.created_at >= midnight)
    states = Counter(row["status"] for row in recent_orders)
    active = db.scalar(
        select(func.count())
        .select_from(orders)
        .where(
            condition(orders, tenant),
            orders.c.status.in_(p.OPEN),
            orders.c.financial_status.in_(("unpaid", "bill_requested")),
        )
    )
    tables = dict(
        db.execute(
            select(m.tables.c.state, func.count())
            .join(
                m.areas,
                (m.areas.c.tenant_id == m.tables.c.tenant_id)
                & (m.areas.c.id == m.tables.c.area_id),
            )
            .where(condition(m.tables, tenant), m.areas.c.active)
            .group_by(m.tables.c.state)
        )
        .tuples()
        .all()
    )
    kitchen = rows(
        db,
        p.tickets,
        tenant,
        p.tickets.c.created_at >= midnight,
        p.tickets.c.kind.in_(("initial", "additional")),
    )
    preparation_times = [
        row["ready_at"] - row["started_at"]
        for row in kitchen
        if row["ready_at"] and row["started_at"]
    ]
    areas = Counter(row["snapshot"]["area"] for row in kitchen)
    lines = p.lines
    popular = db.execute(
        select(lines.c.snapshot["name"].as_string(), func.sum(lines.c.quantity))
        .join(orders, (orders.c.tenant_id == lines.c.tenant_id) & (orders.c.id == lines.c.order_id))
        .where(
            condition(lines, tenant),
            orders.c.created_at >= midnight,
            lines.c.status != "cancelled",
            lines.c.status != "new",
        )
        .group_by(lines.c.item_id, lines.c.snapshot["name"].as_string())
        .order_by(func.sum(lines.c.quantity).desc())
        .limit(5)
    )
    return {
        "today": len(recent_orders),
        "active": active,
        "states": {state: states[state] for state in (*p.OPEN, "cancelled")},
        "tables": tables,
        "average_seconds": sum(preparation_times) // len(preparation_times)
        if preparation_times
        else None,
        "stations": [{"name": name, "tickets": count} for name, count in areas.items()],
        "popular": [{"name": name, "quantity": count} for name, count in popular],
    }
