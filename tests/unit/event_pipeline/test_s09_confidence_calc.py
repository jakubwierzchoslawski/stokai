"""Unit tests for ConfidenceCalcStep (TASK-008, TDD).

Tests written before implementation.
Covers: AC-001.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.event_pipeline.pipeline_state import (
    EventCategory,
    PipelineState,
    RawEventPayload,
    RawEventSource,
)


def _make_state_with_analogues(analogue_count: int = 5) -> PipelineState:
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
        event_description="Conflict event",
        category=EventCategory.GEOPOLITICAL_CONFLICT,
        intensity=3,
        analogues=[uuid.uuid4() for _ in range(analogue_count)],
        langfuse_trace_id="trace-xyz",
    )


class TestConfidenceCalcCallsLlmAndSetsState:
    """test_confidence_calc_calls_llm_and_sets_state"""

    @pytest.mark.asyncio
    async def test_confidence_calc_calls_llm_and_sets_state(self):
        """ConfidenceCalcStep calls LLM and sets state.confidence."""
        from src.event_pipeline.steps.s09_confidence_calc import ConfidenceCalcStep

        llm_mock = AsyncMock()
        llm_mock.synthesise_confidence = AsyncMock(return_value=0.75)

        repo_mock = AsyncMock()
        repo_mock.write_audit_log = AsyncMock()

        langfuse_mock = MagicMock()

        step = ConfidenceCalcStep(
            llm_client=llm_mock,
            repo=repo_mock,
            langfuse_client=langfuse_mock,
        )
        state = _make_state_with_analogues()

        result = await step.execute(state)

        assert result.confidence == 0.75
        llm_mock.synthesise_confidence.assert_called_once()


class TestConfidenceCalcWritesAuditLog:
    """test_confidence_calc_writes_audit_log"""

    @pytest.mark.asyncio
    async def test_confidence_calc_writes_audit_log(self):
        """ConfidenceCalcStep writes a second ai_audit_log entry."""
        from src.event_pipeline.steps.s09_confidence_calc import ConfidenceCalcStep

        llm_mock = AsyncMock()
        llm_mock.synthesise_confidence = AsyncMock(return_value=0.6)

        repo_mock = AsyncMock()
        repo_mock.write_audit_log = AsyncMock()

        langfuse_mock = MagicMock()

        step = ConfidenceCalcStep(
            llm_client=llm_mock,
            repo=repo_mock,
            langfuse_client=langfuse_mock,
        )
        state = _make_state_with_analogues()

        await step.execute(state)

        repo_mock.write_audit_log.assert_called_once()
