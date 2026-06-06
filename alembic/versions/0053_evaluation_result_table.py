"""evaluation_result table for Tier-1 judge outputs

Revision ID: 0053
Revises: 0052
Create Date: 2026-06-04 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy import DateTime

try:
    from sqlalchemy.dialects.postgresql import TIMESTAMPTZ
except ImportError:
    TIMESTAMPTZ = lambda: DateTime(timezone=True)  # type: ignore[misc,assignment]

revision = "0053"
down_revision = "0052"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "evaluation_result",
        sa.Column(
            "eval_id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("run_id", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "eval_type",
            sa.String(),
            nullable=False,
            server_default=sa.text("'tier_1'"),
        ),
        sa.Column("judge_model", sa.String(), nullable=False),
        sa.Column("scores", JSONB(), nullable=False),
        sa.Column("overall_quality", sa.Float(), nullable=False),
        sa.Column("prompt_version", sa.String(), nullable=False),
        sa.Column(
            "evaluated_at",
            TIMESTAMPTZ(),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint(
            "overall_quality >= 0 AND overall_quality <= 1",
            name="ck_evaluation_result_overall_quality_range",
        ),
    )
    op.create_index(
        "ix_evaluation_result_run_id",
        "evaluation_result",
        ["run_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_evaluation_result_run_id", table_name="evaluation_result")
    op.drop_table("evaluation_result")
