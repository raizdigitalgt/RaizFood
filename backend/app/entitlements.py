from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.commercial_models import OnboardingPlan, PlanVersion, Subscription
from app.models import Plan, Tenant

BUSINESS_TZ = timezone(timedelta(hours=-6))
ACCESS_STATES = {"trial", "active", "grace"}


def today() -> date:
    return datetime.now(BUSINESS_TZ).date()


def status(subscription: Subscription, on: date) -> str:
    if subscription.state in {"suspended", "cancelled"}:
        return subscription.state
    if on < subscription.starts_on:
        return "pending"
    if subscription.trial_until and on < subscription.trial_until:
        return "trial"
    if on >= subscription.ends_on:
        if subscription.state == "active" and on < subscription.ends_on + timedelta(
            days=subscription.grace_days
        ):
            return "grace"
        return "expired"
    return "pending" if subscription.state == "pending" else "active"


def subscription_for(db: Session, tenant_id: str) -> Subscription | None:
    return db.scalar(select(Subscription).where(Subscription.tenant_id == tenant_id))


def contracted_plan(db: Session, tenant: Tenant):
    subscription = subscription_for(db, tenant.id)
    if subscription:
        return db.get(PlanVersion, subscription.plan_version_id)
    initial = db.get(OnboardingPlan, tenant.id)
    return db.get(PlanVersion, initial.plan_version_id) if initial else db.get(Plan, tenant.plan_id)


def operational(db: Session, tenant_id: str) -> bool:
    subscription = subscription_for(db, tenant_id)
    return not subscription or status(subscription, today()) in ACCESS_STATES
