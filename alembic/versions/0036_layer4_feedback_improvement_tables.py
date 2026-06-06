"""Layer 4 user_feedback and improvement_proposal tables

Revision ID: 0036
Revises: 0035
Create Date: 2026-06-03 00:00:00.000000

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, ARRAY, JSONB
from sqlalchemy import DateTime

try:
    from sqlalchemy.dialects.postgresql import TIMESTAMPTZ
except ImportError:
    TIMESTAMPTZ = lambda: DateTime(timezone=True)  # type: ignore[misc,assignment]

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── user_feedback ─────────────────────────────────────────────────────────
    op.create_table(
        "user_feedback",
        sa.Column(
            "feedback_id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("report_id", UUID(as_uuid=True), nullable=True),
        sa.Column("recommendation_id", UUID(as_uuid=True), nullable=True),
        sa.Column("feedback_type", sa.String(), nullable=False),
        sa.Column("feedback_text", sa.Text(), nullable=True),
        sa.Column("user_edit", sa.Text(), nullable=True),
        sa.Column("reviewer_id", UUID(as_uuid=True), nullable=True),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column(
            "submitted_at",
            TIMESTAMPTZ(),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint(
            "feedback_type IN ('thumbs_up','thumbs_down','approve','edit_approve','reject','reject_with_feedback')",
            name="ck_user_feedback_feedback_type",
        ),
        sa.CheckConstraint(
            "source IN ('hil_action','in_app')",
            name="ck_user_feedback_source",
        ),
    )

    # ── improvement_proposal ──────────────────────────────────────────────────
    op.create_table(
        "improvement_proposal",
        sa.Column(
            "proposal_id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("proposal_type", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("proposed_changes", JSONB(), nullable=True),
        sa.Column(
            "status",
            sa.String(),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("reviewed_by", UUID(as_uuid=True), nullable=True),
        sa.Column("reviewed_at", TIMESTAMPTZ(), nullable=True),
        sa.Column(
            "created_at",
            TIMESTAMPTZ(),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "source_feedback_ids",
            ARRAY(UUID(as_uuid=True)),
            server_default=sa.text("'{}'::uuid[]"),
        ),
        sa.CheckConstraint(
            "proposal_type IN ('prompt_adjustment','threshold_adjustment')",
            name="ck_improvement_proposal_proposal_type",
        ),
        sa.CheckConstraint(
            "status IN ('pending','approved','rejected')",
            name="ck_improvement_proposal_status",
        ),
    )


def downgrade() -> None:
    op.drop_table("improvement_proposal")
    op.drop_table("user_feedback")
