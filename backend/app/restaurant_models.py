from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    LargeBinary,
    String,
    Table,
    UniqueConstraint,
)

from app import commercial_models  # noqa: F401
from app.db import Base
from app.models import now, uuid

metadata = Base.metadata


def column(name, kind=String, default=None, *, nullable=False):
    return Column(name, kind, nullable=nullable, default=default)


def link(field, target):
    return ForeignKeyConstraint(["tenant_id", field], [f"{target}.tenant_id", f"{target}.id"])


def scoped(name, *fields):
    return Table(
        name,
        metadata,
        Column("id", String(36), primary_key=True, default=uuid),
        Column("tenant_id", String(36), ForeignKey("tenants.id"), nullable=False),
        column("created_at", Integer, now),
        column("updated_at", Integer, now),
        UniqueConstraint("tenant_id", "id", name=f"uq_{name}_tenant_id"),
        Index(f"ix_{name}_tenant", "tenant_id"),
        *fields,
    )


def named():
    return [
        column("name"),
        column("normalized_name"),
        column("description", default=""),
        column("active", Boolean, True),
        column("position", Integer, 0),
    ]


def reference(name, *, nullable=False):
    return column(name, String(36), nullable=nullable)


media_folders = scoped(
    "media_folders",
    column("name"),
    column("normalized_name"),
    reference("parent_id", nullable=True),
    link("parent_id", "media_folders"),
)
Index(
    "uq_media_folders_parent_name",
    media_folders.c.tenant_id,
    media_folders.c.parent_id,
    media_folders.c.normalized_name,
    unique=True,
)
Index(
    "uq_media_folders_root_name",
    media_folders.c.tenant_id,
    media_folders.c.normalized_name,
    unique=True,
    sqlite_where=media_folders.c.parent_id.is_(None),
)
media_files = scoped(
    "media_files",
    column("name"),
    reference("folder_id", nullable=True),
    column("width", Integer),
    column("height", Integer),
    column("size", Integer),
    column("content", LargeBinary),
    column("thumbnail", LargeBinary),
    link("folder_id", "media_folders"),
)
categories = scoped(
    "menu_categories",
    *named(),
    column("icon", default=""),
    column("color", default=""),
    reference("image_id", nullable=True),
    link("image_id", "media_files"),
    UniqueConstraint("tenant_id", "normalized_name"),
)
preparation = scoped(
    "preparation_areas", *named(), UniqueConstraint("tenant_id", "normalized_name")
)
areas = scoped("restaurant_areas", *named(), UniqueConstraint("tenant_id", "normalized_name"))
tables = scoped(
    "restaurant_tables",
    reference("area_id"),
    column("number"),
    column("normalized_number"),
    column("name", default=""),
    column("capacity", Integer),
    column("state"),
    column("position", Integer, 0),
    link("area_id", "restaurant_areas"),
    UniqueConstraint("tenant_id", "area_id", "normalized_number"),
    CheckConstraint("capacity > 0", name="ck_restaurant_table_capacity"),
    CheckConstraint(
        "state IN ('available','cleaning','out_of_service','occupied','reserved','payment_due')",
        name="ck_restaurant_table_state",
    ),
)
customers = scoped(
    "customers",
    column("name"),
    column("tax_id", default=""),
    column("phone", default=""),
    column("email", default=""),
    column("address", default=""),
    column("notes", default=""),
    column("active", Boolean, True),
)
items = scoped(
    "menu_items",
    *named(),
    column("code"),
    column("normalized_code"),
    column("sku", default=""),
    reference("category_id"),
    reference("image_id", nullable=True),
    reference("preparation_id", nullable=True),
    column("price_cents", BigInteger),
    column("available", Boolean, True),
    column("prep_minutes", Integer, 0),
    column("featured", Boolean, False),
    UniqueConstraint("tenant_id", "normalized_code"),
    link("category_id", "menu_categories"),
    link("image_id", "media_files"),
    link("preparation_id", "preparation_areas"),
    CheckConstraint("price_cents >= 0 AND prep_minutes >= 0", name="ck_menu_item_numbers"),
)
variants = scoped(
    "menu_item_variants",
    *named(),
    column("code"),
    column("normalized_code"),
    reference("item_id"),
    reference("image_id", nullable=True),
    column("available", Boolean, True),
    column("pricing"),
    column("price_cents", BigInteger),
    UniqueConstraint("tenant_id", "normalized_code"),
    link("item_id", "menu_items"),
    link("image_id", "media_files"),
    CheckConstraint(
        "pricing IN ('replace','adjust') AND (pricing = 'adjust' OR price_cents >= 0)",
        name="ck_variant_pricing",
    ),
)
groups = scoped(
    "modifier_groups",
    *named(),
    column("minimum", Integer),
    column("maximum", Integer),
    UniqueConstraint("tenant_id", "normalized_name"),
    CheckConstraint(
        "minimum >= 0 AND maximum >= 1 AND maximum >= minimum", name="ck_modifier_limits"
    ),
)
modifiers = scoped(
    "modifiers",
    *named(),
    reference("group_id"),
    column("price_cents", BigInteger),
    link("group_id", "modifier_groups"),
    UniqueConstraint("tenant_id", "group_id", "normalized_name"),
    CheckConstraint("price_cents >= 0", name="ck_modifier_price"),
)
item_groups = Table(
    "menu_item_modifier_groups",
    metadata,
    Column("tenant_id", String(36), ForeignKey("tenants.id"), primary_key=True),
    Column("item_id", String(36), primary_key=True),
    Column("group_id", String(36), primary_key=True),
    link("item_id", "menu_items"),
    link("group_id", "modifier_groups"),
)
price_history = scoped(
    "menu_price_history",
    reference("item_id"),
    reference("variant_id", nullable=True),
    Column("actor_id", String(36), ForeignKey("users.id"), nullable=False),
    column("price_cents", BigInteger),
    column("pricing"),
    link("item_id", "menu_items"),
    link("variant_id", "menu_item_variants"),
)
settings = Table(
    "restaurant_settings",
    metadata,
    Column("tenant_id", String(36), ForeignKey("tenants.id"), primary_key=True),
    column("profile", JSON, dict),
    column("preferences", JSON, dict),
    reference("logo_id", nullable=True),
    reference("cover_id", nullable=True),
    reference("default_area_id", nullable=True),
    reference("default_preparation_id", nullable=True),
    link("logo_id", "media_files"),
    link("cover_id", "media_files"),
    link("default_area_id", "restaurant_areas"),
    link("default_preparation_id", "preparation_areas"),
    column("updated_at", Integer, now),
)
payment_methods = scoped(
    "payment_methods",
    *named(),
    UniqueConstraint("tenant_id", "normalized_name"),
)
change_requests = scoped(
    "subscription_change_requests",
    Column("plan_id", String(36), ForeignKey("plans.id"), nullable=False),
    Column("actor_id", String(36), ForeignKey("users.id"), nullable=False),
    column("notes"),
    column("status", default="pending"),
)
Index(
    "uq_pending_restaurant_plan_request",
    change_requests.c.tenant_id,
    unique=True,
    sqlite_where=change_requests.c.status == "pending",
)
member_profiles = Table(
    "restaurant_member_profiles",
    metadata,
    Column("tenant_id", String(36), primary_key=True),
    Column("user_id", String(36), primary_key=True),
    column("display_name"),
    ForeignKeyConstraint(
        ["user_id", "tenant_id"], ["tenant_memberships.user_id", "tenant_memberships.tenant_id"]
    ),
)
