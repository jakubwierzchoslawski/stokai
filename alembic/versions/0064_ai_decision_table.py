"""Create ai_decision audit log table.

Revision: 0064
Revises: 0063
Create Date: 2026-06-04

PLAN-F-029 TASK-001

Changes:
  1. Creates ai_decision table for denormalised AI decision audit log.
  2. Adds composite index on (created_at DESC, decision_id) for cursor pagination.
  3. Adds index on agent_role.
  4. Adds index on company_ticker.
  5. Adds index on action_signal.
  6. Adds GIN index on retrieved_analogs JSONB.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB, TIMESTAMPTZ

# revision identifiers, used by Alembic.
revision = "0064"
down_revision = "0063"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_decision",
        sa.Column(
            "decision_id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("agent_role", sa.String(), nullable=False),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("prompt_version", sa.String(40), nullable=False),
        sa.Column(
            "confidence",
            sa.Float(),
            nullable=False,
            comment="Must be between 0 and 1",
        ),
        sa.Column("inputs_summary", sa.Text(), nullable=False),
        sa.Column("inputs_full", sa.Text(), nullable=False),
        sa.Column("retrieved_analogs", JSONB(), nullable=False, server_default="[]"),
        sa.Column("action_signal", sa.String(), nullable=True),
        sa.Column("company_ticker", sa.String(), nullable=True),
        sa.Column("output_text", sa.Text(), nullable=False),
        sa.Column("langfuse_trace_url", sa.String(), nullable=False),
        sa.Column(
            "workflow_run_id",
            UUID(as_uuid=True),
            sa.ForeignKey("workflow_run.workflow_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            TIMESTAMPTZ(),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint(
            "confidence >= 0.0 AND confidence <= 1.0",
            name="ai_decision_confidence_range",
        ),
    )

    # Composite index for cursor-based pagination
    op.create_index(
        "ix_ai_decision_created_at_decision_id",
        "ai_decision",
        [sa.text("created_at DESC"), "decision_id"],
    )

    # Individual field indexes
    op.create_index("ix_ai_decision_agent_role", "ai_decision", ["agent_role"])
    op.create_index(
        "ix_ai_decision_company_ticker", "ai_decision", ["company_ticker"]
    )
    op.create_index("ix_ai_decision_action_signal", "ai_decision", ["action_signal"])

    # GIN index on retrieved_analogs JSONB
    op.create_index(
        "ix_ai_decision_retrieved_analogs_gin",
        "ai_decision",
        ["retrieved_analogs"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index("ix_ai_decision_retrieved_analogs_gin", table_name="ai_decision")
    op.drop_index("ix_ai_decision_action_signal", table_name="ai_decision")
    op.drop_index("ix_ai_decision_company_ticker", table_name="ai_decision")
    op.drop_index("ix_ai_decision_agent_role", table_name="ai_decision")
    op.drop_index(
        "ix_ai_decision_created_at_decision_id", table_name="ai_decision"
    )
    op.drop_table("ai_decision")
