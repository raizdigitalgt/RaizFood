"""Pin onboarding seats to the selected catalog revision."""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "onboarding_plans",
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id"), primary_key=True),
        sa.Column(
            "plan_version_id", sa.String(36), sa.ForeignKey("plan_versions.id"), nullable=False
        ),
    )
    op.execute(
        sa.text(
            "INSERT INTO onboarding_plans (tenant_id, plan_version_id) "
            "SELECT tenants.id, plan_versions.id FROM tenants "
            "JOIN plan_versions ON plan_versions.plan_id = tenants.plan_id "
            "WHERE plan_versions.revision = 1"
        )
    )


def downgrade():
    op.drop_table("onboarding_plans")
