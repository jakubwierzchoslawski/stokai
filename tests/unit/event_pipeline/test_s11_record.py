"""Unit tests for RecordStep (TASK-009, TDD).

Tests written before implementation.
Covers: AC-001, AC-005.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, call

import pytest

from src.event_pipeline.pipeline_state import (
    AlertRoute,
    EventCategory,
    PipelineState,
    RawEventPayload,
    RawEventSource,
)
from src.event_pipeline.exceptions import PipelineHalt


def _make_state(route: AlertRoute = AlertRoute.AUTO_SEND) -> PipelineState:
    tenant_id = uuid.uuid4()
    portfolio_1 = str(uuid.uuid4())
    portfolio_2 = str(uuid.uuid4())
    portfolio_3 = str(uuid.uuid4())
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
        confidence=0.8,
        route=route,
        exposure_map={
            portfolio_1: 0.45,
            portfolio_2: 0.30,
            portfolio_3: 0.15,
        },
    )


class TestRecordStepWritesEventScoresForAllPortfolios:
    """test_record_step_writes_event_scores_for_all_portfolios"""

    @pytest.mark.asyncio
    async def test_record_step_writes_event_scores_for_all_portfolios(self):
        """RecordStep writes 3 event_scores rows for 3 portfolios."""
        from src.event_pipeline.steps.s11_record import RecordStep

        repo_mock = AsyncMock()
        repo_mock.write_event_score_batch = AsyncMock()
        repo_mock.write_episodic_memory = AsyncMock()
        repo_mock.update_status = AsyncMock()

        step = RecordStep(repo=repo_mock)
        state = _make_state()

        await step.execute(state)

        # write_event_score_batch called with 3 portfolios
        repo_mock.write_event_score_batch.assert_called_once()
        call_args = repo_mock.write_event_score_batch.call_args
        scores = call_args.args[0] if call_args.args else call_args.kwargs.get("scores", [])
        assert len(scores) == 3


class TestRecordStepWritesEpisodicMemoryAppendOnly:
    """test_record_step_writes_episodic_memory_append_only"""

    @pytest.mark.asyncio
    async def test_record_step_writes_episodic_memory_append_only(self):
        """RecordStep calls write_episodic_memory (INSERT only — no updates)."""
        from src.event_pipeline.steps.s11_record import RecordStep

        repo_mock = AsyncMock()
        repo_mock.write_event_score_batch = AsyncMock()
        repo_mock.write_episodic_memory = AsyncMock()
        repo_mock.update_status = AsyncMock()

        step = RecordStep(repo=repo_mock)
        state = _make_state()

        await step.execute(state)

        repo_mock.write_episodic_memory.assert_called_once()
        # Confirm it's an insert call — no 'update' kwarg
        call_kwargs = repo_mock.write_episodic_memory.call_args.kwargs
        assert "update" not in call_kwargs


class TestRecordStepSetsPipelineStatusCompleted:
    """test_record_step_sets_pipeline_status_completed"""

    @pytest.mark.asyncio
    async def test_record_step_sets_pipeline_status_completed(self):
        """RecordStep sets raw_event.pipeline_status = completed."""
        from src.event_pipeline.steps.s11_record import RecordStep

        repo_mock = AsyncMock()
        repo_mock.write_event_score_batch = AsyncMock()
        repo_mock.write_episodic_memory = AsyncMock()
        repo_mock.update_status = AsyncMock()

        step = RecordStep(repo=repo_mock)
        state = _make_state()

        await step.execute(state)

        repo_mock.update_status.assert_called_once()
        call_args = repo_mock.update_status.call_args
        status = call_args.kwargs.get("status") or (
            call_args.args[1] if len(call_args.args) > 1 else None
        )
        assert status == "completed"


class TestRecordStepRollsBackOnDbError:
    """test_record_step_rolls_back_on_db_error"""

    @pytest.mark.asyncio
    async def test_record_step_raises_pipeline_halt_on_db_error(self):
        """RecordStep raises PipelineHalt when episodic memory write fails."""
        from src.event_pipeline.steps.s11_record import RecordStep

        repo_mock = AsyncMock()
        repo_mock.write_event_score_batch = AsyncMock()
        repo_mock.write_episodic_memory = AsyncMock(
            side_effect=RuntimeError("DB connection lost")
        )
        repo_mock.update_status = AsyncMock()

        step = RecordStep(repo=repo_mock)
        state = _make_state()

        with pytest.raises(PipelineHalt):
            await step.execute(state)
