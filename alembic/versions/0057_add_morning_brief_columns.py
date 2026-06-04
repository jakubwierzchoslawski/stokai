"""Add morning brief columns to brief table.

Revision: 0057
Revises: 0056
Create Date: 2026-06-04

PLAN-F-006 TASK-002

Changes:
  1. Adds brief_type column (VARCHAR, check constraint morning_brief/watchlist_scan/earnings_brief/event_deep_dive).
  2. Adds user_id column to brief table.
  3. Adds workflow_id column to brief table.
  4. Adds hil_status column (VARCHAR, check constraint none/pending/approved/rejected).
  5. Adds sent_at column (TIMESTAMPTZ, nullable).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, TIMESTAMPTZ

# revision identifiers, used by Alembic.
revision = "0057"
down_revision = "0056"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add brief_type column (backfill as event_deep_dive for existing rows)
    op.add_column(
        "brief",
        sa.Column(
            "brief_type",
            sa.String(64),
            nullable=True,
            server_default=sa.text("'event_deep_dive'"),
        ),
    )
    op.create_check_constraint(
        "ck_brief_brief_type",
        "brief",
        "brief_type IN ('morning_brief', 'watchlist_scan', 'earnings_brief', 'event_deep_dive')",
    )

    # 2. Add user_id column (nullable for backward compatibility)
    op.add_column(
        "brief",
        sa.Column("user_id", UUID(as_uuid=True), nullable=True),
    )

    # 3. Add workflow_id column (nullable for backward compatibility)
    op.add_column(
        "brief",
        sa.Column("workflow_id", UUID(as_uuid=True), nullable=True),
    )

    # 4. Add hil_status column
    op.add_column(
        "brief",
        sa.Column(
            "hil_status",
            sa.String(16),
            nullable=True,
            server_default=sa.text("'none'"),
        ),
    )
    op.create_check_constraint(
        "ck_brief_hil_status",
        "brief",
        "hil_status IN ('none', 'pending', 'approved', 'rejected')",
    )

    # 5. Add sent_at column
    op.add_column(
        "brief",
        sa.Column("sent_at", TIMESTAMPTZ, nullable=True),
    )

    # Add index for morning brief lookups
    op.create_index(
        "idx_brief_user_tenant_type",
        "brief",
        ["user_id", "tenant_id", "brief_type"],
    )


def downgrade() -> None:
    op.drop_index("idx_brief_user_tenant_type", table_name="brief")
    op.drop_column("brief", "sent_at")
    op.drop_constraint("ck_brief_hil_status", "brief", type_="check")
    op.drop_column("brief", "hil_status")
    op.drop_column("brief", "workflow_id")
    op.drop_column("brief", "user_id")
    op.drop_constraint("ck_brief_brief_type", "brief", type_="check")
    op.drop_column("brief", "brief_type")
