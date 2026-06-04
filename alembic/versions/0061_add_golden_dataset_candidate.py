"""Add golden_dataset_candidate table.

Revision: 0061
Revises: 0060
Create Date: 2026-06-04

PLAN-F-026 TASK-003

Changes:
  1. Creates golden_dataset_candidate table.
  2. Indexes (tenant_id, reviewed, created_at DESC) for Admin Audit Console query.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision = "0061"
down_revision = "0060"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "golden_dataset_candidate",
        sa.Column(
            "candidate_id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "brief_id",
            UUID(as_uuid=True),
            sa.ForeignKey("workflow_run.workflow_id", name="fk_golden_dataset_workflow_run"),
            nullable=False,
        ),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("original_content", sa.Text(), nullable=False),
        sa.Column("correction", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "reviewed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("FALSE"),
        ),
        sa.Column("review_notes", sa.Text(), nullable=True),
    )

    # Index for Admin Audit Console: unreviewed candidates by tenant, ordered by creation
    op.create_index(
        "idx_golden_dataset_candidate_tenant_reviewed_created",
        "golden_dataset_candidate",
        ["tenant_id", "reviewed", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_golden_dataset_candidate_tenant_reviewed_created",
        table_name="golden_dataset_candidate",
    )
    op.drop_table("golden_dataset_candidate")
