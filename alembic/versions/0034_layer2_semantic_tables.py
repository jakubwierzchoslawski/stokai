"""Layer 2 semantic tables with pgvector HNSW index

Revision ID: 0034
Revises: 0033
Create Date: 2026-06-03 00:00:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, TIMESTAMPTZ, ARRAY

# revision identifiers, used by Alembic.
revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Ensure pgvector extension is present (may already be enabled by init.sql)
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    # ── semantic_fact_staging — pre-gate holding area ──────────────────────
    op.create_table(
        "semantic_fact_staging",
        sa.Column(
            "staging_id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("entity_id", UUID(as_uuid=True), nullable=False),
        sa.Column("fact_text", sa.Text(), nullable=False),
        sa.Column("evidence_count", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column(
            "source_invocation_ids",
            ARRAY(UUID(as_uuid=True)),
            server_default=sa.text("'{}'::uuid[]"),
        ),
        sa.Column(
            "created_at",
            TIMESTAMPTZ(),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )

    # ── semantic_fact — committed facts (evidence_count >= 3) ──────────────
    op.create_table(
        "semantic_fact",
        sa.Column(
            "fact_id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("entity_id", UUID(as_uuid=True), nullable=False),
        sa.Column("fact_text", sa.Text(), nullable=False),
        # Vector column — raw DDL since SA doesn't know the vector type natively
        # without pgvector's SA extension installed
        sa.Column("evidence_count", sa.Integer(), nullable=False),
        sa.Column(
            "last_confirmed",
            TIMESTAMPTZ(),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("decayed_at", TIMESTAMPTZ(), nullable=True),
        sa.Column("retracted_at", TIMESTAMPTZ(), nullable=True),
        sa.Column("retracted_by", UUID(as_uuid=True), nullable=True),
        sa.Column(
            "source_invocations",
            ARRAY(UUID(as_uuid=True)),
            server_default=sa.text("'{}'::uuid[]"),
        ),
        sa.Column(
            "created_at",
            TIMESTAMPTZ(),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )

    # Add embedding column with vector type via raw DDL
    op.execute(
        "ALTER TABLE semantic_fact ADD COLUMN IF NOT EXISTS embedding vector(1536);"
    )

    # HNSW index for cosine similarity search on embeddings
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_semantic_fact_embedding_hnsw
        ON semantic_fact
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64);
        """
    )

    # GIN index on source_invocations UUID[] array for containment queries
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_semantic_fact_source_invocations_gin
        ON semantic_fact USING GIN (source_invocations);
        """
    )

    # GIN index on source_invocation_ids in staging table
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_semantic_fact_staging_source_invocation_ids_gin
        ON semantic_fact_staging USING GIN (source_invocation_ids);
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP INDEX IF EXISTS idx_semantic_fact_staging_source_invocation_ids_gin;"
    )
    op.execute(
        "DROP INDEX IF EXISTS idx_semantic_fact_source_invocations_gin;"
    )
    op.execute(
        "DROP INDEX IF EXISTS idx_semantic_fact_embedding_hnsw;"
    )
    op.drop_table("semantic_fact")
    op.drop_table("semantic_fact_staging")
