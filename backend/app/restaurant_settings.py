from fastapi import APIRouter, HTTPException, Request, Response
from sqlalchemy import func, insert, select, update
from sqlalchemy.exc import IntegrityError

from app import restaurant_models as m
from app.access import audit, usage
from app.auth import DB
from app.commercial import notify, payment_rows, plan_summary, subscription_summary
from app.commercial_models import SubscriptionEvent
from app.db import write_transaction
from app.entitlements import contracted_plan, subscription_for, today
from app.models import AuditLog, Plan, User, now
from app.operations import pack_restaurants, restaurant_user
from app.restaurant_records import condition, get_row, scoped_rows
from app.restaurant_schemas import ChangeRequest, SettingsInput

router = APIRouter(prefix="/restaurants/{slug}", tags=["Configuración del restaurante"])
TENANT_FIELDS = ("name", "legal_name", "tax_id", "owner", "phone", "contact_email", "address")
PROFILE_FIELDS = ("department", "municipality", "contact_info", "display_name", "accent")
RELATIONS = {
    "logo_id": m.media_files,
    "cover_id": m.media_files,
    "default_area_id": m.areas,
    "default_preparation_id": m.preparation,
}


def read_settings(db, tenant):
    values = {field: getattr(tenant, field) for field in TENANT_FIELDS}
    settings = (
        db.execute(select(m.settings).where(m.settings.c.tenant_id == tenant.id)).mappings().first()
    )
    if settings:
        values.update(settings["profile"])
        values.update(
            {
                key: value
                for key, value in settings["preferences"].items()
                if key in SettingsInput.model_fields
            }
        )
        values.update({field: settings[field] for field in RELATIONS})
    return SettingsInput.model_validate(values).model_dump(mode="json")


@router.get("/settings")
def settings_view(slug: str, request: Request, db: DB):
    _, access = restaurant_user(request, db, slug, "settings.manage")
    return read_settings(db, access.tenant)


@router.put("/settings")
def settings_update(slug: str, data: SettingsInput, request: Request, db: DB):
    with write_transaction(db):
        actor, access = restaurant_user(request, db, slug, "settings.manage")
        tenant = access.tenant
        updates = data.model_dump(mode="json")
        previous = read_settings(db, tenant)
        for key, table in RELATIONS.items():
            target = updates[key]
            if target:
                row = get_row(db, table, tenant.id, target)
                if row.get("active") is False and target != previous[key]:
                    raise HTTPException(422, "Selecciona un área activa como predeterminada")
        for field in TENANT_FIELDS:
            setattr(tenant, field, updates.pop(field))
        profile = {key: updates.pop(key) for key in PROFILE_FIELDS}
        references = {key: updates.pop(key) for key in RELATIONS}
        updates["days"] = list(dict.fromkeys(updates["days"]))
        updates["order_modes"] = list(dict.fromkeys(updates["order_modes"]))
        saved = db.scalar(
            select(m.settings.c.preferences).where(m.settings.c.tenant_id == tenant.id)
        )
        stored = {
            "profile": profile,
            "preferences": {**(saved or {}), **updates},
            **references,
            "updated_at": now(),
        }
        if saved is not None:
            db.execute(
                update(m.settings).where(m.settings.c.tenant_id == tenant.id).values(**stored)
            )
        else:
            db.execute(insert(m.settings).values(tenant_id=tenant.id, **stored))
        audit(db, actor, "restaurant.settings.edit", tenant.id, tenant.id)
        if references["logo_id"] != previous["logo_id"]:
            audit(db, actor, "restaurant.settings.logo", tenant.id, tenant.id)
        return read_settings(db, tenant)


@router.get("/appearance")
def appearance(slug: str, request: Request, db: DB):
    _, access = restaurant_user(request, db, slug, "dashboard.view")
    settings = read_settings(db, access.tenant)
    return {field: settings[field] for field in ("display_name", "accent", "logo_id", "cover_id")}


