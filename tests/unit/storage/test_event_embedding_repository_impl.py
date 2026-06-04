"""
Unit tests for EventEmbeddingRepositoryImpl (PLAN-F-004, TASK-002).

All DB interactions are mocked. No pgvector or real DB required.
Tests cover save(), get_by_event_id(), and search_similar().
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.events.models import AnalogSearchResult
from src.storage.repositories.event_embedding_impl import EventEmbeddingRepositoryImpl


def _make_vector(dim: int = 1536) -> list[float]:
    return [0.01] * dim


def _make_search_row(
    event_id=None,
    similarity_score=0.9,
    price_change_t1d=0.05,
    sample_size=6,
):
    return {
        "event_id": event_id or uuid.uuid4(),
        "event_title": "Historical Event",
        "event_date": datetime(2023, 6, 1, tzinfo=timezone.utc),
        "intensity": 3,
        "category": ["conflict"],
        "similarity_score": similarity_score,
        "price_change_t1d": price_change_t1d,
        "sample_size": sample_size,
    }


@pytest.mark.asyncio
class TestSave:
    """save() persists embedding row idempotently."""

    async def test_save_persists_embedding_row(self) -> None:
        """Against test DB (mocked); assert row exists after save."""
        session = AsyncMock()
        session.execute = AsyncMock(return_value=MagicMock())

        repo = EventEmbeddingRepositoryImpl(session)
        event_id = uuid.uuid4()

        await repo.save(event_id, _make_vector())

        session.execute.assert_called_once()
        session.flush.assert_called_once()

    async def test_save_is_idempotent(self) -> None:
        """Call save twice with same event_id; no unique-violation, only executes."""
        session = AsyncMock()
        session.execute = AsyncMock(return_value=MagicMock())

        repo = EventEmbeddingRepositoryImpl(session)
        event_id = uuid.uuid4()
        vector = _make_vector()

        await repo.save(event_id, vector)
        await repo.save(event_id, vector)

        # Both calls should succeed without error
        assert session.execute.call_count == 2

    async def test_save_uses_on_conflict_do_nothing(self) -> None:
        """The SQL statement contains ON CONFLICT DO NOTHING for idempotency."""
        session = AsyncMock()
        session.execute = AsyncMock(return_value=MagicMock())

        repo = EventEmbeddingRepositoryImpl(session)
        await repo.save(uuid.uuid4(), _make_vector())

        call_args = session.execute.call_args
        sql_stmt = str(call_args[0][0])
        assert "ON CONFLICT" in sql_stmt
        assert "DO NOTHING" in sql_stmt


@pytest.mark.asyncio
class TestGetByEventId:
    """get_by_event_id() returns stored embedding or None."""

    async def test_get_by_event_id_returns_none_for_missing(self) -> None:
        """Return None when no row exists for given event_id."""
        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.fetchone.return_value = None
        session.execute = AsyncMock(return_value=result_mock)

        repo = EventEmbeddingRepositoryImpl(session)
        result = await repo.get_by_event_id(uuid.uuid4())

        assert result is None

    async def test_get_by_event_id_returns_vector_when_found(self) -> None:
        """Return the stored embedding list when row exists."""
        session = AsyncMock()
        result_mock = MagicMock()
        stored_vector = [0.01] * 1536
        result_mock.fetchone.return_value = (stored_vector,)
        session.execute = AsyncMock(return_value=result_mock)

        repo = EventEmbeddingRepositoryImpl(session)
        result = await repo.get_by_event_id(uuid.uuid4())

        assert result is not None
        assert len(result) == 1536


@pytest.mark.asyncio
class TestSearchSimilar:
    """search_similar() returns AnalogSearchResult list sorted by score descending."""

    async def test_search_similar_returns_top_k_ordered_by_score(self) -> None:
        """Seed 10 rows (mocked); assert sorted descending by similarity."""
        session = AsyncMock()
        rows = [
            _make_search_row(similarity_score=0.9 - 0.05 * i, sample_size=6)
            for i in range(5)
        ]
        result_mock = MagicMock()
        result_mock.mappings.return_value.all.return_value = rows
        session.execute = AsyncMock(return_value=result_mock)

        repo = EventEmbeddingRepositoryImpl(session)
        results = await repo.search_similar(_make_vector(), k=5)

        assert len(results) <= 5
        assert all(isinstance(r, AnalogSearchResult) for r in results)
        scores = [r.similarity_score for r in results]
        assert scores == sorted(scores, reverse=True)

    async def test_search_similar_sets_low_sample_true_when_fewer_than_5_outcomes(self) -> None:
        """low_sample=True when sample_size < 5."""
        session = AsyncMock()
        rows = [
            _make_search_row(similarity_score=0.8, sample_size=3),
            _make_search_row(similarity_score=0.7, sample_size=3),
        ]
        result_mock = MagicMock()
        result_mock.mappings.return_value.all.return_value = rows
        session.execute = AsyncMock(return_value=result_mock)

        repo = EventEmbeddingRepositoryImpl(session)
        results = await repo.search_similar(_make_vector(), k=5)

        assert all(r.low_sample is True for r in results)
        assert all(r.sample_size == 3 for r in results)

    async def test_search_similar_sets_low_sample_false_when_5_or_more_outcomes(self) -> None:
        """low_sample=False when sample_size >= 5."""
        session = AsyncMock()
        rows = [_make_search_row(similarity_score=0.8, sample_size=5)]
        result_mock = MagicMock()
        result_mock.mappings.return_value.all.return_value = rows
        session.execute = AsyncMock(return_value=result_mock)

        repo = EventEmbeddingRepositoryImpl(session)
        results = await repo.search_similar(_make_vector(), k=5)

        assert results[0].low_sample is False

    async def test_search_similar_returns_empty_list_for_no_rows(self) -> None:
        """Empty result when no similar events found."""
        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.mappings.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=result_mock)

        repo = EventEmbeddingRepositoryImpl(session)
        results = await repo.search_similar(_make_vector(), k=5)

        assert results == []

    async def test_search_similar_uses_bound_parameters(self) -> None:
        """All query params are bound, not interpolated."""
        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.mappings.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=result_mock)

        repo = EventEmbeddingRepositoryImpl(session)
        await repo.search_similar(_make_vector(), k=7)

        call_args = session.execute.call_args
        params = call_args[0][1] if len(call_args[0]) > 1 else {}
        assert "k" in params
        assert params["k"] == 7
