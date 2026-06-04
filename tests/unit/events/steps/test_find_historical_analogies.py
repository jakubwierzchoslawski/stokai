"""
Unit tests for the find_historical_analogies step.

Updated for PLAN-F-004: step now uses EventEmbeddingRepository protocol
(search_similar) and returns AnalogSearchResultSet.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.events.models import AnalogSearchResult, PipelineContext, RawEvent
from src.events.steps.find_historical_analogies import find_historical_analogies


def _make_ctx(event_id=None) -> PipelineContext:
    eid = event_id or uuid.uuid4()
    return PipelineContext(
        raw_event=RawEvent(
            source_provider="gdelt",
            occurred_at=datetime(2024, 1, 15, tzinfo=timezone.utc),
            raw_payload={"title": "T", "summary": "S"},
        ),
        event_id=eid,
        embedding=[0.01] * 1536,
    )


def _make_analog_result(
    event_id=None,
    similarity_score=0.9,
    sample_size=6,
) -> AnalogSearchResult:
    return AnalogSearchResult(
        event_id=event_id or uuid.uuid4(),
        similarity_score=similarity_score,
        event_title="Historical Event",
        event_date=datetime(2023, 6, 1, tzinfo=timezone.utc),
        intensity=3,
        category=["conflict"],
        price_change_t1d=0.05,
        sample_size=sample_size,
        low_sample=sample_size < 5,
    )


def _make_settings(k: int = 5) -> MagicMock:
    s = MagicMock()
    s.ANALOGY_K = k
    return s


@pytest.mark.asyncio
class TestFindHistoricalAnalogies:

    async def test_returns_up_to_5_sorted_by_similarity(self) -> None:
        ctx = _make_ctx()
        similars = [_make_analog_result(similarity_score=0.9 - 0.1 * i) for i in range(1, 4)]
        embedding_repo = AsyncMock()
        embedding_repo.search_similar = AsyncMock(return_value=similars)
        settings = _make_settings()

        result = await find_historical_analogies(ctx, embedding_repo, settings)

        assert result.analogy_result_set is not None
        assert len(result.analogy_result_set.results) <= 5
        scores = [r.similarity_score for r in result.analogy_result_set.results]
        assert scores == sorted(scores, reverse=True)

    async def test_empty_repository_result_gives_empty_results(self) -> None:
        ctx = _make_ctx()
        embedding_repo = AsyncMock()
        embedding_repo.search_similar = AsyncMock(return_value=[])
        settings = _make_settings()

        result = await find_historical_analogies(ctx, embedding_repo, settings)

        assert result.analogy_result_set is not None
        assert result.analogy_result_set.results == []

    async def test_each_analogy_contains_required_fields(self) -> None:
        ctx = _make_ctx()
        similars = [_make_analog_result()]
        embedding_repo = AsyncMock()
        embedding_repo.search_similar = AsyncMock(return_value=similars)
        settings = _make_settings()

        result = await find_historical_analogies(ctx, embedding_repo, settings)

        for analogy in result.analogy_result_set.results:
            assert analogy.event_id is not None
            assert analogy.event_title is not None
            assert analogy.event_date is not None
            assert analogy.similarity_score is not None

    async def test_low_sample_set_true_when_below_threshold(self) -> None:
        ctx = _make_ctx()
        similars = [_make_analog_result(sample_size=2)]
        embedding_repo = AsyncMock()
        embedding_repo.search_similar = AsyncMock(return_value=similars)
        settings = _make_settings()

        result = await find_historical_analogies(ctx, embedding_repo, settings)

        assert result.analogy_result_set.low_sample is True
