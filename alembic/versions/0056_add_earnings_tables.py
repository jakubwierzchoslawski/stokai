"""Add earnings_event and earnings_brief_run tables.

Revision: 0056
Revises: 0055
Create Date: 2026-06-04

PLAN-F-009 TASK-001

Changes:
  1. Creates earnings_event table (T-1 detection feed).
  2. Creates earnings_brief_run table (brief execution log with idempotency guard).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB, TIMESTAMPTZ

# revision identifiers, used by Alembic.
revision = "0056"
down_revision = "0055"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. Create earnings_event table ────────────────────────────────────────
    op.create_table(
        "earnings_event",
        sa.Column(
            "earnings_event_id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("company_id", UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("earnings_date", sa.Date(), nullable=False),
        sa.Column("fiscal_quarter", sa.String(10), nullable=True),
        sa.Column("expected_eps", sa.Float(), nullable=True),
        sa.Column("announced_at", TIMESTAMPTZ, nullable=True),
        sa.Column(
            "created_at",
            TIMESTAMPTZ,
            nullable=True,
            server_default=sa.text("now()"),
        ),
    )

    op.create_unique_constraint(
        "uq_earnings_event_company_tenant_date",
        "earnings_event",
        ["company_id", "tenant_id", "earnings_date"],
    )
    op.create_index(
        "idx_earnings_event_tenant_date",
        "earnings_event",
        ["tenant_id", "earnings_date"],
    )

    # ── 2. Create earnings_brief_run table ────────────────────────────────────
    op.create_table(
        "earnings_brief_run",
        sa.Column(
            "run_id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "workflow_id",
            UUID(as_uuid=True),
            sa.ForeignKey(
                "workflow_run.workflow_id",
                name="fk_earnings_brief_run_workflow",
            ),
            nullable=False,
        ),
        sa.Column("company_id", UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("earnings_date", sa.Date(), nullable=False),
        sa.Column(
            "status",
            sa.String(16),
            sa.CheckConstraint(
                "status IN ('running', 'completed', 'hil', 'failed')",
                name="ck_earnings_brief_run_status",
            ),
            nullable=False,
            server_default=sa.text("'running'"),
        ),
        sa.Column("scenario_tree", JSONB, nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=True),
        sa.Column(
            "hil_status",
            sa.String(16),
            sa.CheckConstraint(
                "hil_status IN ('none', 'pending', 'approved', 'rejected')",
                name="ck_earnings_brief_run_hil_status",
            ),
            nullable=False,
            server_default=sa.text("'none'"),
        ),
        sa.Column(
            "created_at",
            TIMESTAMPTZ,
            nullable=True,
            server_default=sa.text("now()"),
        ),
    )

    op.create_unique_constraint(
        "uq_earnings_brief_run_company_tenant_date",
        "earnings_brief_run",
        ["company_id", "tenant_id", "earnings_date"],
    )
    op.create_index(
        "idx_earnings_brief_run_tenant_company",
        "earnings_brief_run",
        ["tenant_id", "company_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_earnings_brief_run_tenant_company", table_name="earnings_brief_run")
    op.drop_constraint(
        "uq_earnings_brief_run_company_tenant_date",
        "earnings_brief_run",
        type_="unique",
    )
    op.drop_table("earnings_brief_run")

    op.drop_index("idx_earnings_event_tenant_date", table_name="earnings_event")
    op.drop_constraint(
        "uq_earnings_event_company_tenant_date",
        "earnings_event",
        type_="unique",
    )
    op.drop_table("earnings_event")
