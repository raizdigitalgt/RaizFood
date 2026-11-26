"""pos_operations

Revision: 0007
Anterior: 0006
"""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


NEW_SCOPES = (
    "orders.assign",
    "orders.transfer",
    "orders.split",
    "orders.merge",
    "orders.request_bill",
    "kitchen.cancel",
    "kitchen.adjust",
    "kitchen.tickets.create",
    "kitchen.tickets.view",
    "kitchen.all_areas",
    "receipts.preview",
    "reports.operational",
)
GRANTS = {
    "admin": NEW_SCOPES,
    "waiter": (
        "orders.request_bill",
        "kitchen.tickets.create",
        "kitchen.tickets.view",
        "receipts.preview",
    ),
    "cashier": ("orders.request_bill", "orders.split", "orders.merge", "receipts.preview"),
    "cook": ("kitchen.tickets.view",),
}


def upgrade():
    connection = op.get_bind()
    for code in NEW_SCOPES:
        connection.execute(
            sa.text("INSERT OR IGNORE INTO permissions (code) VALUES (:code)"), {"code": code}
        )
    for role, scopes in {**GRANTS, "cashier": (*GRANTS["cashier"], "tables.view")}.items():
        for code in scopes:
            connection.execute(
                sa.text("""INSERT OR IGNORE INTO role_permissions (tenant_id, role_id, permission)
                SELECT tenant_id, id, :code FROM roles WHERE code = :role"""),
                {"role": role, "code": code},
            )
    op.create_table(
        "document_sequences",
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("value", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
        ),
        sa.PrimaryKeyConstraint("tenant_id", "kind"),
    )
    op.create_table(
        "idempotency_records",
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("actor_id", sa.String(length=36), nullable=False),
        sa.Column("request_id", sa.String(length=36), nullable=False),
        sa.Column("fingerprint", sa.String(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["actor_id", "tenant_id"],
            ["tenant_memberships.user_id", "tenant_memberships.tenant_id"],
        ),
        sa.PrimaryKeyConstraint("tenant_id", "actor_id", "request_id"),
    )
    op.create_table(
        "kitchen_area_access",
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("preparation_id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "preparation_id"],
            ["preparation_areas.tenant_id", "preparation_areas.id"],
        ),
        sa.ForeignKeyConstraint(
            ["user_id", "tenant_id"],
            ["tenant_memberships.user_id", "tenant_memberships.tenant_id"],
        ),
        sa.PrimaryKeyConstraint("tenant_id", "user_id", "preparation_id"),
    )
    op.create_table(
        "orders",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.Integer(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("mode", sa.String(), nullable=False),
        sa.Column("table_id", sa.String(length=36), nullable=True),
        sa.Column("customer_id", sa.String(length=36), nullable=True),
        sa.Column("creator_id", sa.String(length=36), nullable=False),
        sa.Column("waiter_id", sa.String(length=36), nullable=True),
        sa.Column("guests", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("financial_status", sa.String(), nullable=False),
        sa.Column("notes", sa.String(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("contact", sa.JSON(), nullable=False),
        sa.Column("delivery_state", sa.String(), nullable=False),
        sa.Column("shipping_cents", sa.BigInteger(), nullable=False),
        sa.Column("subtotal_cents", sa.BigInteger(), nullable=False),
        sa.Column("discount_cents", sa.BigInteger(), nullable=False),
        sa.Column("total_cents", sa.BigInteger(), nullable=False),
        sa.Column("seated_at", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "(mode = 'dine_in') = (table_id IS NOT NULL)", name="ck_order_table_mode"
        ),
        sa.CheckConstraint(
            "financial_status IN ('unpaid', 'bill_requested', 'partial', 'paid', 'reversed')",
            name="ck_order_financial",
        ),
        sa.CheckConstraint("mode IN ('dine_in', 'takeaway', 'delivery')", name="ck_order_mode"),
        sa.CheckConstraint(
            "status IN ('draft', 'confirmed', 'sent', 'preparing', "
            "'ready', 'delivered', 'cancelled')",
            name="ck_order_status",
        ),
        sa.CheckConstraint(
            "version >= 1 AND guests >= 0 AND total_cents >= 0 AND subtotal_cents >= 0 "
            "AND discount_cents BETWEEN 0 AND subtotal_cents AND shipping_cents >= 0 "
            "AND total_cents = subtotal_cents - discount_cents + shipping_cents",
            name="ck_order_totals",
        ),
        sa.ForeignKeyConstraint(
            ["creator_id", "tenant_id"],
            ["tenant_memberships.user_id", "tenant_memberships.tenant_id"],
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "customer_id"],
            ["customers.tenant_id", "customers.id"],
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "table_id"],
            ["restaurant_tables.tenant_id", "restaurant_tables.id"],
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
        ),
        sa.ForeignKeyConstraint(
            ["waiter_id", "tenant_id"],
            ["tenant_memberships.user_id", "tenant_memberships.tenant_id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_orders_tenant_id"),
        sa.UniqueConstraint("tenant_id", "number"),
    )
    with op.batch_alter_table("orders", schema=None) as batch_op:
        batch_op.create_index("ix_orders_tenant", ["tenant_id"], unique=False)
        batch_op.create_index("ix_orders_tenant_created", ["tenant_id", "created_at"], unique=False)
        batch_op.create_index(
            "uq_active_order_by_table",
            ["tenant_id", "table_id"],
            unique=True,
            sqlite_where=sa.text(
                "table_id IS NOT NULL AND status IN ('draft', 'confirmed', 'sent', "
                "'preparing', 'ready', 'delivered') "
                "AND financial_status IN ('unpaid', 'bill_requested', 'partial')"
            ),
        )

    op.create_table(
        "kitchen_tickets",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.String(length=36), nullable=False),
        sa.Column("preparation_id", sa.String(length=36), nullable=True),
        sa.Column("actor_id", sa.String(length=36), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("state", sa.String(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.Integer(), nullable=True),
        sa.Column("ready_at", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "kind IN ('initial', 'additional', 'adjustment', 'cancellation', 'transfer')",
            name="ck_ticket_kind",
        ),
        sa.CheckConstraint(
            "state IN ('new', 'preparing', 'ready', 'cancelled')", name="ck_ticket_state"
        ),
        sa.ForeignKeyConstraint(
            ["actor_id", "tenant_id"],
            ["tenant_memberships.user_id", "tenant_memberships.tenant_id"],
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "order_id"],
            ["orders.tenant_id", "orders.id"],
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "preparation_id"],
            ["preparation_areas.tenant_id", "preparation_areas.id"],
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_kitchen_tickets_tenant_id"),
        sa.UniqueConstraint("tenant_id", "number"),
        sa.UniqueConstraint("tenant_id", "order_id", "id"),
    )
    with op.batch_alter_table("kitchen_tickets", schema=None) as batch_op:
        batch_op.create_index(
            "ix_kitchen_queue", ["tenant_id", "preparation_id", "state", "number"], unique=False
        )
        batch_op.create_index("ix_kitchen_tickets_tenant", ["tenant_id"], unique=False)

    op.create_table(
        "order_accounts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "order_id"],
            ["orders.tenant_id", "orders.id"],
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_order_accounts_tenant_id"),
        sa.UniqueConstraint("tenant_id", "order_id", "id"),
        sa.UniqueConstraint("tenant_id", "order_id", "position"),
    )
    with op.batch_alter_table("order_accounts", schema=None) as batch_op:
        batch_op.create_index("ix_order_accounts_tenant", ["tenant_id"], unique=False)

    op.create_table(
        "order_status_history",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.String(length=36), nullable=False),
        sa.Column("actor_id", sa.String(length=36), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("changes", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["actor_id", "tenant_id"],
            ["tenant_memberships.user_id", "tenant_memberships.tenant_id"],
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "order_id"],
            ["orders.tenant_id", "orders.id"],
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_order_status_history_tenant_id"),
    )
    with op.batch_alter_table("order_status_history", schema=None) as batch_op:
        batch_op.create_index(
            "ix_order_history_timeline", ["tenant_id", "order_id", "created_at"], unique=False
        )
        batch_op.create_index("ix_order_status_history_tenant", ["tenant_id"], unique=False)

    op.create_table(
        "order_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.String(length=36), nullable=False),
        sa.Column("item_id", sa.String(length=36), nullable=False),
        sa.Column("variant_id", sa.String(length=36), nullable=True),
        sa.Column("preparation_id", sa.String(length=36), nullable=True),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_cents", sa.BigInteger(), nullable=False),
        sa.Column("notes", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "status IN ('new', 'sent', 'preparing', 'ready', 'delivered', 'cancelled')",
            name="ck_order_line_status",
        ),
        sa.CheckConstraint(
            "quantity > 0 AND unit_cents >= 0 AND revision >= 1", name="ck_order_line_numbers"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "item_id"],
            ["menu_items.tenant_id", "menu_items.id"],
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "order_id"],
            ["orders.tenant_id", "orders.id"],
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "preparation_id"],
            ["preparation_areas.tenant_id", "preparation_areas.id"],
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "variant_id"],
            ["menu_item_variants.tenant_id", "menu_item_variants.id"],
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_order_items_tenant_id"),
        sa.UniqueConstraint("tenant_id", "order_id", "id"),
    )
    with op.batch_alter_table("order_items", schema=None) as batch_op:
        batch_op.create_index("ix_order_items_order", ["tenant_id", "order_id"], unique=False)
        batch_op.create_index("ix_order_items_tenant", ["tenant_id"], unique=False)

    op.create_table(
        "kitchen_ticket_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.Integer(), nullable=False),
        sa.Column("ticket_id", sa.String(length=36), nullable=False),
        sa.Column("line_id", sa.String(length=36), nullable=False),
        sa.Column("order_id", sa.String(length=36), nullable=False),
        sa.Column("original_ticket_id", sa.String(length=36), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.CheckConstraint(
            "state IN ('new', 'preparing', 'ready', 'cancelled')", name="ck_ticket_item_state"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "order_id", "line_id"],
            ["order_items.tenant_id", "order_items.order_id", "order_items.id"],
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "order_id", "original_ticket_id"],
            ["kitchen_tickets.tenant_id", "kitchen_tickets.order_id", "kitchen_tickets.id"],
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "order_id", "ticket_id"],
            ["kitchen_tickets.tenant_id", "kitchen_tickets.order_id", "kitchen_tickets.id"],
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_kitchen_ticket_items_tenant_id"),
        sa.UniqueConstraint("tenant_id", "ticket_id", "line_id"),
    )
    with op.batch_alter_table("kitchen_ticket_items", schema=None) as batch_op:
        batch_op.create_index("ix_kitchen_ticket_items_tenant", ["tenant_id"], unique=False)

    op.create_table(
        "order_account_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.String(length=36), nullable=False),
        sa.Column("account_id", sa.String(length=36), nullable=False),
        sa.Column("line_id", sa.String(length=36), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.CheckConstraint("quantity > 0", name="ck_account_quantity"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "order_id", "account_id"],
            ["order_accounts.tenant_id", "order_accounts.order_id", "order_accounts.id"],
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "order_id", "line_id"],
            ["order_items.tenant_id", "order_items.order_id", "order_items.id"],
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "account_id", "line_id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_order_account_items_tenant_id"),
    )
    with op.batch_alter_table("order_account_items", schema=None) as batch_op:
        batch_op.create_index("ix_order_account_items_tenant", ["tenant_id"], unique=False)

    op.create_table(
        "order_discounts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.String(length=36), nullable=False),
        sa.Column("line_id", sa.String(length=36), nullable=True),
        sa.Column("actor_id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("value", sa.BigInteger(), nullable=False),
        sa.Column("reason", sa.String(), nullable=False),
        sa.CheckConstraint("kind IN ('fixed', 'percent')", name="ck_order_discount_kind"),
        sa.CheckConstraint(
            "value > 0 AND (kind != 'percent' OR value <= 10000)", name="ck_order_discount_value"
        ),
        sa.ForeignKeyConstraint(
            ["actor_id", "tenant_id"],
            ["tenant_memberships.user_id", "tenant_memberships.tenant_id"],
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "order_id", "line_id"],
            ["order_items.tenant_id", "order_items.order_id", "order_items.id"],
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "order_id"],
            ["orders.tenant_id", "orders.id"],
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_order_discounts_tenant_id"),
        sa.UniqueConstraint("tenant_id", "order_id", "line_id"),
    )
    with op.batch_alter_table("order_discounts", schema=None) as batch_op:
        batch_op.create_index("ix_order_discounts_tenant", ["tenant_id"], unique=False)
        batch_op.create_index(
            "uq_order_general_discount",
            ["tenant_id", "order_id"],
            unique=True,
            sqlite_where=sa.text("line_id IS NULL"),
        )

    op.create_table(
        "order_item_modifiers",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.Integer(), nullable=False),
        sa.Column("line_id", sa.String(length=36), nullable=False),
        sa.Column("modifier_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("price_cents", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "line_id"],
            ["order_items.tenant_id", "order_items.id"],
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "modifier_id"],
            ["modifiers.tenant_id", "modifiers.id"],
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_order_item_modifiers_tenant_id"),
        sa.UniqueConstraint("tenant_id", "line_id", "modifier_id"),
    )
    with op.batch_alter_table("order_item_modifiers", schema=None) as batch_op:
        batch_op.create_index("ix_order_item_modifiers_tenant", ["tenant_id"], unique=False)

    # ### end Alembic commands ###


