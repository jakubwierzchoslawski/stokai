"""golden_dataset_item table for Tier-2 regression golden dataset

Revision ID: 0054
Revises: 0053
Create Date: 2026-06-04 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID, JSONB, TIMESTAMPTZ

revision = "0054"
down_revision = "0053"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "golden_dataset_item",
        sa.Column(
            "item_id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("input", JSONB(), nullable=False),
        sa.Column("expected_output", JSONB(), nullable=False),
        sa.Column("quality_metrics", JSONB(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column(
            "active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("FALSE"),
        ),
        sa.Column("approved_by", UUID(as_uuid=True), nullable=True),
        sa.Column("approved_at", TIMESTAMPTZ(), nullable=True),
        sa.Column(
            "created_at",
            TIMESTAMPTZ(),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint(
            "source IN ('hand_authored', 'admin_override')",
            name="ck_golden_dataset_item_source",
        ),
    )
    # Partial index on active=TRUE for fast lookup of active items
    op.execute(
        """
        CREATE INDEX ix_golden_dataset_item_active
        ON golden_dataset_item (item_id)
        WHERE active = TRUE;
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_golden_dataset_item_active;")
    op.drop_table("golden_dataset_item")
