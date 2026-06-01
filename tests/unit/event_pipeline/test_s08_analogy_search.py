"""Unit tests for AnalogySearchStep (TASK-007, TDD).

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


def _make_embedded_state() -> PipelineState:
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
        event_description="event",
        category=EventCategory.GEOPOLITICAL_CONFLICT,
        intensity=3,
        embedding=[0.1] * 1536,
    )


class TestAnalogySearchReturnsTopK:
    """test_analogy_search_returns_top_k"""

    @pytest.mark.asyncio
    async def test_analogy_search_returns_top_k(self):
        """AnalogySearchStep sets state.analogues with up to 10 UUIDs."""
        from src.event_pipeline.steps.s08_analogy_search import AnalogySearchStep

        analogue_ids = [uuid.uuid4() for _ in range(10)]

        repo_mock = AsyncMock()
        repo_mock.find_analogues = AsyncMock(return_value=analogue_ids)

        step = AnalogySearchStep(repo=repo_mock)
        state = _make_embedded_state()

        result = await step.execute(state)

        assert len(result.analogues) == 10
        assert result.analogues == analogue_ids


class TestAnalogySearchExcludesCurrentEvent:
    """test_analogy_search_excludes_current_event"""

    @pytest.mark.asyncio
    async def test_analogy_search_excludes_current_event(self):
        """AnalogySearchStep passes exclude_id=raw_event_id to repo."""
        from src.event_pipeline.steps.s08_analogy_search import AnalogySearchStep

        repo_mock = AsyncMock()
        repo_mock.find_analogues = AsyncMock(return_value=[])

        step = AnalogySearchStep(repo=repo_mock)
        state = _make_embedded_state()

        await step.execute(state)

        call_kwargs = repo_mock.find_analogues.call_args.kwargs
        # exclude_event_id must be passed to prevent self-match
        assert "exclude_event_id" in call_kwargs or \
               state.raw_event_id in repo_mock.find_analogues.call_args.args
