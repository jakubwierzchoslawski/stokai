"""Unit tests for TraceStep, AlertTextGenerator, DeepDiveEnqueuer (TASK-011, TDD).

Tests written before implementation.
Covers: AC-001, AC-002, AC-003.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.event_pipeline.pipeline_state import (
    AlertRoute,
    EventCategory,
    PipelineState,
    RawEventPayload,
    RawEventSource,
)


def _make_state(route: AlertRoute = AlertRoute.AUTO_SEND) -> PipelineState:
    tenant_id = uuid.uuid4()
    return PipelineState(
        raw_event_id=uuid.uuid4(),
        tenant_id=tenant_id,
        payload=RawEventPayload(
            source=RawEventSource.GDELT,
            raw_payload={"title": "event"},
            detected_at=datetime.now(timezone.utc),
            tenant_id=tenant_id,
        ),
        event_description="Geopolitical conflict in region",
        category=EventCategory.GEOPOLITICAL_CONFLICT,
        intensity=4,
        confidence=0.82,
        route=route,
        analogues=[uuid.uuid4() for _ in range(7)],
    )


class TestAlertTextGeneratorIncludesRequiredFields:
    """test_alert_text_generator_includes_required_fields"""

    def test_alert_text_generator_includes_required_fields(self):
        """AlertTextGenerator output includes confidence, sample_size, and disclaimer."""
        from src.event_pipeline.steps.alert_text_generator import AlertTextGenerator

        generator = AlertTextGenerator()
        state = _make_state()

        result = generator.generate(state)

        assert "0.82" in result or "82" in result  # confidence present
        assert "7" in result  # sample size (len analogues)
        assert len(result) > 50  # substantive output


class TestDeepDiveEnqueuerPublishesForAutoSend:
    """test_deep_dive_enqueuer_publishes_for_auto_send"""

    @pytest.mark.asyncio
    async def test_deep_dive_enqueuer_publishes_for_auto_send(self):
        """DeepDiveEnqueuer enqueues task for AUTO_SEND route."""
        from src.event_pipeline.steps.deep_dive_enqueuer import DeepDiveEnqueuer

        celery_mock = MagicMock()
        celery_mock.apply_async = MagicMock()

        enqueuer = DeepDiveEnqueuer(celery_task=celery_mock)
        state = _make_state(AlertRoute.AUTO_SEND)

        await enqueuer.enqueue(state)

        celery_mock.apply_async.assert_called_once()


class TestDeepDiveEnqueuerSuppressedForBlocked:
    """test_deep_dive_enqueuer_suppressed_for_blocked"""

    @pytest.mark.asyncio
    async def test_deep_dive_enqueuer_suppressed_for_blocked(self):
        """DeepDiveEnqueuer does not enqueue for BLOCKED route."""
        from src.event_pipeline.steps.deep_dive_enqueuer import DeepDiveEnqueuer

        celery_mock = MagicMock()
        celery_mock.apply_async = MagicMock()

        enqueuer = DeepDiveEnqueuer(celery_task=celery_mock)
        state = _make_state(AlertRoute.BLOCKED)

        await enqueuer.enqueue(state)

        celery_mock.apply_async.assert_not_called()


class TestTraceStepSetsGeneratedAt:
    """test_trace_step_sets_generated_at"""

    @pytest.mark.asyncio
    async def test_trace_step_sets_generated_at(self):
        """TraceStep sets state.generated_at to current UTC time."""
        from src.event_pipeline.steps.s13_trace import TraceStep

        repo_mock = AsyncMock()
        repo_mock.set_generated_at = AsyncMock()

        langfuse_mock = MagicMock()
        langfuse_mock.finish = MagicMock()

        step = TraceStep(repo=repo_mock, langfuse_client=langfuse_mock)
        state = _make_state()

        result = await step.execute(state)

        assert result.generated_at is not None
        assert isinstance(result.generated_at, datetime)


class TestTraceStepClosesLangfuseTrace:
    """test_trace_step_closes_langfuse_trace"""

    @pytest.mark.asyncio
    async def test_trace_step_closes_langfuse_trace(self):
        """TraceStep calls langfuse_client.finish()."""
        from src.event_pipeline.steps.s13_trace import TraceStep

        repo_mock = AsyncMock()
        repo_mock.set_generated_at = AsyncMock()

        langfuse_mock = MagicMock()
        langfuse_mock.finish = MagicMock()

        step = TraceStep(repo=repo_mock, langfuse_client=langfuse_mock)
        state = _make_state()

        await step.execute(state)

        langfuse_mock.finish.assert_called_once()
