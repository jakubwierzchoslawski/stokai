"""Alembic migration: add brief table for morning brief workflow.

Creates the `brief` table to persist morning brief outputs, including HIL
status tracking, cost tracking, and multi-tenancy via tenant_id.

Revision ID: 0058_add_brief_table_morning_brief
Revises: 017_scoring_engine
Branch labels: None
Depends on: None

PLAN-F-006 TASK-001
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0058_add_brief_table_morning_brief"
down_revision = "017_scoring_engine"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the brief table and supporting indexes."""
    op.create_table(
        "brief",
        sa.Column(
            "brief_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        # legacy column; defaults to 'event_deep_dive'
        sa.Column(
            "type",
            sa.String(64),
            nullable=False,
            server_default=sa.text("'event_deep_dive'"),
        ),
        # extended column for morning brief / other workflow types
        sa.Column(
            "brief_type",
            sa.String(64),
            nullable=True,
            server_default=sa.text("'event_deep_dive'"),
        ),
        # FK → geo_event (nullable; only set for event_deep_dive briefs)
        sa.Column(
            "event_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        # Morning brief owner
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        # Workflow that produced this brief
        sa.Column(
            "workflow_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        # Multi-tenancy column — every query MUST include tenant_id
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        # Full brief content as JSONB (HTML body stored in content['body'])
        sa.Column(
            "content",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "confidence",
            sa.Float,
            nullable=False,
            server_default=sa.text("0.0"),
        ),
        # HIL status: none|pending|approved|rejected|timed_out|not_required
        sa.Column(
            "hil_status",
            sa.String(16),
            nullable=True,
            server_default=sa.text("'none'"),
        ),
        # When the email was dispatched; NULL means not yet sent
        sa.Column(
            "sent_at",
            postgresql.TIMESTAMPTZ,
            nullable=True,
        ),
        sa.Column(
            "cost_usd",
            sa.Float,
            nullable=False,
            server_default=sa.text("0.0"),
        ),
        sa.Column(
            "cost_limited",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "hil_reviewed",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "hil_approved",
            sa.Boolean,
            nullable=True,
        ),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMPTZ,
            nullable=True,
            server_default=sa.text("now()"),
        ),
    )

    # Composite index for tenant + event lookups (event_deep_dive briefs)
    op.create_index(
        "idx_brief_tenant_event",
        "brief",
        ["tenant_id", "event_id"],
    )

    # Composite index for morning brief lookups by user+tenant+type
    op.create_index(
        "idx_brief_user_tenant_type",
        "brief",
        ["user_id", "tenant_id", "brief_type"],
    )

    # Index for HIL status queries (timeout handler scans hil_status=pending)
    op.create_index(
        "idx_brief_hil_status",
        "brief",
        ["hil_status", "tenant_id"],
    )


def downgrade() -> None:
    """Drop the brief table and its indexes."""
    op.drop_index("idx_brief_hil_status", table_name="brief")
    op.drop_index("idx_brief_user_tenant_type", table_name="brief")
    op.drop_index("idx_brief_tenant_event", table_name="brief")
    op.drop_table("brief")