@router.get("/editor-defaults")
def editor_defaults(slug: str, request: Request, db: DB):
    _, access = restaurant_user(request, db, slug, None)
    scopes = {"menu.manage", "menu.create", "tables.manage"}
    if not scopes & access.permissions:
        raise HTTPException(403, "Permiso insuficiente")
    values = read_settings(db, access.tenant)
    result = {"default_available": values["default_available"]}
    for key in ("default_area_id", "default_preparation_id"):
        reference = values[key]
        row = get_row(db, RELATIONS[key], access.tenant.id, reference) if reference else {}
        result[key] = reference if row.get("active") else None
    return result


def audit_rows(db, tenant_id, q="", action="", page=1, size=20, start=None, end=None):
    filters = [AuditLog.tenant_id == tenant_id]
    if q:
        filters.append(
            AuditLog.action.icontains(q, autoescape=True)
            | User.name.icontains(q, autoescape=True)
            | AuditLog.subject.icontains(q, autoescape=True)
        )
    if action:
        filters.append(AuditLog.action == action)
    if start is not None:
        filters.append(AuditLog.created_at >= start)
    if end is not None:
        filters.append(AuditLog.created_at <= end)
    source = (
        select(AuditLog, User.name).outerjoin(User, User.id == AuditLog.user_id).where(*filters)
    )
    rows = db.execute(
        source.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .offset((page - 1) * size)
        .limit(size)
    )
    count = db.scalar(select(func.count()).select_from(source.subquery()))
    return {
        "items": [
            {
                "id": row.id,
                "action": row.action,
                "subject": row.subject,
                "created_at": row.created_at,
                "user": name or "Sistema",
                "result": row.result,
                "detail": row.detail,
            }
            for row, name in rows
        ],
        "total": count,
    }


@router.get("/audit")
def audit_view(
    slug: str,
    request: Request,
    db: DB,
    q: str = "",
    action: str = "",
    page: int = 1,
    start: int | None = None,
    end: int | None = None,
):
    _, access = restaurant_user(request, db, slug, "audit.view")
    if len(q) > 100 or len(action) > 100 or not 1 <= page <= 10000:
        raise HTTPException(422, "Filtro inválido")
    return audit_rows(db, access.tenant.id, q, action, page, start=start, end=end)


def subscription_data(db, tenant):
    contract = contracted_plan(db, tenant)
    sub = subscription_for(db, tenant.id)
    summary = subscription_summary(db, sub, tenant) if sub else None
    if summary:
        summary["remaining_days"] = max(0, (sub.ends_on - today()).days)
    plan = db.get(Plan, tenant.plan_id)
    limits = {key: getattr(contract, key) for key in ("max_admins", "max_staff", "max_total")}
    return {
        "subscription": summary,
        "plan": {
            "name": contract.name,
            "code": plan.code,
            "monthly_cents": contract.monthly_cents,
            "fel_enabled": contract.fel_enabled,
            **limits,
            "features": getattr(contract, "features", []),
        },
        "usage": usage(db, [tenant.id])[tenant.id],
    }


@router.get("/subscription")
def subscription_view(slug: str, request: Request, db: DB):
    _, access = restaurant_user(request, db, slug, "subscription.view")
    tenant = access.tenant
    data = subscription_data(db, tenant)
    sub = subscription_for(db, tenant.id)
    history = []
    if sub:
        history = [
            {
                "id": event.id,
                "action": event.action,
                "snapshot": event.snapshot,
                "created_at": event.created_at,
            }
            for event in db.scalars(
                select(SubscriptionEvent)
                .where(SubscriptionEvent.subscription_id == sub.id)
                .order_by(SubscriptionEvent.created_at.desc(), SubscriptionEvent.id)
                .limit(100)
            )
        ]
    receipts = [
        {
            "id": payment.id,
            "amount_cents": payment.amount_cents,
            "state": payment.state,
            "method": payment.method,
            "paid_on": payment.paid_on,
            "reference": payment.reference,
            "starts_on": period.starts_on,
            "ends_on": period.ends_on,
        }
        for payment, period, _, _ in payment_rows(db, tenant.slug, limit=100)
    ]
    catalog = [
        plan_summary(db, plan)
        for plan in db.scalars(
            select(Plan).where(Plan.active.is_(True)).order_by(Plan.monthly_cents)
        )
    ]
    for plan in catalog:
        plan.pop("restaurants", None)
    pending = [
        dict(row)
        for row in db.execute(
            scoped_rows(db, m.change_requests, tenant.id)
            .order_by(m.change_requests.c.created_at.desc())
            .limit(40)
        ).mappings()
    ]
    return {**data, "history": history, "payments": receipts, "plans": catalog, "requests": pending}


