from datetime import date, timedelta

from fastapi import APIRouter, HTTPException, Request, Response
from sqlalchemy import func, select
from sqlalchemy.orm import defer

from app.access import audit, usage
from app.auth import DB
from app.commercial_models import (
    BillingPeriod,
    PlanVersion,
    PlatformNotification,
    PlatformSetting,
    Subscription,
    SubscriptionEvent,
    SubscriptionPayment,
)
from app.commercial_schemas import (
    ActiveInput,
    ChangePlan,
    NewPlan,
    PaymentInput,
    PaymentState,
    PlanInput,
    RenewalInput,
    RestaurantEdit,
    SubscriptionInput,
    SubscriptionState,
    SubscriptionTerms,
)
from app.db import write_transaction
from app.entitlements import status, subscription_for, today
from app.mailer_queue import admin_notice, enqueue
from app.models import AuditLog, Plan, Tenant, User, now
from app.operations import list_team, pack_restaurants
from app.platform_access import platform_user

router = APIRouter(prefix="/platform", tags=["Gestión comercial"])
PLAN_FIELDS = ("name", "monthly_cents", "max_admins", "max_staff", "max_total", "fel_enabled")
DEFAULT_METHODS = ["Efectivo", "Transferencia bancaria", "Depósito bancario"]


def options(db, key, default):
    record = db.get(PlatformSetting, key)
    return record.value if record else default


def save_option(db, key, data):
    record = db.get(PlatformSetting, key)
    if record:
        record.value = data
    else:
        db.add(PlatformSetting(key=key, value=data))


def notify(db, key, kind, message, tenant_id=None):
    if not db.scalar(select(PlatformNotification.id).where(PlatformNotification.key == key)):
        db.add(PlatformNotification(key=key, kind=kind, message=message, tenant_id=tenant_id))
        admin_notice(db, key, message, tenant_id)


def values(obj, fields):
    return {key: getattr(obj, key) for key in fields}


def plan_lookup(db, code, *, require_active=False):
    plan = db.scalar(select(Plan).where(Plan.code == code))
    if not plan or (require_active and not plan.active):
        raise HTTPException(404, "Plan no disponible")
    return plan


def tenant_lookup(db, slug):
    tenant = db.scalar(select(Tenant).where(Tenant.slug == slug))
    if not tenant:
        raise HTTPException(404, "Restaurante no disponible")
    return tenant


def latest_version(db, plan):
    return db.scalar(
        select(PlanVersion)
        .where(PlanVersion.plan_id == plan.id)
        .order_by(PlanVersion.revision.desc())
        .limit(1)
    )


def add_version(db, plan, data: PlanInput, revision: int):
    version = PlanVersion(plan_id=plan.id, revision=revision, **data.model_dump(exclude={"active"}))
    db.add(version)
    db.flush()
    return version


def ensure_version(db, plan):
    version = latest_version(db, plan)
    return version or add_version(db, plan, PlanInput(**values(plan, PLAN_FIELDS)), 1)


def plan_summary(db, plan):
    version = latest_version(db, plan)
    fields = ("description", "annual_cents", "features", "trial_days", "grace_days")
    extra = (
        values(version, fields)
        if version
        else {
            "description": "",
            "annual_cents": None,
            "features": [],
            "trial_days": 0,
            "grace_days": 0,
        }
    )
    return {
        **values(plan, PLAN_FIELDS),
        **extra,
        "code": plan.code,
        "active": plan.active,
        "revision": version.revision if version else 1,
        "restaurants": db.scalar(select(func.count()).where(Tenant.plan_id == plan.id)),
    }


@router.get("/plan-catalog")
def plan_catalog(request: Request, db: DB):
    platform_user(request, db, "plans")
    plans = db.scalars(select(Plan).order_by(Plan.monthly_cents, Plan.code)).all()
    return [plan_summary(db, plan) for plan in plans]


