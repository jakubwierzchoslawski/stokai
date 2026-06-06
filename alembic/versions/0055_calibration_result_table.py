"""calibration_result table for Tier-3 calibration tracking

Revision ID: 0055
Revises: 0054
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

revision = "0055"
down_revision = "0054"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "calibration_result",
        sa.Column(
            "result_id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("action_signal", sa.String(), nullable=False),
        sa.Column("total_recommendations", sa.Integer(), nullable=False),
        sa.Column("direction_correct_pct", sa.Float(), nullable=False),
        sa.Column("corr_confidence_actual", sa.Float(), nullable=True),
        sa.Column("mean_confidence", sa.Float(), nullable=False),
        sa.Column("mean_actual_t1d", sa.Float(), nullable=True),
        sa.Column(
            "computed_at",
            TIMESTAMPTZ(),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint(
            "date",
            "action_signal",
            name="uq_calibration_result_date_signal",
        ),
    )


def downgrade() -> None:
    op.drop_table("calibration_result")
