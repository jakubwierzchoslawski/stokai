"""add cache_entry table

Revision ID: 0032
Revises:
Create Date: 2026-06-03 00:00:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0032"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cache_entry",
        sa.Column("cache_key", sa.Text, primary_key=True),
        sa.Column("data_type", sa.Text, nullable=False),
        sa.Column("entity_id", sa.Text, nullable=True),
        sa.Column("params_hash", sa.Text, nullable=True),
        sa.Column("value", sa.LargeBinary, nullable=False),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_cache_entry_data_type_entity",
        "cache_entry",
        ["data_type", "entity_id", "expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_cache_entry_data_type_entity", table_name="cache_entry")
    op.drop_table("cache_entry")
