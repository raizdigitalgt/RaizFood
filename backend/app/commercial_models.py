from datetime import date

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    LargeBinary,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models import Identified, now


class PlanVersion(Identified, Base):
    __tablename__ = "plan_versions"
    __table_args__ = (UniqueConstraint("plan_id", "revision"),)
    plan_id: Mapped[str] = mapped_column(ForeignKey("plans.id"), index=True)
    revision: Mapped[int]
    name: Mapped[str]
    description: Mapped[str]
    monthly_cents: Mapped[int] = mapped_column(BigInteger)
    annual_cents: Mapped[int | None] = mapped_column(BigInteger)
    max_admins: Mapped[int]
    max_staff: Mapped[int]
    max_total: Mapped[int]
    fel_enabled: Mapped[bool]
    features: Mapped[list[str]] = mapped_column(JSON)
    trial_days: Mapped[int]
    grace_days: Mapped[int]
    created_at: Mapped[int] = mapped_column(default=now)


class Subscription(Identified, Base):
    __tablename__ = "subscriptions"
    __table_args__ = (
        UniqueConstraint("id", "tenant_id"),
        CheckConstraint("starts_on < ends_on", name="ck_subscription_dates"),
    )
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), unique=True)
    plan_version_id: Mapped[str] = mapped_column(ForeignKey("plan_versions.id"), index=True)
    starts_on: Mapped[date]
    ends_on: Mapped[date] = mapped_column(index=True)
    trial_until: Mapped[date | None]
    grace_days: Mapped[int]
    cycle: Mapped[str] = mapped_column(String(8))
    price_cents: Mapped[int] = mapped_column(BigInteger)
    discount_cents: Mapped[int] = mapped_column(BigInteger)
    state: Mapped[str] = mapped_column(String(16), index=True)
    created_at: Mapped[int] = mapped_column(default=now)


class SubscriptionEvent(Identified, Base):
    __tablename__ = "subscription_events"
    subscription_id: Mapped[str] = mapped_column(ForeignKey("subscriptions.id"), index=True)
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str]
    snapshot: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[int] = mapped_column(default=now)


class BillingPeriod(Identified, Base):
    __tablename__ = "billing_periods"
    __table_args__ = (
        UniqueConstraint("subscription_id", "starts_on"),
        CheckConstraint("starts_on < ends_on AND due_cents >= 0", name="ck_billing_period"),
    )
    subscription_id: Mapped[str] = mapped_column(ForeignKey("subscriptions.id"), index=True)
    plan_version_id: Mapped[str] = mapped_column(ForeignKey("plan_versions.id"))
    starts_on: Mapped[date]
    ends_on: Mapped[date]
    due_cents: Mapped[int] = mapped_column(BigInteger)
    kind: Mapped[str]
    applied: Mapped[bool] = mapped_column(default=False)


class SubscriptionPayment(Identified, Base):
    __tablename__ = "subscription_payments"
    __table_args__ = (
        UniqueConstraint("period_id", "request_key"),
        CheckConstraint("amount_cents > 0", name="ck_subscription_payment_amount"),
    )
    period_id: Mapped[str] = mapped_column(ForeignKey("billing_periods.id"), index=True)
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    method: Mapped[str]
    reference: Mapped[str]
    paid_on: Mapped[date] = mapped_column(index=True)
    state: Mapped[str] = mapped_column(index=True, default="pending")
    notes: Mapped[str]
    request_key: Mapped[str]
    receipt: Mapped[bytes | None] = mapped_column(LargeBinary)
    receipt_type: Mapped[str | None]
    created_at: Mapped[int] = mapped_column(default=now)


class PlatformSetting(Base):
    __tablename__ = "platform_settings"
    key: Mapped[str] = mapped_column(primary_key=True)
    value: Mapped[dict] = mapped_column(JSON)


class PlatformAsset(Base):
    __tablename__ = "platform_assets"
    key: Mapped[str] = mapped_column(primary_key=True)
    content: Mapped[bytes] = mapped_column(LargeBinary)
    content_type: Mapped[str]


class Invitation(Base):
    __tablename__ = "invitations"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "role_id"], ["roles.tenant_id", "roles.id"]),
    )
    digest: Mapped[str] = mapped_column(primary_key=True)
    email: Mapped[str]
    name: Mapped[str]
    tenant_id: Mapped[str | None] = mapped_column(ForeignKey("tenants.id"))
    role_id: Mapped[str | None]
    platform_role: Mapped[str | None]
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    expires_at: Mapped[int]
    accepted_at: Mapped[int | None]
    cancelled_at: Mapped[int | None]


class PlatformNotification(Identified, Base):
    __tablename__ = "platform_notifications"
    key: Mapped[str] = mapped_column(unique=True)
    kind: Mapped[str]
    message: Mapped[str]
    tenant_id: Mapped[str | None] = mapped_column(ForeignKey("tenants.id"))
    created_at: Mapped[int] = mapped_column(default=now)


class NotificationRead(Base):
    __tablename__ = "notification_reads"
    notification_id: Mapped[str] = mapped_column(
        ForeignKey("platform_notifications.id"), primary_key=True
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)


class SupportTicket(Identified, Base):
    __tablename__ = "support_tickets"
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    subject: Mapped[str]
    description: Mapped[str]
    priority: Mapped[str]
    state: Mapped[str]
    assignee_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[int] = mapped_column(default=now)


class SupportEvent(Identified, Base):
    __tablename__ = "support_events"
    ticket_id: Mapped[str] = mapped_column(ForeignKey("support_tickets.id"), index=True)
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    message: Mapped[str]
    state: Mapped[str]
    assignee_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[int] = mapped_column(default=now)


class BackupRecord(Identified, Base):
    __tablename__ = "backup_records"
    filename: Mapped[str] = mapped_column(unique=True)
    size: Mapped[int] = mapped_column(BigInteger)
    checksum: Mapped[str]
    revision: Mapped[str]
    state: Mapped[str]
    created_at: Mapped[int] = mapped_column(default=now)


class MailJob(Base):
    __tablename__ = "mail_jobs"
    key: Mapped[str] = mapped_column(primary_key=True)
    recipient: Mapped[str]
    subject: Mapped[str]
    body: Mapped[str]
    tenant_id: Mapped[str | None] = mapped_column(ForeignKey("tenants.id"))
    state: Mapped[str] = mapped_column(default="pending", index=True)
    created_at: Mapped[int] = mapped_column(default=now)
    finished_at: Mapped[int | None]


class OnboardingPlan(Base):
    __tablename__ = "onboarding_plans"
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), primary_key=True)
    plan_version_id: Mapped[str] = mapped_column(ForeignKey("plan_versions.id"))
