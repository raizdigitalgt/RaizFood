from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, HttpUrl, StringConstraints, model_validator

from app.schemas import Name, Password, Slug

Cents = Annotated[int, Field(ge=0, le=10**12)]
Short = Annotated[str, StringConstraints(strip_whitespace=True, max_length=255)]
Notes = Annotated[str, StringConstraints(strip_whitespace=True, max_length=4000)]
Days = Annotated[int, Field(ge=0, le=90)]


class PlanInput(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=60)]
    description: Notes = ""
    monthly_cents: Cents
    annual_cents: Cents | None = None
    max_admins: Annotated[int, Field(ge=1, le=10000)]
    max_staff: Annotated[int, Field(ge=0, le=10000)]
    max_total: Annotated[int, Field(ge=1, le=20000)]
    fel_enabled: bool = False
    features: Annotated[list[Short], Field(max_length=50)] = []
    trial_days: Days = 0
    grace_days: Days = 0
    active: bool = True

    @model_validator(mode="after")
    def coherent(self):
        if (
            not max(self.max_admins, self.max_staff)
            <= self.max_total
            <= self.max_admins + self.max_staff
        ):
            raise ValueError("El cupo total debe ser coherente con los cupos por rol")
        return self


class NewPlan(PlanInput):
    code: Annotated[Slug, Field(max_length=30)]


class RestaurantEdit(BaseModel):
    name: Name
    legal_name: Short = ""
    tax_id: Short = ""
    owner: Short = ""
    phone: Short = ""
    contact_email: EmailStr | Literal[""] = ""
    address: Notes = ""
    notes: Notes = ""
    logo_url: HttpUrl | Literal[""] = ""


class ActiveInput(BaseModel):
    active: bool


class SubscriptionInput(BaseModel):
    restaurant: Slug
    plan_code: Slug
    starts_on: date
    ends_on: date
    cycle: Literal["monthly", "annual"] = "monthly"
    discount_cents: Cents = 0
    trial_days: Days | None = None
    grace_days: Days | None = None
    pending: bool = True

    @model_validator(mode="after")
    def valid_dates(self):
        if self.starts_on >= self.ends_on or self.ends_on.year > 2099 or self.starts_on.year < 2000:
            raise ValueError("Ingresa un período válido")
        return self


class ChangePlan(BaseModel):
    plan_code: Slug
    cycle: Literal["monthly", "annual"]
    discount_cents: Cents = 0


class SubscriptionTerms(BaseModel):
    grace_days: Days
    starts_on: date | None = None
    ends_on: date | None = None
    trial_days: Days | None = None
    discount_cents: Cents | None = None


class RenewalInput(BaseModel):
    starts_on: date
    ends_on: date


class SubscriptionState(BaseModel):
    action: Literal["suspend", "resume", "cancel"]


class PaymentInput(BaseModel):
    period_id: UUID
    amount_cents: Annotated[Cents, Field(gt=0)]
    method: Short
    reference: Short = ""
    paid_on: date
    notes: Notes = ""
    request_key: UUID
    receipt: Annotated[str, Field(max_length=2_800_000)] | None = None


class PaymentState(BaseModel):
    action: Literal["confirm", "reject", "reverse"]


PlatformRole = Literal["super", "admin", "commercial", "support", "auditor"]


class PlatformUserInput(BaseModel):
    name: Name
    email: EmailStr
    role: PlatformRole
    password: Password


class PlatformUserEdit(BaseModel):
    name: Name
    role: PlatformRole
    active: bool


class InvitationInput(BaseModel):
    name: Name
    email: EmailStr
    role: Short


class BrandingInput(BaseModel):
    name: Name
    support_email: EmailStr | Literal[""] = ""
    contact: Short = ""
    footer: Short = ""
    primary: Annotated[str, Field(pattern=r"^#[0-9a-fA-F]{6}$")] = "#EA580C"


class AssetInput(BaseModel):
    content: Annotated[str, Field(max_length=2_800_000)]


class SmtpInput(BaseModel):
    host: Annotated[str, Field(pattern=r"^[a-zA-Z0-9.-]{1,253}$")]
    port: Annotated[int, Field(ge=1, le=65535)]
    username: Short = ""
    password: Annotated[str, Field(max_length=512)] | None = None
    sender_name: Short = ""
    sender_email: EmailStr
    security: Literal["starttls", "ssl"] = "starttls"
    enabled: bool = False


class MailTest(BaseModel):
    email: EmailStr


class BackupSettings(BaseModel):
    interval_hours: Annotated[int, Field(ge=1, le=720)] = 24
    retention_days: Annotated[int, Field(ge=1, le=3650)] = 30
    automatic: bool = False


class TicketInput(BaseModel):
    restaurant: Slug
    subject: Name
    description: Notes
    priority: Literal["low", "normal", "high"]


class TicketEdit(BaseModel):
    state: Literal["open", "in_progress", "closed"]
    assignee_id: UUID | None = None
    message: Notes = ""


class GeneralInput(BaseModel):
    payment_methods: Annotated[list[Short], Field(min_length=1, max_length=30)]
    platform_name: Name = "Raíz Food"
    notification_email: EmailStr | Literal[""] = ""


class PermissionInput(BaseModel):
    permissions: Annotated[list[str], Field(max_length=20)]
