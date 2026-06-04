"""
Alembic migration: add seeding_checkpoint table.

Revision: 0031
Description: Creates the seeding_checkpoint table used by the cold-start seeding
pipeline to track per-batch progress and enable resumability across container restarts.
This implements the 12-factor pattern for seeding state (DB, not in-memory or files).
"""
from alembic import op
import sqlalchemy as sa

# Alembic revision identifiers
revision = "0031"
down_revision = None  # Update to previous migration revision when chained
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create seeding_checkpoint table for cold-start pipeline resumability."""
    op.create_table(
        "seeding_checkpoint",
        sa.Column("batch_key", sa.Text(), nullable=False, primary_key=True),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("events_seeded", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("embeddings_done", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )

    # Index on state for efficient pending-batch queries
    op.create_index(
        "ix_seeding_checkpoint_state",
        "seeding_checkpoint",
        ["state"],
    )


def downgrade() -> None:
    """Drop seeding_checkpoint table and associated indexes."""
    op.drop_index("ix_seeding_checkpoint_state", table_name="seeding_checkpoint")
    op.drop_table("seeding_checkpoint")
