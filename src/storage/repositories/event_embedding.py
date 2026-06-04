"""
EventEmbeddingRepository protocol (PLAN-F-004, TASK-002).

Protocol-driven interface for event_embedding table operations including
pgvector HNSW cosine similarity search over historical events.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable
from uuid import UUID

from src.events.models import AnalogSearchResult


@runtime_checkable
class EventEmbeddingRepository(Protocol):
    """Repository protocol for event_embedding table access."""

    async def save(self, event_id: UUID, embedding: list[float]) -> None:
        """Persist an embedding vector for the given event.

        Idempotent: uses INSERT ... ON CONFLICT DO NOTHING so repeated calls
        with the same event_id are safe (Principle 2 — Infinite TTL).

        Args:
            event_id: PK of the geo_event this embedding belongs to.
            embedding: Dense float vector of exactly 1536 dimensions.
        """
        ...

    async def get_by_event_id(self, event_id: UUID) -> list[float] | None:
        """Return the stored embedding for event_id, or None if not found."""
        ...

    async def search_similar(
        self, embedding: list[float], k: int
    ) -> list[AnalogSearchResult]:
        """Execute pgvector HNSW cosine search and return top-k analogies.

        Joins against geo_event for metadata and left-joins event_exposure for
        price_change_t1d. Sets sample_size to count of non-null price outcomes.
        Sets low_sample=True when sample_size < 5.

        All query parameters are bound — never string-interpolated.

        Args:
            embedding: Query vector of 1536 dimensions.
            k: Maximum number of results to return.

        Returns:
            List of AnalogSearchResult sorted by similarity_score descending
            (most similar first).
        """
        ...
