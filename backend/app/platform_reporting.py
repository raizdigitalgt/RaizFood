import csv
from collections import Counter
from datetime import date, datetime, timedelta
from io import BytesIO, StringIO

from fastapi import APIRouter, HTTPException, Request, Response
from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import func, select

from app.access import audit
from app.auth import DB
from app.commercial import notify, payment_rows, payment_summary, tenant_lookup, values
from app.commercial_models import (
    BackupRecord,
    BillingPeriod,
    NotificationRead,
    PlatformNotification,
    Subscription,
    SubscriptionPayment,
    SupportEvent,
    SupportTicket,
)
from app.commercial_schemas import TicketEdit, TicketInput
from app.db import write_transaction
from app.entitlements import BUSINESS_TZ, contracted_plan, status, today
from app.mailer_queue import enqueue
from app.models import AuditLog, Plan, Tenant, User
from app.platform_access import platform_grants, platform_user

router = APIRouter(prefix="/platform", tags=["Reportes y seguimiento"])


def metrics(db, start=None, end=None):
    on = today()
    start = start or on.replace(day=1)
    end = end or on
    if start > end or end - start > timedelta(days=3660) or start.year < 2000 or end.year > 2099:
        raise HTTPException(422, "Selecciona un rango de fechas válido")
    tenants = db.scalars(select(Tenant)).all()
    subs = db.scalars(select(Subscription)).all()
    plans = {plan.id: plan for plan in db.scalars(select(Plan))}
    states = Counter(status(sub, on) for sub in subs)
    by_plan = Counter(plans[tenant.plan_id].name for tenant in tenants)
    active_tenants = {tenant.id for tenant in tenants if tenant.active}
    accepted = [
        sub
        for sub in subs
        if sub.tenant_id in active_tenants and status(sub, on) in {"active", "grace"}
    ]
    annual = sum(
        (sub.price_cents - sub.discount_cents) * (1 if sub.cycle == "annual" else 12)
        for sub in accepted
    )
    payments = db.execute(
        select(
            SubscriptionPayment.paid_on, SubscriptionPayment.amount_cents, SubscriptionPayment.state
        ).where(SubscriptionPayment.paid_on.between(min(start, on.replace(day=1)), max(on, end)))
    ).all()
    buckets = {}
    month = start.replace(day=1)
    while month <= end:
        key = month.strftime("%Y-%m")
        buckets[key] = {"month": key, "income_cents": 0, "payments": 0, "restaurants": 0}
        month = (month.replace(day=28) + timedelta(days=4)).replace(day=1)
    collected = received_month = 0
    for paid, amount, state in payments:
        if state == "confirmed":
            if start <= paid <= end:
                bucket = buckets[paid.strftime("%Y-%m")]
                bucket["income_cents"] += amount
                bucket["payments"] += 1
                collected += amount
            if on.replace(day=1) <= paid <= on:
                received_month += 1
    for tenant in tenants:
        created = datetime.fromtimestamp(tenant.created_at, BUSINESS_TZ).date()
        if start <= created <= end:
            buckets[created.strftime("%Y-%m")]["restaurants"] += 1
    pending_periods = db.execute(
        select(
            BillingPeriod.due_cents, func.coalesce(func.sum(SubscriptionPayment.amount_cents), 0)
        )
        .join(Subscription, BillingPeriod.subscription_id == Subscription.id)
        .outerjoin(
            SubscriptionPayment,
            (SubscriptionPayment.period_id == BillingPeriod.id)
            & (SubscriptionPayment.state == "confirmed"),
        )
        .where(Subscription.state != "cancelled")
        .group_by(BillingPeriod.id)
    ).all()
    backup = db.scalar(select(BackupRecord).order_by(BackupRecord.created_at.desc()).limit(1))
    activity = db.execute(
        select(AuditLog, User.name)
        .join(User, User.id == AuditLog.user_id)
        .order_by(AuditLog.created_at.desc())
        .limit(8)
    ).all()
    return {
        "range": {"start": start, "end": end},
        "restaurants": len(tenants),
        "catalog_plans": sum(plan.active for plan in plans.values()),
        "recent_restaurants": [
            {
                "slug": tenant.slug,
                "name": tenant.name,
                "created_at": tenant.created_at,
                "active": tenant.active,
                "plan": plans[tenant.plan_id].name,
            }
            for tenant in sorted(tenants, key=lambda row: (-row.created_at, row.id))[:6]
        ],
        "active_restaurants": len(active_tenants),
        "suspended_restaurants": len(tenants) - len(active_tenants),
        "trial_restaurants": sum(
            sub.tenant_id in active_tenants and status(sub, on) == "trial" for sub in subs
        ),
        "registered_users": db.scalar(select(func.count()).select_from(User)),
        "subscription_states": dict(states),
        "expiring": sum(
            status(sub, on) in {"active", "trial"} and on <= sub.ends_on <= on + timedelta(days=7)
            for sub in subs
        ),
        "monthly_recurring_cents": (annual + 6) // 12,
        "annual_projected_cents": annual,
        "collected_cents": collected,
        "outstanding_cents": sum(due - paid for due, paid in pending_periods),
        "received_month": received_month,
        "pending_payments": db.scalar(
            select(func.count()).where(SubscriptionPayment.state == "pending")
        ),
        "basic_restaurants": sum(plans[tenant.plan_id].code == "basic" for tenant in tenants),
        "pro_restaurants": sum(plans[tenant.plan_id].code == "pro" for tenant in tenants),
        "plan_distribution": [
            {"plan": name, "count": count} for name, count in sorted(by_plan.items())
        ],
        "series": list(buckets.values()),
        "backup": backup,
        "activity": [
            {**values(entry, ("id", "action", "created_at", "result")), "user": user}
            for entry, user in activity
        ],
    }