@router.post("/subscription/requests", status_code=201)
def request_plan(slug: str, data: ChangeRequest, request: Request, db: DB):
    try:
        with write_transaction(db):
            actor, access = restaurant_user(request, db, slug, "subscription.view")
            tenant = access.tenant
            plan = db.scalar(select(Plan).where(Plan.code == data.plan_code, Plan.active.is_(True)))
            if not plan or plan.id == tenant.plan_id:
                raise HTTPException(422, "Selecciona otro plan disponible")
            key = db.execute(
                insert(m.change_requests).values(
                    tenant_id=tenant.id,
                    plan_id=plan.id,
                    notes=data.notes,
                    actor_id=actor.id,
                )
            ).inserted_primary_key[0]
            notify(
                db,
                f"plan-request:{key}",
                "plan_change_requested",
                f"{tenant.name} solicitó el plan {plan.name}",
                tenant.id,
            )
            audit(db, actor, "restaurant.subscription.request", key, tenant.id)
            return get_row(db, m.change_requests, tenant.id, key)
    except IntegrityError as error:
        raise HTTPException(409, "Ya tienes una solicitud pendiente") from error


@router.delete("/subscription/requests/{key}", status_code=204)
def cancel_request(slug: str, key: str, request: Request, db: DB):
    with write_transaction(db):
        actor, access = restaurant_user(request, db, slug, "subscription.view")
        tenant = access.tenant.id
        row = get_row(db, m.change_requests, tenant, key)
        if row["status"] != "pending":
            raise HTTPException(409, "La solicitud ya fue atendida")
        db.execute(
            update(m.change_requests)
            .where(condition(m.change_requests, tenant, key))
            .values(status="cancelled", updated_at=now())
        )
        audit(db, actor, "restaurant.subscription.cancel_request", key, tenant)
    return Response(status_code=204)


@router.get("/overview")
def overview(slug: str, request: Request, db: DB):
    _, access = restaurant_user(request, db, slug, "dashboard.view")
    tenant = access.tenant
    basics = pack_restaurants(db, [(tenant, db.get(Plan, tenant.plan_id))])[0]
    counts = {}
    for name, table in (
        ("items", m.items),
        ("categories", m.categories),
        ("tables", m.tables),
        ("areas", m.areas),
        ("customers", m.customers),
    ):
        counts[name] = db.scalar(
            select(func.count()).select_from(table).where(condition(table, tenant.id))
        )
    counts["available"] = db.scalar(
        select(func.count())
        .select_from(m.items)
        .join(
            m.categories,
            (m.items.c.tenant_id == m.categories.c.tenant_id)
            & (m.items.c.category_id == m.categories.c.id),
        )
        .where(
            condition(m.items, tenant.id),
            m.items.c.active,
            m.items.c.available,
            m.categories.c.active,
        )
    )
    counts["inactive"] = db.scalar(
        select(func.count())
        .select_from(m.items)
        .where(condition(m.items, tenant.id), m.items.c.active.is_(False))
    )
    allowed_activity = "audit.view" in access.permissions
    subscription = (
        subscription_data(db, tenant)["subscription"]
        if "subscription.view" in access.permissions
        else None
    )
    return {
        **basics,
        "counts": counts,
        "subscription": subscription,
        "activity": audit_rows(db, tenant.id, size=8)["items"] if allowed_activity else [],
    }
