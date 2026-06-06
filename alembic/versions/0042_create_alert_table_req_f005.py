"""Create alert table per REQ-F-005 schema.

Revision ID: 0042
Revises: 0041
Create Date: 2026-06-03 00:00:00.000000

Stores both dispatched alerts (channel='email') and silent-log rows
(channel='silent') in a single table for unified audit trail.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0042_create_alert_table"
down_revision = "0042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS alert (
            alert_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            event_id        UUID NOT NULL,
            user_id         UUID NOT NULL,
            tenant_id       UUID NOT NULL,
            rule_id         UUID,
            alert_text      TEXT,
            action_signal   VARCHAR(20),
            confidence      FLOAT,
            sample_size     INT,
            dispatched_at   TIMESTAMPTZ,
            channel         VARCHAR(10) NOT NULL DEFAULT 'silent',
            cost_usd        FLOAT NOT NULL DEFAULT 0,
            status          VARCHAR(50) NOT NULL,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    # Indexes for anti-fatigue gate queries
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_alert_user_tenant_dispatched_at "
        "ON alert (user_id, tenant_id, dispatched_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_alert_event_user_tenant "
        "ON alert (event_id, user_id, tenant_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_alert_tenant_status "
        "ON alert (tenant_id, status)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS alert")
