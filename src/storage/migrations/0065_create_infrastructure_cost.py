"""
Alembic migration 0065 — create infrastructure_cost table.

Introduced by PLAN-N-005 TASK-001.

Table: infrastructure_cost
  cost_id        UUID PRIMARY KEY DEFAULT gen_random_uuid()
  tenant_id      UUID NULLABLE
  billing_month  DATE NOT NULL
  category       VARCHAR(32) NOT NULL
  description    TEXT NOT NULL
  cost_usd       NUMERIC(10,4) NOT NULL CHECK (cost_usd >= 0)
  recorded_at    TIMESTAMPTZ NOT NULL DEFAULT now()
  recorded_by    UUID NOT NULL

Index: ix_infrastructure_cost_billing_month_tenant_id (billing_month, tenant_id)
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0065"
down_revision: str | None = "0064"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "infrastructure_cost",
        sa.Column(
            "cost_id",
            sa.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("tenant_id", sa.UUID(as_uuid=True), nullable=True),
        sa.Column("billing_month", sa.Date(), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "cost_usd",
            sa.Numeric(10, 4),
            nullable=False,
        ),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("recorded_by", sa.UUID(as_uuid=True), nullable=False),
        sa.CheckConstraint("cost_usd >= 0", name="chk_infra_cost_usd_non_negative"),
    )

    op.create_index(
        "ix_infrastructure_cost_billing_month_tenant_id",
        "infrastructure_cost",
        ["billing_month", "tenant_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_infrastructure_cost_billing_month_tenant_id",
        table_name="infrastructure_cost",
    )
    op.drop_table("infrastructure_cost")
