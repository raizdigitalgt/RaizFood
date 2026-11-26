from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, model_validator

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Text = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]
Code = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]
ID = Annotated[str, Field(pattern=r"^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$")]
Money = Annotated[int, Field(ge=0, le=100_000_000)]
Position = Annotated[int, Field(ge=0, le=100_000)]
Color = Annotated[str, Field(pattern=r"^(|#[0-9a-fA-F]{6})$")]


class Payload(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Named(Payload):
    name: Name
    description: Text = ""
    active: bool = True
    position: Position = 0


class Category(Named):
    icon: Text = ""
    color: Color = ""
    image_id: ID | None = None


class MenuItem(Named):
    code: Code
    sku: Text = ""
    category_id: ID
    image_id: ID | None = None
    preparation_id: ID | None = None
    price_cents: Money
    available: bool = True
    prep_minutes: Annotated[int, Field(ge=0, le=1440)] = 0
    featured: bool = False
    group_ids: Annotated[list[ID], Field(max_length=30)] = []


class Variant(Named):
    item_id: ID
    code: Code
    image_id: ID | None = None
    available: bool = True
    pricing: Literal["replace", "adjust"] = "replace"
    price_cents: Annotated[int, Field(ge=-100_000_000, le=100_000_000)]

    @model_validator(mode="after")
    def valid_price(self):
        if self.pricing == "replace" and self.price_cents < 0:
            raise ValueError("El precio propio debe ser positivo o cero")
        return self


class Group(Named):
    minimum: Annotated[int, Field(ge=0, le=25)] = 0
    maximum: Annotated[int, Field(ge=1, le=25)] = 1

    @model_validator(mode="after")
    def valid_bounds(self):
        if self.minimum > self.maximum:
            raise ValueError("El mínimo no puede superar el máximo")
        return self


class Modifier(Named):
    group_id: ID
    price_cents: Money = 0


class RestaurantTable(Payload):
    area_id: ID
    number: Code
    name: Text = ""
    capacity: Annotated[int, Field(ge=1, le=1000)] = 4
    state: Literal["available", "cleaning", "out_of_service"] = "available"
    position: Position = 0


class BatchTables(Payload):
    area_id: ID
    prefix: Code
    quantity: Annotated[int, Field(ge=1, le=100)]
    start: Annotated[int, Field(ge=1, le=9998)] = 1
    capacity: Annotated[int, Field(ge=1, le=1000)] = 4


class Customer(Payload):
    name: Name
    tax_id: Text = ""
    phone: Text = ""
    email: EmailStr | Literal[""] = ""
    address: Text = ""
    notes: Text = ""
    active: bool = True


class Folder(Payload):
    name: Name
    parent_id: ID | None = None


class FileEdit(Payload):
    name: Name
    folder_id: ID | None = None


class FileUpload(FileEdit):
    content: Annotated[str, Field(max_length=22_369_624)]


class SettingsInput(Payload):
    name: Name
    legal_name: Text = ""
    tax_id: Text = ""
    owner: Text = ""
    phone: Text = ""
    contact_email: EmailStr | Literal[""] = ""
    address: Text = ""
    department: Text = ""
    municipality: Text = ""
    contact_info: Text = ""
    display_name: Text = ""
    accent: Color = ""
    hours: Text = ""
    days: Annotated[
        list[Literal["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]], Field(max_length=7)
    ] = []
    timezone: Literal[
        "America/Guatemala",
        "America/Belize",
        "America/El_Salvador",
        "America/Tegucigalpa",
        "America/Costa_Rica",
        "America/Managua",
        "America/Panama",
        "America/Mexico_City",
    ] = "America/Guatemala"
    order_modes: Annotated[
        list[Literal["dine_in", "takeaway", "delivery"]], Field(max_length=3)
    ] = ["dine_in"]
    table_policy: Text = ""
    default_available: bool = True
    currency: Literal["GTQ"] = "GTQ"
    discount_policy: Text = ""
    thanks: Text = ""
    receipt_preferences: Text = ""
    logo_id: ID | None = None
    cover_id: ID | None = None
    default_area_id: ID | None = None
    default_preparation_id: ID | None = None


class Quote(Payload):
    variant_id: ID | None = None
    quantity: Annotated[int, Field(ge=1, le=1000)] = 1
    modifier_ids: Annotated[list[ID], Field(max_length=150)] = []


class DuplicateItem(Payload):
    code: Code
    name: Name


class ChangeRequest(Payload):
    plan_code: Code
    notes: Text = ""


class RoleEdit(Payload):
    name: Name
    permissions: Annotated[list[Code], Field(max_length=120)]


class MemberEdit(Payload):
    display_name: Name
    role_code: Code
    active: bool