@router.get("/commercial-summary")
def dashboard(request: Request, db: DB, start: date | None = None, end: date | None = None):
    actor = platform_user(request, db)
    return visible_summary(db, actor, start, end)


@router.get("/reports")
def reports(request: Request, db: DB, start: date | None = None, end: date | None = None):
    actor = platform_user(request, db, "reports")
    return visible_summary(db, actor, start, end)


def visible_summary(db, actor, start, end):
    scopes = platform_grants(db, actor)
    data = metrics(db, start, end)
    if "restaurants" not in scopes:
        data["recent_restaurants"] = []
    if "audit" not in scopes:
        data["activity"] = []
    if "backups" not in scopes:
        data["backup"] = None
    return data


def csv_cell(value):
    raw = str(value)
    return "'" + raw if raw.lstrip().startswith(("=", "+", "-", "@")) else raw


@router.get("/payments-export/{file_format}")
def export_payments(
    file_format: str,
    request: Request,
    db: DB,
    restaurant: str = "",
    state: str = "",
    start: date | None = None,
    end: date | None = None,
):
    platform_user(request, db, "payments")
    if file_format not in {"csv", "pdf"}:
        raise HTTPException(404, "Formato no disponible")
    limit = 1001 if file_format == "pdf" else None
    rows = [payment_summary(*row) for row in payment_rows(db, restaurant, state, start, end, limit)]
    if file_format == "pdf" and len(rows) > 1000:
        raise HTTPException(422, "Acota las fechas del PDF o descarga todo en CSV")
    db.rollback()
    headings = ["Restaurante", "Fecha", "Monto GTQ", "Metodo", "Referencia", "Estado"]
    export = [
        [
            row["restaurant_name"],
            row["paid_on"],
            f"{row['amount_cents'] // 100}.{row['amount_cents'] % 100:02d}",
            row["method"],
            row["reference"],
            row["state"],
        ]
        for row in rows
    ]
    if file_format == "csv":
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(headings)
        writer.writerows([csv_cell(value) for value in row] for row in export)
        return Response(
            output.getvalue().encode("utf-8-sig"),
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="pagos.csv"'},
        )
    pages = []
    batch = 30
    font = ImageFont.load_default(size=13)
    for first in range(0, max(1, len(export)), batch):
        sheet = Image.new("RGB", (842, 595), "white")
        draw = ImageDraw.Draw(sheet)
        draw.text(
            (28, 20),
            "Raíz Food · Pagos de suscripción",
            fill="black",
            font=ImageFont.load_default(size=19),
        )
        draw.text((740, 24), str(first // batch + 1), fill="black", font=font)
        for line, row in enumerate([headings, *export[first : first + batch]]):
            for x, cell, width in zip(
                (28, 216, 318, 410, 572, 720), row, (24, 12, 13, 21, 18, 14), strict=True
            ):
                draw.text((x, 58 + line * 16), str(cell)[:width], fill="black", font=font)
        pages.append(sheet)
    buffer = BytesIO()
    pages[0].save(buffer, "PDF", save_all=True, append_images=pages[1:])
    return Response(
        buffer.getvalue(),
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="pagos.pdf"'},
    )


@router.get("/notifications")
def notifications(request: Request, db: DB):
    actor = platform_user(request, db, "notifications")
    query = (
        select(PlatformNotification, NotificationRead.user_id)
        .outerjoin(
            NotificationRead,
            (NotificationRead.notification_id == PlatformNotification.id)
            & (NotificationRead.user_id == actor.id),
        )
        .order_by(PlatformNotification.created_at.desc(), PlatformNotification.id)
        .limit(300)
    )
    return [
        {**values(row, ("id", "kind", "message", "created_at")), "read": bool(seen)}
        for row, seen in db.execute(query)
    ]


@router.post("/notifications/{key}/read")
def mark_read(key: str, request: Request, db: DB):
    with write_transaction(db):
        actor = platform_user(request, db, "notifications")
        if not db.get(PlatformNotification, key):
            raise HTTPException(404, "Notificación no disponible")
        if not db.get(NotificationRead, (key, actor.id)):
            db.add(NotificationRead(notification_id=key, user_id=actor.id))
    return {"ok": True}


def expiry_notifications(db):
    on = today()
    query = (
        select(Subscription, Tenant)
        .join(Tenant)
        .where(
            Subscription.ends_on <= on + timedelta(days=7),
            Subscription.state.not_in({"suspended", "cancelled"}),
        )
    )
    count = 0
    for sub, tenant in db.execute(query):
        state = status(sub, on)
        if state in {"active", "trial"} and sub.ends_on >= on:
            kind, description = "subscription_expiring", f"{tenant.name} vence el {sub.ends_on}"
        elif state == "expired":
            kind, description = (
                "subscription_expired",
                f"{tenant.name} tiene una suscripción vencida",
            )
        else:
            continue
        key = f"{kind}:{sub.id}:{sub.ends_on}"
        notify(db, key, kind, description, tenant.id)
        enqueue(db, key, tenant.contact_email, "Vigencia de Raíz Food", description, tenant.id)
        count += 1
    return count


def ticket_details(db, ticket):
    tenant = db.get(Tenant, ticket.tenant_id)
    owner = db.get(User, ticket.assignee_id) if ticket.assignee_id else None
    return {
        **values(
            ticket,
            ("id", "subject", "description", "priority", "state", "assignee_id", "created_at"),
        ),
        "restaurant_name": tenant.name,
        "restaurant": tenant.slug,
        "assignee": owner.name if owner else None,
    }


@router.get("/support")
def tickets(request: Request, db: DB, state: str = ""):
    platform_user(request, db, "support")
    query = select(SupportTicket)
    if state:
        query = query.where(SupportTicket.state == state)
    return [
        ticket_details(db, ticket)
        for ticket in db.scalars(query.order_by(SupportTicket.created_at.desc()).limit(300))
    ]


@router.get("/support-assignees")
def assignees(request: Request, db: DB):
    platform_user(request, db, "support")
    return [
        {"id": user.id, "name": user.name}
        for user in db.scalars(
            select(User)
            .where(User.platform_admin.is_(True), User.active.is_(True))
            .order_by(User.name)
        )
    ]


@router.post("/support", status_code=201)
def new_ticket(data: TicketInput, request: Request, db: DB):
    with write_transaction(db):
        actor = platform_user(request, db, "support")
        tenant = tenant_lookup(db, data.restaurant)
        ticket = SupportTicket(
            tenant_id=tenant.id, state="open", **data.model_dump(exclude={"restaurant"})
        )
        db.add(ticket)
        db.flush()
        db.add(
            SupportEvent(
                ticket_id=ticket.id,
                actor_id=actor.id,
                message="Solicitud registrada",
                state=ticket.state,
            )
        )
        notify(
            db,
            f"ticket:{ticket.id}",
            "support_request",
            f"{tenant.name}: {ticket.subject}",
            tenant.id,
        )
        audit(db, actor, "support.create", ticket.id, tenant.id)
        return ticket_details(db, ticket)


@router.get("/support/{key}")
def ticket_detail(key: str, request: Request, db: DB):
    platform_user(request, db, "support")
    ticket = db.get(SupportTicket, key)
    if not ticket:
        raise HTTPException(404, "Solicitud no disponible")
    history = db.execute(
        select(SupportEvent, User.name)
        .join(User, User.id == SupportEvent.actor_id)
        .where(SupportEvent.ticket_id == key)
        .order_by(SupportEvent.created_at, SupportEvent.id)
    ).all()
    return {
        **ticket_details(db, ticket),
        "history": [
            {**values(event, ("id", "message", "state", "assignee_id", "created_at")), "user": user}
            for event, user in history
        ],
    }


@router.put("/support/{key}")
def edit_ticket(key: str, data: TicketEdit, request: Request, db: DB):
    with write_transaction(db):
        actor = platform_user(request, db, "support")
        ticket = db.get(SupportTicket, key)
        if not ticket:
            raise HTTPException(404, "Solicitud no disponible")
        assignee = db.get(User, str(data.assignee_id)) if data.assignee_id else None
        if data.assignee_id and (
            not assignee or not assignee.active or not assignee.platform_admin
        ):
            raise HTTPException(422, "Responsable no disponible")
        ticket.state = data.state
        ticket.assignee_id = assignee.id if assignee else None
        db.add(
            SupportEvent(
                ticket_id=key,
                actor_id=actor.id,
                state=ticket.state,
                assignee_id=ticket.assignee_id,
                message=data.message,
            )
        )
        audit(db, actor, "support.update", key, ticket.tenant_id)
    return ticket_detail(key, request, db)


@router.get("/fel")
def fiscal_preparation(request: Request, db: DB):
    platform_user(request, db, "fel")
    tenants = db.scalars(select(Tenant).order_by(Tenant.name)).all()
    result = []
    for tenant in tenants:
        if contracted_plan(db, tenant).fel_enabled:
            result.append(
                {
                    "slug": tenant.slug,
                    "name": tenant.name,
                    "active": tenant.active,
                    "plan": db.get(Plan, tenant.plan_id).name,
                }
            )
    return {"integration": "Fase 7 · Digifact pendiente", "restaurants": result}
