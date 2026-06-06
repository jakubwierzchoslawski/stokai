"""Create alert_rule table per REQ-F-005 schema.

Revision ID: 0041
Revises: 0037
Create Date: 2026-06-03 00:00:00.000000

REQ-F-005 is authoritative over ARCHITECTURE.md for this table schema.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0041"
down_revision = "0040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS alert_rule (
            rule_id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id               UUID NOT NULL,
            user_id                 UUID NOT NULL REFERENCES "user"(user_id) ON DELETE CASCADE,
            event_categories        JSONB NOT NULL DEFAULT '[]',
            intensity_min           INT NOT NULL DEFAULT 1,
            ticker_list             JSONB NOT NULL DEFAULT '[]',
            quiet_hours_start       TIME,
            quiet_hours_end         TIME,
            daily_limit             INT NOT NULL DEFAULT 5,
            dedup_window_minutes    INT NOT NULL DEFAULT 60,
            per_ticker_interval_hours INT NOT NULL DEFAULT 24,
            enabled                 BOOLEAN NOT NULL DEFAULT TRUE,
            created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    # Indexes for performance — all WHERE clauses use these columns
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_alert_rule_tenant_enabled "
        "ON alert_rule (tenant_id, enabled)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_alert_rule_user_id "
        "ON alert_rule (user_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS alert_rule")
