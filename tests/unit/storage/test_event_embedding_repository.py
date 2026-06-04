"""
Unit tests for EventEmbeddingRepository.

All DB interactions are mocked. No pgvector installation required.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.events.exceptions import PipelineError
from src.storage.implementations.event_embedding_repository import (
    EventEmbeddingRepository,
)
from src.storage.interfaces.i_event_embedding_repository import SimilarEvent


def _make_vector(dim: int = 1536) -> list[float]:
    return [0.01] * dim


@pytest.mark.asyncio
class TestInsert:
    """insert stores a 1536-dimension vector."""

    async def test_insert_stores_vector(self) -> None:
        session = AsyncMock()
        result_mock = MagicMock()
        session.execute = AsyncMock(return_value=result_mock)

        repo = EventEmbeddingRepository(session)
        event_id = uuid.uuid4()
        vector = _make_vector(1536)

        await repo.insert(event_id, vector)

        session.execute.assert_called_once()
        session.flush.assert_called_once()

    async def test_insert_wrong_dimension_raises_pipeline_error(self) -> None:
        session = AsyncMock()
        repo = EventEmbeddingRepository(session)

        with pytest.raises(PipelineError, match="dimension"):
            await repo.insert(uuid.uuid4(), _make_vector(512))

        # No DB call should be made for invalid vectors
        session.execute.assert_not_called()


@pytest.mark.asyncio
class TestFindSimilarHnsw:
    """find_similar_hnsw returns results ordered by cosine distance."""

    async def test_returns_at_most_k_results(self) -> None:
        session = AsyncMock()
        rows = [
            MagicMock(
                event_id=uuid.uuid4(),
                cosine_distance=0.1 * i,
                title=f"Event {i}",
                occurred_at=datetime(2024, 1, i + 1, tzinfo=timezone.utc),
            )
            for i in range(3)
        ]
        result_mock = MagicMock()
        result_mock.mappings.return_value = [
            {
                "event_id": r.event_id,
                "cosine_distance": r.cosine_distance,
                "title": r.title,
                "occurred_at": r.occurred_at,
            }
            for r in rows
        ]
        session.execute = AsyncMock(return_value=result_mock)

        repo = EventEmbeddingRepository(session)
        results = await repo.find_similar_hnsw(_make_vector(), k=5)

        assert len(results) <= 5
        assert all(isinstance(r, SimilarEvent) for r in results)

    async def test_returns_empty_list_when_no_rows(self) -> None:
        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.mappings.return_value = []
        session.execute = AsyncMock(return_value=result_mock)

        repo = EventEmbeddingRepository(session)
        results = await repo.find_similar_hnsw(_make_vector(), k=5)

        assert results == []

    async def test_wrong_query_dimension_raises_pipeline_error(self) -> None:
        session = AsyncMock()
        repo = EventEmbeddingRepository(session)

        with pytest.raises(PipelineError, match="dimension"):
            await repo.find_similar_hnsw(_make_vector(100), k=5)

        session.execute.assert_not_called()

    async def test_sql_uses_limit_bound(self) -> None:
        """Verify LIMIT is forwarded as a bound parameter, not interpolated."""
        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.mappings.return_value = []
        session.execute = AsyncMock(return_value=result_mock)

        repo = EventEmbeddingRepository(session)
        await repo.find_similar_hnsw(_make_vector(), k=3)

        call_args = session.execute.call_args
        # Second positional arg should be the params dict containing k/limit
        params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("params", {})
        assert any(v == 3 for v in (params or {}).values()), \
            "LIMIT value must be passed as a bound parameter"