@router.get("/plans/{code}/versions")
def versions(code: str, request: Request, db: DB):
    platform_user(request, db, "plans")
    plan = plan_lookup(db, code)
    return db.scalars(
        select(PlanVersion)
        .where(PlanVersion.plan_id == plan.id)
        .order_by(PlanVersion.revision.desc())
    ).all()


@router.post("/plans", status_code=201)
def new_plan(data: NewPlan, request: Request, db: DB):
    with write_transaction(db):
        actor = platform_user(request, db, "plans")
        if db.scalar(select(Plan.id).where(Plan.code == data.code)):
            raise HTTPException(409, "El código ya existe")
        plan = Plan(code=data.code, active=data.active, **values(data, PLAN_FIELDS))
        db.add(plan)
        db.flush()
        add_version(db, plan, PlanInput(**data.model_dump(exclude={"code"})), 1)
        audit(db, actor, "plan.create", plan.id)
        return plan_summary(db, plan)


@router.put("/plans/{code}")
def edit_plan(code: str, data: PlanInput, request: Request, db: DB):
    with write_transaction(db):
        actor = platform_user(request, db, "plans")
        plan = plan_lookup(db, code)
        previous = ensure_version(db, plan)
        changes = data.model_dump(exclude={"active"})
        if values(previous, changes) != changes:
            add_version(db, plan, data, previous.revision + 1)
            for key, value in values(data, PLAN_FIELDS).items():
                setattr(plan, key, value)
            audit(
                db,
                actor,
                "plan.price"
                if previous.monthly_cents != data.monthly_cents
                or previous.annual_cents != data.annual_cents
                else "plan.version",
                plan.id,
            )
        if plan.active != data.active:
            plan.active = data.active
            audit(db, actor, "plan.activate" if plan.active else "plan.archive", plan.id)
        return plan_summary(db, plan)


@router.delete("/plans/{code}")
def archive_plan(code: str, request: Request, db: DB):
    with write_transaction(db):
        actor = platform_user(request, db, "plans")
        plan = plan_lookup(db, code)
        plan.active = False
        audit(db, actor, "plan.archive", plan.id)
    return {"ok": True}


def record_subscription(db, sub, actor, action):
    revision = db.get(PlanVersion, sub.plan_version_id)
    snapshot = {
        "starts_on": sub.starts_on.isoformat(),
        "ends_on": sub.ends_on.isoformat(),
        "state": status(sub, today()),
        "price_cents": sub.price_cents,
        "discount_cents": sub.discount_cents,
        "grace_days": sub.grace_days,
        "trial_until": sub.trial_until.isoformat() if sub.trial_until else None,
        "plan": revision.name,
        "revision": revision.revision,
    }
    db.add(
        SubscriptionEvent(
            subscription_id=sub.id,
            actor_id=actor.id if actor else None,
            action=action,
            snapshot=snapshot,
        )
    )
    if actor:
        audit(db, actor, f"subscription.{action}", sub.id, sub.tenant_id)


def require_capacity(db, tenant, version):
    used = usage(db, [tenant.id])[tenant.id]
    limits = (version.max_admins, version.max_staff, version.max_total)
    if any(
        used[key] > limit for key, limit in zip(("admins", "staff", "total"), limits, strict=True)
    ):
        raise HTTPException(409, "El equipo supera el cupo del plan seleccionado")


def price_for(version, cycle, discount):
    price = version.annual_cents if cycle == "annual" else version.monthly_cents
    if price is None or discount > price:
        raise HTTPException(422, "El plan no admite este período o descuento")
    return price


def subscription_summary(db, sub, tenant=None):
    tenant = tenant or db.get(Tenant, sub.tenant_id)
    version = db.get(PlanVersion, sub.plan_version_id)
    plan = db.get(Plan, version.plan_id)
    return {
        **values(
            sub,
            (
                "id",
                "starts_on",
                "ends_on",
                "trial_until",
                "grace_days",
                "cycle",
                "price_cents",
                "discount_cents",
            ),
        ),
        "state": status(sub, today()),
        "restaurant": tenant.slug,
        "restaurant_name": tenant.name,
        "plan": version.name,
        "plan_code": plan.code,
        "revision": version.revision,
    }


