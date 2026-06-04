"""Create event_embedding table and HNSW index for pgvector cosine search.

Revision ID: 0042
Revises: 0041
Create Date: 2026-06-03 00:00:00.000000

PLAN-F-004: Implements storage for VECTOR(1536) event embeddings produced by
OpenAI text-embedding-3-small. The HNSW index enables sub-second approximate
nearest-neighbour cosine search (find_historical_analogies step, REQ-N-001).

NOTE: The HNSW index only becomes useful after PLAN-F-031 cold-start seeding
completes. Until that seeding run populates historical event embeddings, the
index exists but provides no analogy results.

Migration is non-destructive and idempotent (IF NOT EXISTS throughout).
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0042"
down_revision = "0041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Ensure pgvector extension is enabled (idempotent)
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # Create event_embedding table if it does not already exist
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS event_embedding (
            event_id   UUID PRIMARY KEY REFERENCES geo_event(event_id) ON DELETE CASCADE,
            embedding  vector(1536) NOT NULL,
            created_at TIMESTAMPTZ  NOT NULL DEFAULT NOW()
        )
        """
    )

    # Create HNSW index for cosine distance searches via pgvector <=> operator.
    # vector_cosine_ops requires pgvector 0.5+.
    # This index becomes useful after PLAN-F-031 cold-start seeding completes.
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_event_embedding_hnsw
        ON event_embedding
        USING hnsw (embedding vector_cosine_ops)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_event_embedding_hnsw")
    op.execute("DROP TABLE IF EXISTS event_embedding")
