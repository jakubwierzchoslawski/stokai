"""Alembic migration: add timeout_at and partial_result to workflow_run.

Adds:
  - timeout_at TIMESTAMPTZ NULL — populated by save_timeout() when
    Celery SoftTimeLimitExceeded fires on any Mode B workflow.
  - partial_result BOOLEAN NOT NULL DEFAULT FALSE — set to TRUE on timeout,
    remains FALSE for completed runs.

Revision ID: 019_add_workflow_run_timeout_fields
Revises: 018_geo_modifier
Branch labels: None
Depends on: None

PLAN-N-002 TASK-002
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers
revision = "019_add_workflow_run_timeout_fields"
down_revision = "018_geo_modifier"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add timeout_at and partial_result columns to workflow_run."""
    op.add_column(
        "workflow_run",
        sa.Column(
            "timeout_at",
            sa.TIMESTAMP(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "workflow_run",
        sa.Column(
            "partial_result",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("FALSE"),
        ),
    )


def downgrade() -> None:
    """Drop timeout_at and partial_result columns from workflow_run."""
    op.drop_column("workflow_run", "partial_result")
    op.drop_column("workflow_run", "timeout_at")