def subscription_lookup(db, key):
    sub = db.get(Subscription, key)
    if not sub:
        raise HTTPException(404, "Suscripción no disponible")
    return sub


def periods_for(db, sub):
    return db.scalars(
        select(BillingPeriod)
        .where(BillingPeriod.subscription_id == sub.id)
        .order_by(BillingPeriod.starts_on.desc())
    ).all()


def confirmed_total(db, period):
    return db.scalar(
        select(func.coalesce(func.sum(SubscriptionPayment.amount_cents), 0)).where(
            SubscriptionPayment.period_id == period.id,
            SubscriptionPayment.state == "confirmed",
        )
    )


def period_summary(db, period):
    paid = confirmed_total(db, period)
    return {
        **values(period, ("id", "starts_on", "ends_on", "due_cents", "kind", "applied")),
        "paid_cents": paid,
        "balance_cents": period.due_cents - paid,
    }


@router.get("/subscriptions")
def subscriptions(
    request: Request,
    db: DB,
    restaurant: str = "",
    plan: str = "",
    state: str = "",
    start: date | None = None,
    end: date | None = None,
):
    platform_user(request, db, "subscriptions")
    query = (
        select(Subscription, Tenant)
        .join(Tenant)
        .join(PlanVersion, Subscription.plan_version_id == PlanVersion.id)
        .join(Plan, Plan.id == PlanVersion.plan_id)
    )
    if restaurant:
        query = query.where(Tenant.slug == restaurant)
    if plan:
        query = query.where(Plan.code == plan)
    if start:
        query = query.where(Subscription.ends_on >= start)
    if end:
        query = query.where(Subscription.starts_on <= end)
    rows = db.execute(query.order_by(Subscription.ends_on, Tenant.name))
    return [
        subscription_summary(db, sub, tenant)
        for sub, tenant in rows
        if not state or status(sub, today()) == state
    ]


@router.get("/subscriptions/{key}")
def subscription_detail(key: str, request: Request, db: DB):
    platform_user(request, db, "subscriptions")
    sub = subscription_lookup(db, key)
    history = db.scalars(
        select(SubscriptionEvent)
        .where(SubscriptionEvent.subscription_id == sub.id)
        .order_by(SubscriptionEvent.created_at.desc(), SubscriptionEvent.id)
    ).all()
    return {
        **subscription_summary(db, sub),
        "periods": [period_summary(db, period) for period in periods_for(db, sub)],
        "history": history,
    }


@router.post("/subscriptions", status_code=201)
def new_subscription(data: SubscriptionInput, request: Request, db: DB):
    with write_transaction(db):
        actor = platform_user(request, db, "subscriptions")
        tenant = tenant_lookup(db, data.restaurant)
        if subscription_for(db, tenant.id):
            raise HTTPException(409, "El restaurante ya tiene una suscripción")
        plan = plan_lookup(db, data.plan_code, require_active=True)
        version = ensure_version(db, plan)
        require_capacity(db, tenant, version)
        price = price_for(version, data.cycle, data.discount_cents)
        trial = version.trial_days if data.trial_days is None else data.trial_days
        grace = version.grace_days if data.grace_days is None else data.grace_days
        trial_until = min(data.ends_on, data.starts_on + timedelta(days=trial)) if trial else None
        due = price - data.discount_cents
        sub = Subscription(
            tenant_id=tenant.id,
            plan_version_id=version.id,
            starts_on=data.starts_on,
            ends_on=data.ends_on,
            trial_until=trial_until,
            grace_days=grace,
            cycle=data.cycle,
            price_cents=price,
            discount_cents=data.discount_cents,
            state="pending" if data.pending and due else "active",
        )
        tenant.plan_id = plan.id
        db.add(sub)
        db.flush()
        db.add(
            BillingPeriod(
                subscription_id=sub.id,
                plan_version_id=version.id,
                starts_on=data.starts_on,
                ends_on=data.ends_on,
                due_cents=due,
                kind="initial",
                applied=not (data.pending and due),
            )
        )
        record_subscription(db, sub, actor, "create")
        return subscription_summary(db, sub, tenant)


