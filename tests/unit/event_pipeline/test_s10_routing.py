"""Unit tests for RoutingStep (TASK-008, TDD).

Tests written before implementation.
Covers: AC-001 (confidence routing C-003).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from src.event_pipeline.pipeline_state import (
    AlertRoute,
    EventCategory,
    PipelineState,
    RawEventPayload,
    RawEventSource,
)


def _make_state_with_confidence(confidence: float) -> PipelineState:
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
        category=EventCategory.GEOPOLITICAL_CONFLICT,
        intensity=3,
        confidence=confidence,
    )


class TestRoutingAutoSendAt07:
    """test_routing_auto_send_at_0_7"""

    @pytest.mark.asyncio
    async def test_routing_auto_send_at_0_7(self):
        """confidence=0.7 routes to AUTO_SEND (C-003)."""
        from src.event_pipeline.steps.s10_routing import RoutingStep

        step = RoutingStep()
        state = _make_state_with_confidence(0.7)
        result = await step.execute(state)
        assert result.route == AlertRoute.AUTO_SEND


class TestRoutingHilAt04:
    """test_routing_hil_at_0_4"""

    @pytest.mark.asyncio
    async def test_routing_hil_at_0_4(self):
        """confidence=0.4 routes to HIL_QUEUE (inclusive lower bound, C-003)."""
        from src.event_pipeline.steps.s10_routing import RoutingStep

        step = RoutingStep()
        state = _make_state_with_confidence(0.4)
        result = await step.execute(state)
        assert result.route == AlertRoute.HIL_QUEUE


class TestRoutingBlockedBelow04:
    """test_routing_blocked_below_0_4"""

    @pytest.mark.asyncio
    async def test_routing_blocked_below_0_4(self):
        """confidence=0.399 routes to BLOCKED (C-003)."""
        from src.event_pipeline.steps.s10_routing import RoutingStep

        step = RoutingStep()
        state = _make_state_with_confidence(0.399)
        result = await step.execute(state)
        assert result.route == AlertRoute.BLOCKED


class TestRoutingHilAt0699:
    """test_routing_hil_at_0_699"""

    @pytest.mark.asyncio
    async def test_routing_hil_at_0_699(self):
        """confidence=0.699 routes to HIL_QUEUE (just below AUTO_SEND threshold)."""
        from src.event_pipeline.steps.s10_routing import RoutingStep

        step = RoutingStep()
        state = _make_state_with_confidence(0.699)
        result = await step.execute(state)
        assert result.route == AlertRoute.HIL_QUEUE


class TestRoutingAutoSendAt10:
    """confidence=1.0 routes to AUTO_SEND."""

    @pytest.mark.asyncio
    async def test_routing_auto_send_at_1_0(self):
        from src.event_pipeline.steps.s10_routing import RoutingStep

        step = RoutingStep()
        state = _make_state_with_confidence(1.0)
        result = await step.execute(state)
        assert result.route == AlertRoute.AUTO_SEND


class TestRoutingBlockedAt00:
    """confidence=0.0 routes to BLOCKED."""

    @pytest.mark.asyncio
    async def test_routing_blocked_at_0_0(self):
        from src.event_pipeline.steps.s10_routing import RoutingStep

        step = RoutingStep()
        state = _make_state_with_confidence(0.0)
        result = await step.execute(state)
        assert result.route == AlertRoute.BLOCKED
