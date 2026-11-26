from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    Column,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Table,
    UniqueConstraint,
)

from app.restaurant_models import column, link, metadata, reference, scoped

OPEN = ("draft", "confirmed", "sent", "preparing", "ready", "delivered")
LINE_STATES = ("new", "sent", "preparing", "ready", "delivered", "cancelled")
TICKET_STATES = ("new", "preparing", "ready", "cancelled")


def choices(name, column_name, options):
    return CheckConstraint(f"{column_name} IN {options}", name=name)


def member(field):
    return ForeignKeyConstraint(
        [field, "tenant_id"], ["tenant_memberships.user_id", "tenant_memberships.tenant_id"]
    )


orders = scoped(
    "orders",
    column("number", Integer),
    column("mode"),
    reference("table_id", nullable=True),
    reference("customer_id", nullable=True),
    reference("creator_id"),
    reference("waiter_id", nullable=True),
    column("guests", Integer),
    column("status"),
    column("financial_status"),
    column("notes"),
    column("version", Integer),
    column("contact", JSON),
    column("delivery_state"),
    column("shipping_cents", BigInteger),
    column("subtotal_cents", BigInteger),
    column("discount_cents", BigInteger),
    column("total_cents", BigInteger),
    column("seated_at", Integer, nullable=True),
    link("table_id", "restaurant_tables"),
    link("customer_id", "customers"),
    member("creator_id"),
    member("waiter_id"),
    UniqueConstraint("tenant_id", "number"),
    choices("ck_order_status", "status", (*OPEN, "cancelled")),
    choices("ck_order_mode", "mode", ("dine_in", "takeaway", "delivery")),
    choices(
        "ck_order_financial",
        "financial_status",
        ("unpaid", "bill_requested", "partial", "paid", "reversed"),
    ),
    CheckConstraint("(mode = 'dine_in') = (table_id IS NOT NULL)", name="ck_order_table_mode"),
    CheckConstraint(
        "version >= 1 AND guests >= 0 AND total_cents >= 0 AND subtotal_cents >= 0 AND "
        "discount_cents BETWEEN 0 AND subtotal_cents AND shipping_cents >= 0 AND "
        "total_cents = subtotal_cents - discount_cents + shipping_cents",
        name="ck_order_totals",
    ),
)
active_table = (
    orders.c.table_id.is_not(None)
    & orders.c.status.in_(OPEN)
    & orders.c.financial_status.in_(("unpaid", "bill_requested", "partial"))
)
Index(
    "uq_active_order_by_table",
    orders.c.tenant_id,
    orders.c.table_id,
    unique=True,
    sqlite_where=active_table,
)
Index("ix_orders_tenant_created", orders.c.tenant_id, orders.c.created_at)
lines = scoped(
    "order_items",
    reference("order_id"),
    reference("item_id"),
    reference("variant_id", nullable=True),
    reference("preparation_id", nullable=True),
    column("snapshot", JSON),
    column("quantity", Integer),
    column("unit_cents", BigInteger),
    column("notes"),
    column("status"),
    column("revision", Integer),
    link("order_id", "orders"),
    link("item_id", "menu_items"),
    link("variant_id", "menu_item_variants"),
    link("preparation_id", "preparation_areas"),
    UniqueConstraint("tenant_id", "order_id", "id"),
    choices("ck_order_line_status", "status", LINE_STATES),
    CheckConstraint(
        "quantity > 0 AND unit_cents >= 0 AND revision >= 1", name="ck_order_line_numbers"
    ),
)
Index("ix_order_items_order", lines.c.tenant_id, lines.c.order_id)
line_modifiers = scoped(
    "order_item_modifiers",
    reference("line_id"),
    reference("modifier_id"),
    column("name"),
    column("price_cents", BigInteger),
    link("line_id", "order_items"),
    link("modifier_id", "modifiers"),
    UniqueConstraint("tenant_id", "line_id", "modifier_id"),
)
discounts = scoped(
    "order_discounts",
    reference("order_id"),
    reference("line_id", nullable=True),
    reference("actor_id"),
    column("kind"),
    column("value", BigInteger),
    column("reason"),
    link("order_id", "orders"),
    member("actor_id"),
    ForeignKeyConstraint(
        ["tenant_id", "order_id", "line_id"],
        ["order_items.tenant_id", "order_items.order_id", "order_items.id"],
    ),
    UniqueConstraint("tenant_id", "order_id", "line_id"),
    choices("ck_order_discount_kind", "kind", ("fixed", "percent")),
    CheckConstraint(
        "value > 0 AND (kind != 'percent' OR value <= 10000)", name="ck_order_discount_value"
    ),
)
Index(
    "uq_order_general_discount",
    discounts.c.tenant_id,
    discounts.c.order_id,
    unique=True,
    sqlite_where=discounts.c.line_id.is_(None),
)
history = scoped(
    "order_status_history",
    reference("order_id"),
    reference("actor_id"),
    column("action"),
    column("changes", JSON),
    link("order_id", "orders"),
    member("actor_id"),
)
Index("ix_order_history_timeline", history.c.tenant_id, history.c.order_id, history.c.created_at)
accounts = scoped(
    "order_accounts",
    reference("order_id"),
    column("name"),
    column("position", Integer),
    link("order_id", "orders"),
    UniqueConstraint("tenant_id", "order_id", "position"),
    UniqueConstraint("tenant_id", "order_id", "id"),
)
allocations = scoped(
    "order_account_items",
    reference("order_id"),
    reference("account_id"),
    reference("line_id"),
    column("quantity", Integer),
    UniqueConstraint("tenant_id", "account_id", "line_id"),
    ForeignKeyConstraint(
        ["tenant_id", "order_id", "line_id"],
        ["order_items.tenant_id", "order_items.order_id", "order_items.id"],
    ),
    ForeignKeyConstraint(
        ["tenant_id", "order_id", "account_id"],
        ["order_accounts.tenant_id", "order_accounts.order_id", "order_accounts.id"],
    ),
    CheckConstraint("quantity > 0", name="ck_account_quantity"),
)
tickets = scoped(
    "kitchen_tickets",
    reference("order_id"),
    reference("preparation_id", nullable=True),
    reference("actor_id"),
    column("number", Integer),
    column("kind"),
    column("state"),
    column("snapshot", JSON),
    column("started_at", Integer, nullable=True),
    column("ready_at", Integer, nullable=True),
    link("order_id", "orders"),
    link("preparation_id", "preparation_areas"),
    member("actor_id"),
    UniqueConstraint("tenant_id", "number"),
    UniqueConstraint("tenant_id", "order_id", "id"),
    choices(
        "ck_ticket_kind",
        "kind",
        ("initial", "additional", "adjustment", "cancellation", "transfer"),
    ),
    choices("ck_ticket_state", "state", TICKET_STATES),
)
Index(
    "ix_kitchen_queue",
    tickets.c.tenant_id,
    tickets.c.preparation_id,
    tickets.c.state,
    tickets.c.number,
)
ticket_lines = scoped(
    "kitchen_ticket_items",
    reference("ticket_id"),
    reference("line_id"),
    reference("order_id"),
    reference("original_ticket_id", nullable=True),
    column("revision", Integer),
    column("state"),
    column("snapshot", JSON),
    ForeignKeyConstraint(
        ["tenant_id", "order_id", "ticket_id"],
        ["kitchen_tickets.tenant_id", "kitchen_tickets.order_id", "kitchen_tickets.id"],
    ),
    ForeignKeyConstraint(
        ["tenant_id", "order_id", "line_id"],
        ["order_items.tenant_id", "order_items.order_id", "order_items.id"],
    ),
    ForeignKeyConstraint(
        ["tenant_id", "order_id", "original_ticket_id"],
        ["kitchen_tickets.tenant_id", "kitchen_tickets.order_id", "kitchen_tickets.id"],
    ),
    UniqueConstraint("tenant_id", "ticket_id", "line_id"),
    choices("ck_ticket_item_state", "state", TICKET_STATES),
)
sequences = Table(
    "document_sequences",
    metadata,
    Column("tenant_id", String(36), ForeignKey("tenants.id"), primary_key=True),
    Column("kind", String, primary_key=True),
    column("value", Integer),
)
idempotency = Table(
    "idempotency_records",
    metadata,
    Column("tenant_id", String(36), primary_key=True),
    Column("actor_id", String(36), primary_key=True),
    Column("request_id", String(36), primary_key=True),
    column("fingerprint"),
    column("result", JSON),
    column("created_at", Integer),
    member("actor_id"),
)
kitchen_access = Table(
    "kitchen_area_access",
    metadata,
    Column("tenant_id", String(36), primary_key=True),
    Column("user_id", String(36), primary_key=True),
    Column("preparation_id", String(36), primary_key=True),
    member("user_id"),
    link("preparation_id", "preparation_areas"),
)
