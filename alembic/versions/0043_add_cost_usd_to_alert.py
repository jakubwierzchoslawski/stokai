"""Add cost_usd NUMERIC(10,6) DEFAULT NULL to alert table.

Revision ID: 0043
Revises: 0042
Create Date: 2026-06-03 00:00:00.000000

AC-003: Every completed pipeline run writes total_cost_usd to alert.cost_usd.
NULL is acceptable for historical rows that predate PLAN-N-003.
Migration is reversible.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0043"
down_revision = "0042_create_alert_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The column may already exist as FLOAT NOT NULL DEFAULT 0 (from 0042).
    # Alter it to NUMERIC(10,6) NULLABLE so historical rows can hold NULL.
    op.execute(
        """
        ALTER TABLE alert
            ALTER COLUMN cost_usd DROP NOT NULL,
            ALTER COLUMN cost_usd DROP DEFAULT,
            ALTER COLUMN cost_usd TYPE NUMERIC(10, 6)
                USING cost_usd::NUMERIC(10, 6)
        """
    )


def downgrade() -> None:
    # Restore to FLOAT NOT NULL DEFAULT 0 (original schema from 0042).
    op.execute(
        """
        ALTER TABLE alert
            ALTER COLUMN cost_usd TYPE FLOAT
                USING cost_usd::FLOAT,
            ALTER COLUMN cost_usd SET NOT NULL,
            ALTER COLUMN cost_usd SET DEFAULT 0
        """
    )