@router.put("/subscriptions/{key}/terms")
def amend_terms(key: str, data: SubscriptionTerms, request: Request, db: DB):
    with write_transaction(db):
        actor = platform_user(request, db, "subscriptions")
        sub = subscription_lookup(db, key)
        if sub.state == "cancelled":
            raise HTTPException(409, "La suscripción está cancelada")
        if any(
            value is not None
            for value in (data.starts_on, data.ends_on, data.trial_days, data.discount_cents)
        ):
            periods = periods_for(db, sub)
            first = next((period for period in periods if period.kind == "initial"), None)
            if (
                not first
                or len(periods) > 1
                or first.plan_version_id != sub.plan_version_id
                or db.scalar(
                    select(SubscriptionPayment.id)
                    .where(SubscriptionPayment.period_id == first.id)
                    .limit(1)
                )
            ):
                raise HTTPException(409, "Conserva el período facturado y configura el siguiente")
            start = data.starts_on or sub.starts_on
            end = data.ends_on or sub.ends_on
            discount = sub.discount_cents if data.discount_cents is None else data.discount_cents
            if (
                not 2000 <= start.year <= end.year <= 2099
                or start >= end
                or discount > sub.price_cents
            ):
                raise HTTPException(422, "Verifica las fechas y el descuento del contrato")
            trial_days = (sub.trial_until - sub.starts_on).days if sub.trial_until else 0
            trial_days = trial_days if data.trial_days is None else data.trial_days
            sub.trial_until = min(end, start + timedelta(days=trial_days)) if trial_days else None
            sub.starts_on, sub.ends_on, sub.discount_cents = start, end, discount
            first.starts_on, first.ends_on, first.due_cents = start, end, sub.price_cents - discount
            if sub.state == "pending" and first.due_cents == 0:
                first.applied = True
                sub.state = "active"
        sub.grace_days = data.grace_days
        record_subscription(db, sub, actor, "terms")
        return subscription_summary(db, sub)


@router.post("/subscriptions/{key}/plan")
def change_plan(key: str, data: ChangePlan, request: Request, db: DB):
    with write_transaction(db):
        actor = platform_user(request, db, "subscriptions")
        sub = subscription_lookup(db, key)
        tenant = db.get(Tenant, sub.tenant_id)
        plan = plan_lookup(db, data.plan_code, require_active=True)
        version = ensure_version(db, plan)
        require_capacity(db, tenant, version)
        if sub.state == "cancelled" or any(
            not period.applied and period.kind == "renewal" for period in periods_for(db, sub)
        ):
            raise HTTPException(409, "Resuelve la renovación abierta antes de cambiar de plan")
        sub.price_cents = price_for(version, data.cycle, data.discount_cents)
        sub.discount_cents = data.discount_cents
        sub.plan_version_id = version.id
        sub.cycle = data.cycle
        tenant.plan_id = plan.id
        record_subscription(db, sub, actor, "plan")
        return subscription_summary(db, sub, tenant)


@router.post("/subscriptions/{key}/state")
def change_state(key: str, data: SubscriptionState, request: Request, db: DB):
    with write_transaction(db):
        actor = platform_user(request, db, "subscriptions")
        sub = subscription_lookup(db, key)
        if sub.state == "cancelled":
            raise HTTPException(409, "La suscripción está cancelada")
        first = next((p for p in periods_for(db, sub) if p.kind == "initial"), None)
        renewed = any(p.applied for p in periods_for(db, sub))
        sub.state = {
            "suspend": "suspended",
            "cancel": "cancelled",
            "resume": "active" if renewed or (first and first.applied) else "pending",
        }[data.action]
        record_subscription(db, sub, actor, data.action)
        return subscription_summary(db, sub)


