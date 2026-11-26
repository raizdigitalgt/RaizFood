from fastapi import APIRouter, Request
from sqlalchemy import select

from app.auth import DB
from app.commercial import period_summary, periods_for, subscription_lookup, subscription_summary
from app.commercial_models import Subscription
from app.models import Plan, Tenant
from app.platform_access import platform_user

router = APIRouter(prefix="/platform", tags=["Opciones de gestión"])


@router.get("/subscription-plans")
def subscription_plans(request: Request, db: DB):
    platform_user(request, db, "subscriptions")
    return [
        {"code": plan.code, "name": plan.name}
        for plan in db.scalars(select(Plan).where(Plan.active.is_(True)).order_by(Plan.name))
    ]


@router.get("/subscription-restaurants")
def subscription_restaurants(request: Request, db: DB):
    platform_user(request, db, "subscriptions")
    return [
        {"slug": tenant.slug, "name": tenant.name}
        for tenant in db.scalars(
            select(Tenant)
            .outerjoin(Subscription)
            .where(Tenant.active.is_(True), Subscription.id.is_(None))
            .order_by(Tenant.name)
        )
    ]


@router.get("/payment-subscriptions")
def payment_subscriptions(request: Request, db: DB):
    platform_user(request, db, "payments")
    return [
        subscription_summary(db, sub, tenant)
        for sub, tenant in db.execute(
            select(Subscription, Tenant)
            .join(Tenant)
            .where(Subscription.state != "cancelled")
            .order_by(Tenant.name)
        )
    ]


@router.get("/payment-subscriptions/{key}/periods")
def payment_periods(key: str, request: Request, db: DB):
    platform_user(request, db, "payments")
    return [period_summary(db, period) for period in periods_for(db, subscription_lookup(db, key))]


@router.get("/restaurant-options")
def restaurant_options(request: Request, db: DB):
    platform_user(request, db, "support")
    return [
        {"slug": tenant.slug, "name": tenant.name}
        for tenant in db.scalars(select(Tenant).order_by(Tenant.name))
    ]
