"""
IEventEmbeddingRepository — protocol for event_embedding table persistence
and HNSW vector search.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel
from typing_extensions import Protocol, runtime_checkable


class SimilarEvent(BaseModel):
    """Result row returned by HNSW approximate nearest-neighbour search."""

    event_id: UUID
    cosine_distance: float
    title: str
    occurred_at: datetime


@runtime_checkable
class IEventEmbeddingRepository(Protocol):
    """Repository interface for the event_embedding table."""

    async def insert(self, event_id: UUID, embedding: list[float]) -> None:
        """Store a 1536-dimension embedding vector for the given event.

        Args:
            event_id: PK of the geo_event row this embedding belongs to.
            embedding: Dense float vector of exactly 1536 dimensions.
        """
        ...

    async def find_similar_hnsw(
        self, vector: list[float], k: int = 5
    ) -> list[SimilarEvent]:
        """Return the top-k most similar events using the HNSW index.

        Results are ordered by cosine distance ascending (most similar first).

        Args:
            vector: Query vector of exactly 1536 dimensions.
            k: Maximum number of results to return.

        Returns:
            List of SimilarEvent objects, length <= k.
        """
        ...
