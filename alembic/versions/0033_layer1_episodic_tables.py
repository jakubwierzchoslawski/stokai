"""Layer 1 episodic tables with insert-only enforcement

Revision ID: 0033
Revises: 0032
Create Date: 2026-06-03 00:00:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy import DateTime

try:
    from sqlalchemy.dialects.postgresql import TIMESTAMPTZ
except ImportError:
    TIMESTAMPTZ = lambda: DateTime(timezone=True)  # type: ignore[misc,assignment]

# revision identifiers, used by Alembic.
revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── workflow_run ──────────────────────────────────────────────────────────
    op.create_table(
        "workflow_run",
        sa.Column(
            "workflow_id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workflow_type", sa.String(), nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "started_at",
            TIMESTAMPTZ(),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("completed_at", TIMESTAMPTZ(), nullable=True),
        sa.Column(
            "status",
            sa.String(),
            nullable=False,
            server_default=sa.text("'running'"),
        ),
        sa.Column("final_state", JSONB(), nullable=True),
        sa.Column("cost_usd", sa.Float(), server_default=sa.text("0.0")),
        sa.Column("langfuse_trace_id", sa.String(), nullable=True),
    )

    # ── agent_invocation ──────────────────────────────────────────────────────
    op.create_table(
        "agent_invocation",
        sa.Column("invocation_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("workflow_id", UUID(as_uuid=True), nullable=False),
        sa.Column("agent_role_id", sa.String(), nullable=False),
        sa.Column(
            "started_at",
            TIMESTAMPTZ(),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("model_used", sa.String(), nullable=True),
        sa.Column("prompt_version", sa.String(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), server_default=sa.text("0")),
        sa.Column("output_tokens", sa.Integer(), server_default=sa.text("0")),
        sa.Column("cost_usd", sa.Float(), server_default=sa.text("0.0")),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("output", JSONB(), nullable=True),
        sa.Column(
            "tools_called",
            JSONB(),
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.ForeignKeyConstraint(
            ["workflow_id"],
            ["workflow_run.workflow_id"],
            name="fk_agent_invocation_workflow_run",
        ),
    )

    # ── tool_call ─────────────────────────────────────────────────────────────
    op.create_table(
        "tool_call",
        sa.Column("tool_call_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("invocation_id", UUID(as_uuid=True), nullable=False),
        sa.Column("tool_name", sa.String(), nullable=False),
        sa.Column("arguments", JSONB(), nullable=True),
        sa.Column("result", JSONB(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("cost_tier", sa.String(), nullable=True),
        sa.Column("cached", sa.Boolean(), server_default=sa.text("FALSE")),
        sa.Column(
            "called_at",
            TIMESTAMPTZ(),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.ForeignKeyConstraint(
            ["invocation_id"],
            ["agent_invocation.invocation_id"],
            name="fk_tool_call_agent_invocation",
        ),
    )

    # ── recommendation_outcome ────────────────────────────────────────────────
    op.create_table(
        "recommendation_outcome",
        sa.Column("rec_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("workflow_id", UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", UUID(as_uuid=True), nullable=True),
        sa.Column("action_signal", sa.String(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("actual_t1d", sa.Float(), nullable=True),
        sa.Column("actual_t1w", sa.Float(), nullable=True),
        sa.Column("direction_correct", sa.Boolean(), nullable=True),
        sa.Column("filled_at", TIMESTAMPTZ(), nullable=True),
        sa.Column(
            "created_at",
            TIMESTAMPTZ(),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.ForeignKeyConstraint(
            ["workflow_id"],
            ["workflow_run.workflow_id"],
            name="fk_recommendation_outcome_workflow_run",
        ),
    )

    # ── Insert-only trigger function ──────────────────────────────────────────
    # workflow_run, agent_invocation, tool_call are fully append-only.
    # recommendation_outcome allows updating actual_t1d, actual_t1w,
    # direction_correct, filled_at (calibration columns) but blocks DELETE.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION enforce_append_only()
        RETURNS TRIGGER AS $$
        BEGIN
            IF TG_OP = 'UPDATE' THEN
                RAISE EXCEPTION
                    'Updates are not allowed on append-only table %', TG_TABLE_NAME
                    USING ERRCODE = 'restrict_violation';
            ELSIF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION
                    'Deletes are not allowed on append-only table %', TG_TABLE_NAME
                    USING ERRCODE = 'restrict_violation';
            END IF;
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION enforce_recommendation_outcome_append_only()
        RETURNS TRIGGER AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION
                    'Deletes are not allowed on append-only table recommendation_outcome'
                    USING ERRCODE = 'restrict_violation';
            ELSIF TG_OP = 'UPDATE' THEN
                -- Only calibration columns may be updated
                IF OLD.rec_id         IS DISTINCT FROM NEW.rec_id OR
                   OLD.workflow_id    IS DISTINCT FROM NEW.workflow_id OR
                   OLD.company_id     IS DISTINCT FROM NEW.company_id OR
                   OLD.action_signal  IS DISTINCT FROM NEW.action_signal OR
                   OLD.confidence     IS DISTINCT FROM NEW.confidence OR
                   OLD.created_at     IS DISTINCT FROM NEW.created_at THEN
                    RAISE EXCEPTION
                        'Only calibration columns (actual_t1d, actual_t1w, direction_correct, filled_at) may be updated on recommendation_outcome'
                        USING ERRCODE = 'restrict_violation';
                END IF;
            END IF;
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    for table in ("workflow_run", "agent_invocation", "tool_call"):
        op.execute(
            f"""
            CREATE TRIGGER trg_{table}_append_only
            BEFORE UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION enforce_append_only();
            """
        )

    op.execute(
        """
        CREATE TRIGGER trg_recommendation_outcome_append_only
        BEFORE UPDATE OR DELETE ON recommendation_outcome
        FOR EACH ROW EXECUTE FUNCTION enforce_recommendation_outcome_append_only();
        """
    )


def downgrade() -> None:
    for table in (
        "recommendation_outcome",
        "workflow_run",
        "agent_invocation",
        "tool_call",
    ):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_append_only ON {table};")

    op.execute("DROP FUNCTION IF EXISTS enforce_append_only();")
    op.execute(
        "DROP FUNCTION IF EXISTS enforce_recommendation_outcome_append_only();"
    )

    op.drop_table("recommendation_outcome")
    op.drop_table("tool_call")
    op.drop_table("agent_invocation")
    op.drop_table("workflow_run")
