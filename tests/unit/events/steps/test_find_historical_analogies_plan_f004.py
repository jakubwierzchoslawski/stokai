"""
Unit tests for find_historical_analogies step (PLAN-F-004, TASK-004).

Tests the new AnalogSearchResultSet-based implementation with configurable K,
low_sample flag, timeout enforcement, and PipelineError on missing embedding.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.events.exceptions import PipelineError, StepTimeoutError
from src.events.models import AnalogSearchResult, PipelineContext, RawEvent
from src.events.steps.find_historical_analogies import find_historical_analogies


def _make_ctx(embedding=None, event_id=None) -> PipelineContext:
    return PipelineContext(
        raw_event=RawEvent(
            source_provider="gdelt",
            occurred_at=datetime(2024, 1, 15, tzinfo=timezone.utc),
            raw_payload={"title": "T", "summary": "S"},
        ),
        event_id=event_id or uuid.uuid4(),
        embedding=embedding if embedding is not None else [0.01] * 1536,
    )


def _make_settings(analogy_k: int = 5) -> MagicMock:
    settings = MagicMock()
    settings.ANALOGY_K = analogy_k
    return settings


def _make_analog_result(
    similarity_score: float = 0.9,
    sample_size: int = 6,
    price_change: float | None = 0.05,
) -> AnalogSearchResult:
    return AnalogSearchResult(
        event_id=uuid.uuid4(),
        similarity_score=similarity_score,
        event_title="Historical Event",
        event_date=datetime(2023, 6, 1, tzinfo=timezone.utc),
        intensity=3,
        category=["conflict"],
        price_change_t1d=price_change,
        sample_size=sample_size,
        low_sample=sample_size < 5,
    )


@pytest.mark.asyncio
class TestFindHistoricalAnalogies:
    """Tests for find_historical_analogies step function."""

    async def test_find_analogies_returns_result_set_with_k_results(self) -> None:
        """Returns AnalogSearchResultSet with up to K results."""
        ctx = _make_ctx()
        results = [_make_analog_result(similarity_score=0.9 - 0.05 * i) for i in range(5)]
        repo = AsyncMock()
        repo.search_similar = AsyncMock(return_value=results)
        settings = _make_settings(analogy_k=5)

        updated_ctx = await find_historical_analogies(ctx, repo, settings)

        assert updated_ctx.analogy_result_set is not None
        assert len(updated_ctx.analogy_result_set.results) == 5
        assert updated_ctx.analogy_result_set.k_requested == 5

    async def test_find_analogies_sets_low_sample_true_when_fewer_than_5_outcomes(self) -> None:
        """low_sample=True on result set when any result has low_sample=True."""
        ctx = _make_ctx()
        results = [
            _make_analog_result(sample_size=2),
            _make_analog_result(sample_size=3),
        ]
        repo = AsyncMock()
        repo.search_similar = AsyncMock(return_value=results)
        settings = _make_settings(analogy_k=5)

        updated_ctx = await find_historical_analogies(ctx, repo, settings)

        assert updated_ctx.analogy_result_set is not None
        assert updated_ctx.analogy_result_set.low_sample is True

    async def test_find_analogies_raises_pipeline_error_if_no_embedding(self) -> None:
        """Raise PipelineError when ctx.embedding is None."""
        ctx = _make_ctx(embedding=None)
        ctx.embedding = None
        repo = AsyncMock()
        settings = _make_settings()

        with pytest.raises(PipelineError, match="embedding"):
            await find_historical_analogies(ctx, repo, settings)

    async def test_find_analogies_raises_step_timeout_error(self) -> None:
        """Raise StepTimeoutError when search exceeds timeout."""
        ctx = _make_ctx()

        async def slow_search(embedding, k):
            await asyncio.sleep(3)
            return []

        repo = AsyncMock()
        repo.search_similar = slow_search
        settings = _make_settings()

        with pytest.raises(StepTimeoutError):
            await find_historical_analogies(ctx, repo, settings, timeout_seconds=0.05)

    async def test_find_analogies_uses_configurable_k(self) -> None:
        """Set analogy_k=10; assert repo called with k=10."""
        ctx = _make_ctx()
        repo = AsyncMock()
        repo.search_similar = AsyncMock(return_value=[])
        settings = _make_settings(analogy_k=10)

        await find_historical_analogies(ctx, repo, settings)

        repo.search_similar.assert_called_once_with([0.01] * 1536, k=10)

    async def test_find_analogies_sets_source_event_id_on_result_set(self) -> None:
        """result_set.source_event_id matches ctx.event_id."""
        event_id = uuid.uuid4()
        ctx = _make_ctx(event_id=event_id)
        repo = AsyncMock()
        repo.search_similar = AsyncMock(return_value=[])
        settings = _make_settings()

        updated_ctx = await find_historical_analogies(ctx, repo, settings)

        assert updated_ctx.analogy_result_set is not None
        assert updated_ctx.analogy_result_set.source_event_id == event_id

    async def test_find_analogies_low_sample_false_when_all_have_5_outcomes(self) -> None:
        """low_sample=False when all results have sample_size >= 5."""
        ctx = _make_ctx()
        results = [_make_analog_result(sample_size=5) for _ in range(3)]
        repo = AsyncMock()
        repo.search_similar = AsyncMock(return_value=results)
        settings = _make_settings()

        updated_ctx = await find_historical_analogies(ctx, repo, settings)

        assert updated_ctx.analogy_result_set is not None
        assert updated_ctx.analogy_result_set.low_sample is False
