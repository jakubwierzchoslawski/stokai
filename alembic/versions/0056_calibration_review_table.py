"""calibration_review table for weekly AI calibration review tracking

Revision ID: 0056
Revises: 0055
Create Date: 2026-06-04 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import DateTime

try:
    from sqlalchemy.dialects.postgresql import TIMESTAMPTZ
except ImportError:
    TIMESTAMPTZ = lambda: DateTime(timezone=True)  # type: ignore[misc,assignment]

revision = "0056_calibration_review"
down_revision = "0056_prompt_publication"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "calibration_review",
        sa.Column(
            "review_id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("reviewed_by", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "reviewed_at",
            TIMESTAMPTZ(),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("corr_at_review", sa.Float(), nullable=True),
        sa.Column("below_threshold", sa.Boolean(), nullable=False),
        sa.Column(
            "action_taken",
            sa.String(),
            nullable=False,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "action_taken IN ('no_action', 'improvement_loop_triggered', 'model_flag')",
            name="ck_calibration_review_action_taken",
        ),
    )
    op.create_index(
        "ix_calibration_review_reviewed_at_desc",
        "calibration_review",
        [sa.text("reviewed_at DESC")],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_calibration_review_reviewed_at_desc",
        table_name="calibration_review",
    )
    op.drop_table("calibration_review")