def apply_period(db, sub, period, actor):
    if period.applied or confirmed_total(db, period) < period.due_cents:
        return
    if sub.state in {"cancelled", "suspended"}:
        raise HTTPException(409, "Reactiva la suscripción antes de aplicar el período")
    if period.kind == "renewal":
        if sub.ends_on != period.starts_on or sub.state == "pending":
            raise HTTPException(409, "El período no se puede aplicar al contrato actual")
        sub.ends_on = period.ends_on
    sub.state = "active"
    period.applied = True
    record_subscription(db, sub, actor, "renew" if period.kind == "renewal" else "activate")


@router.post("/subscriptions/{key}/renewals", status_code=201)
def renew(key: str, data: RenewalInput, request: Request, db: DB):
    with write_transaction(db):
        actor = platform_user(request, db, "subscriptions")
        sub = subscription_lookup(db, key)
        existing = db.scalar(
            select(BillingPeriod).where(
                BillingPeriod.subscription_id == sub.id, BillingPeriod.starts_on == data.starts_on
            )
        )
        if existing and existing.kind == "renewal" and existing.ends_on == data.ends_on:
            return period_summary(db, existing)
        if (
            sub.state != "active"
            or data.starts_on != sub.ends_on
            or not data.starts_on < data.ends_on <= data.starts_on + timedelta(days=366)
            or data.ends_on.year > 2099
        ):
            raise HTTPException(
                409, "La renovación requiere una fecha contigua y una cuenta vigente"
            )
        period = BillingPeriod(
            subscription_id=sub.id,
            plan_version_id=sub.plan_version_id,
            starts_on=data.starts_on,
            ends_on=data.ends_on,
            due_cents=sub.price_cents - sub.discount_cents,
            kind="renewal",
        )
        db.add(period)
        db.flush()
        record_subscription(db, sub, actor, "renewal_requested")
        apply_period(db, sub, period, actor)
        return period_summary(db, period)


def payment_rows(db, restaurant="", state="", start=None, end=None, limit=1000):
    query = (
        select(SubscriptionPayment, BillingPeriod, Tenant, User.name)
        .options(defer(SubscriptionPayment.receipt))
        .join(BillingPeriod, SubscriptionPayment.period_id == BillingPeriod.id)
        .join(Subscription, BillingPeriod.subscription_id == Subscription.id)
        .join(Tenant, Tenant.id == Subscription.tenant_id)
        .join(User, User.id == SubscriptionPayment.actor_id)
    )
    if restaurant:
        query = query.where(Tenant.slug == restaurant)
    if state:
        query = query.where(SubscriptionPayment.state == state)
    if start:
        query = query.where(SubscriptionPayment.paid_on >= start)
    if end:
        query = query.where(SubscriptionPayment.paid_on <= end)
    return db.execute(
        query.order_by(
            SubscriptionPayment.paid_on.desc(), SubscriptionPayment.created_at.desc()
        ).limit(limit)
    ).all()


def payment_summary(payment, period, tenant, actor_name):
    return {
        **values(
            payment, ("id", "amount_cents", "method", "reference", "paid_on", "state", "notes")
        ),
        "restaurant": tenant.slug,
        "restaurant_name": tenant.name,
        "period_id": period.id,
        "starts_on": period.starts_on,
        "ends_on": period.ends_on,
        "actor": actor_name,
        "has_receipt": bool(payment.receipt_type),
    }


@router.get("/payments")
def payments(
    request: Request,
    db: DB,
    restaurant: str = "",
    state: str = "",
    start: date | None = None,
    end: date | None = None,
):
    platform_user(request, db, "payments")
    return [payment_summary(*row) for row in payment_rows(db, restaurant, state, start, end)]


