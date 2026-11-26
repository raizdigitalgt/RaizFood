from time import time
from uuid import uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def uuid() -> str:
    return str(uuid4())


def now() -> int:
    return int(time())


class Identified:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid)


class User(Identified, Base):
    __tablename__ = "users"
    email: Mapped[str] = mapped_column(String(254), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    password_hash: Mapped[str]
    platform_admin: Mapped[bool] = mapped_column(default=False)
    platform_role: Mapped[str | None] = mapped_column(String(24))
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[int] = mapped_column(default=now)


class Plan(Identified, Base):
    __tablename__ = "plans"
    __table_args__ = (
        CheckConstraint("monthly_cents >= 0", name="ck_plan_price"),
        CheckConstraint("max_admins >= 1 AND max_staff >= 0", name="ck_plan_role_limits"),
        CheckConstraint("max_total >= max_admins AND max_total >= max_staff", name="ck_plan_total"),
    )
    code: Mapped[str] = mapped_column(String(30), unique=True)
    name: Mapped[str] = mapped_column(String(60))
    monthly_cents: Mapped[int] = mapped_column(BigInteger)
    max_admins: Mapped[int]
    max_staff: Mapped[int]
    max_total: Mapped[int]
    fel_enabled: Mapped[bool]
    active: Mapped[bool] = mapped_column(default=True, server_default="1")


class Tenant(Identified, Base):
    __tablename__ = "tenants"
    slug: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    plan_id: Mapped[str] = mapped_column(ForeignKey("plans.id"), index=True)
    legal_name: Mapped[str] = mapped_column(server_default="")
    tax_id: Mapped[str] = mapped_column(server_default="")
    owner: Mapped[str] = mapped_column(server_default="")
    phone: Mapped[str] = mapped_column(server_default="")
    contact_email: Mapped[str] = mapped_column(server_default="")
    address: Mapped[str] = mapped_column(server_default="")
    notes: Mapped[str] = mapped_column(server_default="")
    logo_url: Mapped[str] = mapped_column(server_default="")
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[int] = mapped_column(default=now)


class Role(Identified, Base):
    __tablename__ = "roles"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_role_tenant_id"),
        UniqueConstraint("tenant_id", "code", name="uq_role_tenant_code"),
    )
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"))
    code: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(80))


class Permission(Base):
    __tablename__ = "permissions"
    code: Mapped[str] = mapped_column(String(64), primary_key=True)


class RolePermission(Base):
    __tablename__ = "role_permissions"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "role_id"], ["roles.tenant_id", "roles.id"]),
    )
    tenant_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    role_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    permission: Mapped[str] = mapped_column(ForeignKey("permissions.code"), primary_key=True)


class Membership(Base):
    __tablename__ = "tenant_memberships"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "role_id"], ["roles.tenant_id", "roles.id"]),
        Index("ix_membership_tenant_role", "tenant_id", "role_id"),
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), primary_key=True)
    role_id: Mapped[str] = mapped_column(String(36))
    active: Mapped[bool] = mapped_column(default=True)


class LoginSession(Identified, Base):
    __tablename__ = "sessions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id", "tenant_id"], ["tenant_memberships.user_id", "tenant_memberships.tenant_id"]
        ),
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    tenant_id: Mapped[str | None] = mapped_column(String(36))
    expires_at: Mapped[int] = mapped_column(index=True)
    revoked: Mapped[bool] = mapped_column(default=False)
    remember: Mapped[bool]
    version: Mapped[int] = mapped_column(default=0)
    mfa_verified: Mapped[bool] = mapped_column(default=False, server_default="0")


class MfaCredential(Base):
    __tablename__ = "mfa_credentials"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    encrypted_seed: Mapped[str]
    last_step: Mapped[int] = mapped_column(default=-1)


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), index=True
    )
    used: Mapped[bool] = mapped_column(default=False)


class LoginLimit(Base):
    __tablename__ = "login_limits"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    attempts: Mapped[int]
    expires_at: Mapped[int] = mapped_column(index=True)


class PasswordReset(Base):
    __tablename__ = "password_reset_tokens"
    digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    expires_at: Mapped[int] = mapped_column(index=True)


class AuditLog(Identified, Base):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_tenant_time", "tenant_id", "created_at"),)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    tenant_id: Mapped[str | None] = mapped_column(ForeignKey("tenants.id"))
    action: Mapped[str] = mapped_column(String(64))
    subject: Mapped[str] = mapped_column(String(36))
    result: Mapped[str] = mapped_column(server_default="ok")
    detail: Mapped[str] = mapped_column(server_default="")
    created_at: Mapped[int] = mapped_column(default=now)
