"""Layer 3 procedural_pattern table

Revision ID: 0035
Revises: 0034
Create Date: 2026-06-03 00:00:00.000000

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy import DateTime

try:
    from sqlalchemy.dialects.postgresql import TIMESTAMPTZ
except ImportError:
    TIMESTAMPTZ = lambda: DateTime(timezone=True)  # type: ignore[misc,assignment]

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── procedural_pattern ────────────────────────────────────────────────────
    op.create_table(
        "procedural_pattern",
        sa.Column(
            "pattern_id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("pattern_type", sa.String(), nullable=False),
        sa.Column(
            "context_tags",
            ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column("pattern_text", sa.Text(), nullable=False),
        sa.Column(
            "authored_by",
            sa.String(),
            nullable=False,
            server_default=sa.text("'human'"),
        ),
        sa.Column("approved_at", TIMESTAMPTZ(), nullable=True),
        sa.Column("approved_by", UUID(as_uuid=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("success_rate", sa.Float(), nullable=True),
        sa.Column("sample_size", sa.Integer(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column(
            "recommended_for_agents",
            ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column(
            "created_at",
            TIMESTAMPTZ(),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("retracted_at", TIMESTAMPTZ(), nullable=True),
        sa.CheckConstraint(
            "authored_by IN ('human', 'mined')",
            name="ck_procedural_pattern_authored_by",
        ),
    )

    # GIN index on context_tags for overlap queries
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_procedural_pattern_context_tags_gin
        ON procedural_pattern USING GIN (context_tags);
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP INDEX IF EXISTS idx_procedural_pattern_context_tags_gin;"
    )
    op.drop_table("procedural_pattern")
