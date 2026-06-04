"""
EventEmbeddingRepository — SQLAlchemy 2.0 async implementation of IEventEmbeddingRepository.

Uses pgvector's <=> cosine distance operator with the HNSW index.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.events.exceptions import PipelineError
from src.storage.interfaces.i_event_embedding_repository import (
    IEventEmbeddingRepository,
    SimilarEvent,
)

_EXPECTED_DIM = 1536


class EventEmbeddingRepository:
    """Async SQLAlchemy repository for the event_embedding table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── Validation ────────────────────────────────────────────────────────────

    @staticmethod
    def _validate_dimension(vector: list[float], label: str = "embedding") -> None:
        if len(vector) != _EXPECTED_DIM:
            raise PipelineError(
                f"{label} dimension mismatch: expected {_EXPECTED_DIM}, got {len(vector)}"
            )

    # ── IEventEmbeddingRepository ─────────────────────────────────────────────

    async def insert(self, event_id: UUID, embedding: list[float]) -> None:
        """Store a 1536-dimension vector for the given event."""
        self._validate_dimension(embedding)

        stmt = text(
            """
            INSERT INTO event_embedding (event_id, embedding)
            VALUES (:event_id, :embedding)
            ON CONFLICT (event_id) DO UPDATE
                SET embedding = EXCLUDED.embedding
            """
        )
        await self._session.execute(
            stmt,
            {
                "event_id": event_id,
                "embedding": str(embedding),  # pgvector accepts '[0.1, 0.2, ...]' format
            },
        )
        await self._session.flush()

    async def find_similar_hnsw(
        self, vector: list[float], k: int = 5
    ) -> list[SimilarEvent]:
        """Return top-k similar events using the HNSW cosine index."""
        self._validate_dimension(vector, "query vector")

        stmt = text(
            """
            SELECT
                ee.event_id,
                (ee.embedding <=> :vector::vector) AS cosine_distance,
                ge.title,
                ge.occurred_at
            FROM event_embedding ee
            JOIN geo_event ge ON ge.event_id = ee.event_id
            ORDER BY cosine_distance ASC
            LIMIT :k
            """
        )
        result = await self._session.execute(
            stmt,
            {
                "vector": str(vector),
                "k": k,
            },
        )
        rows = result.mappings()
        return [SimilarEvent(**row) for row in rows]
