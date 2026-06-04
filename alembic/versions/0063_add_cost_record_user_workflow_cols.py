"""Add user_id and workflow_run_id columns to cost_record table.

Revision: 0063
Revises: 0062
Create Date: 2026-06-04

PLAN-N-004 TASK-003

Changes:
  1. Adds user_id UUID nullable to cost_record for per-user daily totals.
  2. Adds workflow_run_id UUID nullable to cost_record to link to workflow_run.
  3. Adds composite index (user_id, tenant_id, date) to support
     daily_total_for_user() query performance.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision = "0063"
down_revision = "0062"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "cost_record",
        sa.Column("user_id", UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "cost_record",
        sa.Column(
            "workflow_run_id",
            UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_cost_record_user_tenant_date",
        "cost_record",
        ["user_id", "tenant_id", "date"],
    )


def downgrade() -> None:
    op.drop_index("ix_cost_record_user_tenant_date", table_name="cost_record")
    op.drop_column("cost_record", "workflow_run_id")
    op.drop_column("cost_record", "user_id")