@router.post("/payments", status_code=201)
def add_payment(data: PaymentInput, request: Request, db: DB):
    from app.images import image_data

    platform_user(request, db, "payments")
    db.rollback()
    receipt, receipt_type = image_data(data.receipt) if data.receipt else (None, None)
    with write_transaction(db):
        actor = platform_user(request, db, "payments")
        period = db.get(BillingPeriod, str(data.period_id))
        if not period:
            raise HTTPException(404, "Período no disponible")
        sub = subscription_lookup(db, period.subscription_id)
        tenant = db.get(Tenant, sub.tenant_id)
        existing = db.scalar(
            select(SubscriptionPayment).where(
                SubscriptionPayment.period_id == period.id,
                SubscriptionPayment.request_key == str(data.request_key),
            )
        )
        fields = ("amount_cents", "method", "reference", "paid_on", "notes")
        if existing:
            if values(existing, fields) != values(data, fields) or existing.receipt != receipt:
                raise HTTPException(409, "La clave de la solicitud ya fue utilizada")
            return payment_summary(existing, period, tenant, db.get(User, existing.actor_id).name)
        methods = options(db, "general", {"payment_methods": DEFAULT_METHODS})["payment_methods"]
        if data.method not in methods or not 2000 <= data.paid_on.year <= 2099:
            raise HTTPException(422, "Verifica el método de pago y la fecha")
        if sub.state == "cancelled" or data.amount_cents > period.due_cents - confirmed_total(
            db, period
        ):
            raise HTTPException(409, "El pago supera el saldo o la suscripción está cancelada")
        payment = SubscriptionPayment(
            period_id=period.id,
            actor_id=actor.id,
            request_key=str(data.request_key),
            receipt=receipt,
            receipt_type=receipt_type,
            **values(data, fields),
        )
        db.add(payment)
        db.flush()
        audit(db, actor, "payment.create", payment.id, tenant.id)
        notify(
            db,
            f"payment-pending:{payment.id}",
            "payment_pending",
            f"Pago pendiente de {tenant.name}",
            tenant.id,
        )
        return payment_summary(payment, period, tenant, actor.name)


@router.post("/payments/{key}/state")
def payment_state(key: str, data: PaymentState, request: Request, db: DB):
    with write_transaction(db):
        actor = platform_user(request, db, "payments")
        payment = db.get(SubscriptionPayment, key)
        if not payment:
            raise HTTPException(404, "Pago no disponible")
        period = db.get(BillingPeriod, payment.period_id)
        sub = subscription_lookup(db, period.subscription_id)
        tenant = db.get(Tenant, sub.tenant_id)
        expected, target = {
            "confirm": ("pending", "confirmed"),
            "reject": ("pending", "rejected"),
            "reverse": ("confirmed", "reversed"),
        }[data.action]
        if payment.state == target:
            return payment_summary(payment, period, tenant, db.get(User, payment.actor_id).name)
        if payment.state != expected:
            raise HTTPException(409, "El estado del pago ya cambió")
        if target == "confirmed":
            if (
                sub.state == "cancelled"
                or confirmed_total(db, period) + payment.amount_cents > period.due_cents
            ):
                raise HTTPException(409, "Confirma únicamente pagos dentro del saldo vigente")
            payment.state = target
            db.flush()
            apply_period(db, sub, period, actor)
            enqueue(
                db,
                f"payment:{key}",
                tenant.contact_email,
                "Confirmación de pago de Raíz Food",
                f"Confirmamos el pago de {tenant.name} para el período que inicia "
                f"el {period.starts_on}. Consulta el importe con administración.",
                tenant.id,
            )
            notify(
                db,
                f"payment-confirmed:{payment.id}",
                "payment_confirmed",
                f"Pago confirmado de {tenant.name}",
                tenant.id,
            )
        else:
            if target == "reversed" and period.applied:
                later = any(p.starts_on > period.starts_on for p in periods_for(db, sub))
                if later:
                    raise HTTPException(409, "Resuelve los períodos posteriores antes de revertir")
                if period.kind == "renewal":
                    sub.ends_on = period.starts_on
                elif sub.state == "active":
                    sub.state = "pending"
                period.applied = False
                record_subscription(db, sub, actor, "payment_reversed")
            payment.state = target
        audit(db, actor, f"payment.{data.action}", payment.id, tenant.id)
        return payment_summary(payment, period, tenant, db.get(User, payment.actor_id).name)


