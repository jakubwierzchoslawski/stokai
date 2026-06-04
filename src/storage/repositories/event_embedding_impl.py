"""
EventEmbeddingRepositoryImpl — SQLAlchemy 2.0 async implementation (PLAN-F-004).

Implements save(), get_by_event_id(), and search_similar() against the
event_embedding table with pgvector HNSW cosine index.

Security: all query parameters are bound; no string interpolation.
"""
from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.events.models import AnalogSearchResult

_EXPECTED_DIM = 1536
_LOW_SAMPLE_THRESHOLD = 5

logger = logging.getLogger(__name__)


class EventEmbeddingRepositoryImpl:
    """SQLAlchemy 2.0 async implementation of EventEmbeddingRepository protocol."""

    def __init__(self, session: AsyncSession) -> None:
        """Inject the SQLAlchemy async session (DIP)."""
        self._session = session

    async def save(self, event_id: UUID, embedding: list[float]) -> None:
        """Persist embedding for event_id; silently no-ops on duplicate.

        Uses INSERT ... ON CONFLICT (event_id) DO NOTHING for idempotency.
        Embeddings are stored once and never re-fetched (Principle 2).
        """
        stmt = text(
            """
            INSERT INTO event_embedding (event_id, embedding)
            VALUES (:event_id, :embedding)
            ON CONFLICT (event_id) DO NOTHING
            """
        )
        await self._session.execute(
            stmt,
            {
                "event_id": str(event_id),
                "embedding": str(embedding),  # pgvector accepts '[0.1, ...]' format
            },
        )
        await self._session.flush()
        logger.debug("Saved embedding for event_id=%s", event_id)

    async def get_by_event_id(self, event_id: UUID) -> list[float] | None:
        """Return the stored embedding vector, or None if not found."""
        stmt = text(
            """
            SELECT embedding
            FROM event_embedding
            WHERE event_id = :event_id
            """
        )
        result = await self._session.execute(stmt, {"event_id": str(event_id)})
        row = result.fetchone()
        if row is None:
            return None
        # pgvector returns embedding as a list or string depending on adapter
        raw = row[0]
        if isinstance(raw, str):
            import json
            return json.loads(raw.replace("(", "[").replace(")", "]"))
        return list(raw)

    async def search_similar(
        self, embedding: list[float], k: int
    ) -> list[AnalogSearchResult]:
        """Execute HNSW cosine search with price outcome statistics.

        Joins geo_event for event metadata and left-joins event_exposure for
        price_change_t1d. sample_size counts rows with non-null price_change_t1d.

        All parameters are bound (parameterised query, never interpolated).
        """
        stmt = text(
            """
            SELECT
                ge.event_id,
                ge.title AS event_title,
                ge.occurred_at AS event_date,
                ge.intensity,
                ge.category,
                (1 - (ee.embedding <=> CAST(:query_vec AS vector))) AS similarity_score,
                ee2.price_change_t1d,
                COUNT(ee2.price_change_t1d) OVER (PARTITION BY TRUE) AS sample_size
            FROM event_embedding ee
            JOIN geo_event ge ON ge.event_id = ee.event_id
            LEFT JOIN event_exposure ee2 ON ee2.event_id = ee.event_id
            WHERE ee.event_id != :source_event_id
            ORDER BY ee.embedding <=> CAST(:query_vec AS vector)
            LIMIT :k
            """
        )
        # source_event_id is a no-op placeholder; actual filtering happens in
        # embed_event step (we don't have it here — use a nil UUID that won't
        # match any real event unless caller sets it)
        result = await self._session.execute(
            stmt,
            {
                "query_vec": str(embedding),
                "source_event_id": "00000000-0000-0000-0000-000000000000",
                "k": k,
            },
        )
        rows = result.mappings().all()

        sample_size = int(rows[0]["sample_size"]) if rows else 0

        analogy_results: list[AnalogSearchResult] = []
        for row in rows:
            row_sample_size = int(row["sample_size"])
            low_sample = row_sample_size < _LOW_SAMPLE_THRESHOLD
            analogy_results.append(
                AnalogSearchResult(
                    event_id=row["event_id"],
                    similarity_score=float(row["similarity_score"]),
                    event_title=row["event_title"],
                    event_date=row["event_date"],
                    intensity=int(row["intensity"]),
                    category=row["category"] if isinstance(row["category"], list) else list(row["category"]),
                    price_change_t1d=row["price_change_t1d"],
                    sample_size=row_sample_size,
                    low_sample=low_sample,
                )
            )

        return analogy_results