def downgrade():
    connection = op.get_bind()
    for code in NEW_SCOPES:
        connection.execute(
            sa.text("DELETE FROM role_permissions WHERE permission = :code"), {"code": code}
        )
        connection.execute(sa.text("DELETE FROM permissions WHERE code = :code"), {"code": code})
    with op.batch_alter_table("order_item_modifiers", schema=None) as batch_op:
        batch_op.drop_index("ix_order_item_modifiers_tenant")

    op.drop_table("order_item_modifiers")
    with op.batch_alter_table("order_discounts", schema=None) as batch_op:
        batch_op.drop_index("uq_order_general_discount", sqlite_where=sa.text("line_id IS NULL"))
        batch_op.drop_index("ix_order_discounts_tenant")

    op.drop_table("order_discounts")
    with op.batch_alter_table("order_account_items", schema=None) as batch_op:
        batch_op.drop_index("ix_order_account_items_tenant")

    op.drop_table("order_account_items")
    with op.batch_alter_table("kitchen_ticket_items", schema=None) as batch_op:
        batch_op.drop_index("ix_kitchen_ticket_items_tenant")

    op.drop_table("kitchen_ticket_items")
    with op.batch_alter_table("order_items", schema=None) as batch_op:
        batch_op.drop_index("ix_order_items_tenant")
        batch_op.drop_index("ix_order_items_order")

    op.drop_table("order_items")
    with op.batch_alter_table("order_status_history", schema=None) as batch_op:
        batch_op.drop_index("ix_order_status_history_tenant")
        batch_op.drop_index("ix_order_history_timeline")

    op.drop_table("order_status_history")
    with op.batch_alter_table("order_accounts", schema=None) as batch_op:
        batch_op.drop_index("ix_order_accounts_tenant")

    op.drop_table("order_accounts")
    with op.batch_alter_table("kitchen_tickets", schema=None) as batch_op:
        batch_op.drop_index("ix_kitchen_tickets_tenant")
        batch_op.drop_index("ix_kitchen_queue")

    op.drop_table("kitchen_tickets")
    with op.batch_alter_table("orders", schema=None) as batch_op:
        batch_op.drop_index(
            "uq_active_order_by_table",
            sqlite_where=sa.text(
                "table_id IS NOT NULL AND status IN ('draft', 'confirmed', 'sent', "
                "'preparing', 'ready', 'delivered') "
                "AND financial_status IN ('unpaid', 'bill_requested', 'partial')"
            ),
        )
        batch_op.drop_index("ix_orders_tenant_created")
        batch_op.drop_index("ix_orders_tenant")

    op.drop_table("orders")
    op.drop_table("kitchen_area_access")
    op.drop_table("idempotency_records")
    op.drop_table("document_sequences")
    # ### end Alembic commands ###
