"""Unit tests for ExposureScoreStep (TASK-007, TDD).

Tests written before implementation.
Covers: AC-001.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from src.event_pipeline.pipeline_state import (
    EventCategory,
    PipelineState,
    RawEventPayload,
    RawEventSource,
)


def _make_state(tickers: list[str] | None = None) -> PipelineState:
    tenant_id = uuid.uuid4()
    portfolio_id = str(uuid.uuid4())
    return PipelineState(
        raw_event_id=uuid.uuid4(),
        tenant_id=tenant_id,
        payload=RawEventPayload(
            source=RawEventSource.GDELT,
            raw_payload={"title": "event"},
            detected_at=datetime.now(timezone.utc),
            tenant_id=tenant_id,
        ),
        event_description="Conflict event",
        category=EventCategory.GEOPOLITICAL_CONFLICT,
        intensity=3,
        tickers=tickers or ["AAPL"],
        exposure_map={portfolio_id: 0.0},
    )


class TestExposureScoreReusessCachedHash:
    """test_exposure_score_reuses_cached_hash"""

    @pytest.mark.asyncio
    async def test_exposure_score_reuses_cached_hash(self):
        """When inputs_hash matches existing record, score is reused (no recompute)."""
        from src.event_pipeline.steps.s07_exposure_score import ExposureScoreStep

        existing_score = 0.72
        # Mock: DB returns an existing score with matching inputs_hash
        repo_mock = AsyncMock()
        repo_mock.get_portfolio_holdings = AsyncMock(return_value={"AAPL": 0.5, "GOOGL": 0.5})
        repo_mock.get_event_score_by_hash = AsyncMock(return_value=existing_score)
        repo_mock.write_event_score = AsyncMock()

        step = ExposureScoreStep(repo=repo_mock)
        state = _make_state()

        result = await step.execute(state)

        # Score should equal the cached value
        for score in result.exposure_map.values():
            assert score == existing_score

        # write_event_score should NOT be called (reusing cached)
        repo_mock.write_event_score.assert_not_called()


class TestExposureScoreComputesAndWritesNewScore:
    """test_exposure_score_computes_and_writes_new_score"""

    @pytest.mark.asyncio
    async def test_exposure_score_computes_and_writes_new_score(self):
        """When no hash match, new score is computed and written to DB."""
        from src.event_pipeline.steps.s07_exposure_score import ExposureScoreStep

        repo_mock = AsyncMock()
        repo_mock.get_portfolio_holdings = AsyncMock(return_value={"AAPL": 0.6, "TSLA": 0.4})
        repo_mock.get_event_score_by_hash = AsyncMock(return_value=None)  # cache miss
        repo_mock.write_event_score = AsyncMock()

        step = ExposureScoreStep(repo=repo_mock)
        state = _make_state(tickers=["AAPL"])

        result = await step.execute(state)

        repo_mock.write_event_score.assert_called_once()
        # Score must be non-zero (AAPL is in portfolio with weight 0.6, intensity=3)
        for score in result.exposure_map.values():
            assert score > 0.0


class TestExposureScorePreservesHistoricalRecord:
    """test_exposure_score_preserves_historical_record"""

    @pytest.mark.asyncio
    async def test_exposure_score_preserves_historical_record(self):
        """write_event_score always inserts (not updates) — old record preserved (P-03)."""
        from src.event_pipeline.steps.s07_exposure_score import ExposureScoreStep

        repo_mock = AsyncMock()
        repo_mock.get_portfolio_holdings = AsyncMock(return_value={"AAPL": 1.0})
        repo_mock.get_event_score_by_hash = AsyncMock(return_value=None)
        repo_mock.write_event_score = AsyncMock()

        step = ExposureScoreStep(repo=repo_mock)
        state = _make_state(tickers=["AAPL"])

        await step.execute(state)

        # write_event_score is called (insert-only, old records preserved at DB level)
        repo_mock.write_event_score.assert_called_once()
        # Confirm it's an INSERT call (not update) by checking no 'update' kwarg
        call_kwargs = repo_mock.write_event_score.call_args.kwargs
        assert "update" not in call_kwargs