@router.get("/payments/{key}/receipt")
def payment_receipt(key: str, request: Request, db: DB):
    platform_user(request, db, "payments")
    payment = db.get(SubscriptionPayment, key)
    if not payment or payment.receipt is None:
        raise HTTPException(404, "Comprobante no disponible")
    return Response(
        payment.receipt,
        media_type=payment.receipt_type,
        headers={"Content-Disposition": 'attachment; filename="comprobante.png"'},
    )


@router.get("/restaurants/{slug}")
def restaurant_detail(slug: str, request: Request, db: DB):
    platform_user(request, db, "restaurants")
    tenant = tenant_lookup(db, slug)
    plan = db.get(Plan, tenant.plan_id)
    sub = subscription_for(db, tenant.id)
    return {
        **pack_restaurants(db, [(tenant, plan)])[0],
        **values(
            tenant,
            (
                "legal_name",
                "tax_id",
                "owner",
                "phone",
                "contact_email",
                "address",
                "notes",
                "logo_url",
            ),
        ),
        "subscription": subscription_summary(db, sub, tenant) if sub else None,
    }


@router.get("/restaurants/{slug}/history")
def restaurant_history(slug: str, request: Request, db: DB):
    platform_user(request, db, "restaurants")
    tenant = tenant_lookup(db, slug)
    sub = subscription_for(db, tenant.id)
    history = (
        db.scalars(
            select(SubscriptionEvent)
            .where(SubscriptionEvent.subscription_id == sub.id)
            .order_by(SubscriptionEvent.created_at.desc())
        ).all()
        if sub
        else []
    )
    activity = db.scalars(
        select(AuditLog)
        .where(AuditLog.tenant_id == tenant.id)
        .order_by(AuditLog.created_at.desc())
        .limit(100)
    ).all()
    return {
        "subscription": history,
        "payments": [payment_summary(*r) for r in payment_rows(db, slug)],
        "activity": activity,
    }


@router.put("/restaurants/{slug}")
def edit_restaurant(slug: str, data: RestaurantEdit, request: Request, db: DB):
    with write_transaction(db):
        actor = platform_user(request, db, "restaurants")
        tenant = tenant_lookup(db, slug)
        previous_email = tenant.contact_email
        for key, value in data.model_dump(mode="json").items():
            setattr(tenant, key, value)
        if tenant.contact_email and tenant.contact_email != previous_email:
            enqueue(
                db,
                f"registration:{tenant.id}:{tenant.contact_email}",
                tenant.contact_email,
                "Registro en Raíz Food",
                f"{tenant.name} está registrado en Raíz Food.",
                tenant.id,
            )
        audit(db, actor, "restaurant.edit", tenant.id, tenant.id)
    return restaurant_detail(slug, request, db)


@router.post("/restaurants/{slug}/active")
def set_restaurant_active(slug: str, data: ActiveInput, request: Request, db: DB):
    with write_transaction(db):
        actor = platform_user(request, db, "restaurants")
        tenant = tenant_lookup(db, slug)
        if tenant.active != data.active:
            tenant.active = data.active
            audit(
                db,
                actor,
                "restaurant.reactivate" if data.active else "restaurant.suspend",
                tenant.id,
                tenant.id,
            )
            if not data.active:
                notify(
                    db,
                    f"restaurant-suspended:{tenant.id}:{now()}",
                    "restaurant_suspended",
                    f"{tenant.name} fue suspendido",
                    tenant.id,
                )
    return restaurant_detail(slug, request, db)


@router.get("/restaurants/{slug}/members")
def restaurant_team(slug: str, request: Request, db: DB):
    platform_user(request, db, "restaurants")
    return list_team(db, tenant_lookup(db, slug).id)
