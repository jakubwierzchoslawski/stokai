"""
Create hil_queue_item table.

Revision: 0044
Revises: 0043
Create Date: 2026-06-03

PLAN-F-013: Human-in-the-Loop Review Queue (TASK-001)

Creates the hil_queue_item table that stores Mode B workflow pause records
awaiting human review. Confidence values must fall in the [0.4, 0.7) range
(D9 threshold decision). Status lifecycle: pending → approved | edited_approved
| rejected | timed_out.

Includes composite index on (tenant_id, status, scheduled_send_at) for
efficient admin queue queries (tenant-scoped, filtered by status, ordered
by deadline).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, TIMESTAMPTZ

# revision identifiers, used by Alembic.
revision = "0044"
down_revision = "0043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Create hil_queue_item table ───────────────────────────────────────────
    op.create_table(
        "hil_queue_item",
        sa.Column(
            "item_id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "workflow_run_id",
            UUID(as_uuid=True),
            sa.ForeignKey("workflow_run.workflow_id", name="fk_hil_queue_workflow_run"),
            nullable=False,
        ),
        sa.Column("workflow_type", sa.String(64), nullable=False),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("user.user_id", name="fk_hil_queue_user"),
            nullable=False,
        ),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "confidence",
            sa.Float(),
            nullable=False,
        ),
        sa.Column("scheduled_send_at", TIMESTAMPTZ, nullable=False),
        sa.Column(
            "status",
            sa.String(32),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column(
            "reviewer_id",
            UUID(as_uuid=True),
            sa.ForeignKey("user.user_id", name="fk_hil_queue_reviewer"),
            nullable=True,
        ),
        sa.Column("reviewed_at", TIMESTAMPTZ, nullable=True),
        sa.Column("lc_checkpoint_id", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            TIMESTAMPTZ,
            nullable=False,
            server_default=sa.text("now()"),
        ),
        # ── CHECK constraints ─────────────────────────────────────────────────
        sa.CheckConstraint(
            "confidence >= 0.4 AND confidence < 0.7",
            name="ck_hil_queue_confidence_range",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'edited_approved', 'rejected', 'timed_out')",
            name="ck_hil_queue_status_values",
        ),
    )

    # ── Composite index for efficient admin queue queries ─────────────────────
    # Supports: WHERE tenant_id = :tid AND status = 'pending' ORDER BY scheduled_send_at
    op.create_index(
        "idx_hil_queue_tenant_status",
        "hil_queue_item",
        ["tenant_id", "status", "scheduled_send_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_hil_queue_tenant_status", table_name="hil_queue_item")
    op.drop_table("hil_queue_item")
