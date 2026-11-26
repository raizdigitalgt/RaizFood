from typing import Annotated

from pydantic import BaseModel, EmailStr, Field, StringConstraints

Slug = Annotated[
    str, StringConstraints(min_length=2, max_length=64, pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")
]
Password = Annotated[str, Field(min_length=12, max_length=128)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=100)]


class LoginInput(BaseModel):
    email: EmailStr
    password: Annotated[str, Field(min_length=1, max_length=128)]
    remember: bool = False
    otp: Annotated[str, StringConstraints(pattern=r"^[0-9]{6}$")] | None = None


class ChooseTenant(BaseModel):
    slug: Slug


class RestaurantInput(BaseModel):
    slug: Slug
    name: Name
    plan_code: Annotated[str, StringConstraints(min_length=1, max_length=30)]


class MemberInput(BaseModel):
    email: EmailStr
    role_code: Annotated[str, StringConstraints(min_length=1, max_length=40)]
    name: Name | None = None
    password: Password | None = None


class ResetInput(BaseModel):
    token: Annotated[str, Field(min_length=43, max_length=100)]
    password: Password


class TenantOption(BaseModel):
    slug: str
    name: str


class Identity(BaseModel):
    name: str
    email: str
    platform_admin: bool
    platform_permissions: list[str] = []
    tenant: TenantOption | None
    restaurants: list[TenantOption]
    permissions: list[str]


class PlanResponse(BaseModel):
    code: str
    name: str
    monthly_cents: int
    max_admins: int
    max_staff: int
    max_total: int
    fel_enabled: bool


class UsageResponse(BaseModel):
    admins: int
    staff: int
    total: int


class RestaurantResponse(TenantOption):
    active: bool
    created_at: int
    plan: PlanResponse
    usage: UsageResponse


class RestaurantPage(BaseModel):
    items: list[RestaurantResponse]
    total: int


class PlatformDashboard(BaseModel):
    restaurants: int
    active: int
    users: int
    plans: int
    recent: list[RestaurantResponse]


class MemberResponse(BaseModel):
    name: str
    email: str
    role: str
    active: bool


class RoleResponse(BaseModel):
    code: str
    name: str


class TeamPage(BaseModel):
    items: list[MemberResponse]
    roles: list[RoleResponse]
