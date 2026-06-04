"""
Create/extend workflow_run table and create ai_recommendation table.

Revision: 0040
Revises: 0039 (episodic memory tables)
Create Date: 2026-06-03

PLAN-F-007: On-Demand Analysis Workflow

Changes:
  1. Adds user_id and company_id columns to workflow_run (new columns required
     by PLAN-F-007; the base table was created in migration 0033).
  2. Creates composite index idx_workflow_run_tenant.
  3. Creates ai_recommendation table (TASK-010).
  4. Creates idx_ai_rec_company_tenant index.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB, TIMESTAMPTZ

# revision identifiers, used by Alembic.
revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. Extend workflow_run with user_id and company_id ────────────────────
    op.add_column(
        "workflow_run",
        sa.Column("user_id", UUID(as_uuid=True), nullable=True),  # initially nullable for migration
    )
    op.add_column(
        "workflow_run",
        sa.Column("company_id", UUID(as_uuid=True), nullable=True),
    )

    # Backfill user_id with a sentinel UUID so we can make it NOT NULL
    op.execute(
        "UPDATE workflow_run SET user_id = gen_random_uuid() WHERE user_id IS NULL"
    )
    op.alter_column("workflow_run", "user_id", nullable=False)

    # ── 2. Composite index for tenant-scoped lookups ──────────────────────────
    op.create_index(
        "idx_workflow_run_tenant",
        "workflow_run",
        ["tenant_id", "workflow_id"],
        unique=False,
    )

    # ── 3. Create ai_recommendation table ────────────────────────────────────
    op.create_table(
        "ai_recommendation",
        sa.Column(
            "rec_id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("event_id", UUID(as_uuid=True), nullable=True),
        sa.Column("company_id", UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("action_signal", sa.String(32), nullable=False),
        sa.Column("direction", sa.String(32), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("sample_size", sa.Integer(), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("forecast", JSONB, nullable=True),
        sa.Column("analogies", JSONB, nullable=True),
        sa.Column("model_version", sa.String(64), nullable=True),
        sa.Column(
            "workflow_run_id",
            UUID(as_uuid=True),
            sa.ForeignKey("workflow_run.workflow_id", name="fk_ai_rec_workflow_run"),
            nullable=True,
        ),
        sa.Column(
            "generated_at",
            TIMESTAMPTZ,
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # ── 4. Index on ai_recommendation for company/tenant lookups ─────────────
    op.create_index(
        "idx_ai_rec_company_tenant",
        "ai_recommendation",
        ["company_id", "tenant_id", "generated_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_ai_rec_company_tenant", table_name="ai_recommendation")
    op.drop_table("ai_recommendation")
    op.drop_index("idx_workflow_run_tenant", table_name="workflow_run")
    op.drop_column("workflow_run", "company_id")
    op.drop_column("workflow_run", "user_id")
