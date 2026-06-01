"""Unit tests for DispatchStep and AlertFormatter (TASK-010, TDD).

Tests written before implementation.
Covers: AC-001, AC-005.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.event_pipeline.pipeline_state import (
    AlertRoute,
    EventCategory,
    PipelineState,
    RawEventPayload,
    RawEventSource,
)


def _make_state(route: AlertRoute, alert_text: str = "Test alert text") -> PipelineState:
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
        confidence=0.8,
        route=route,
        alert_text=alert_text,
        analogues=[uuid.uuid4() for _ in range(5)],
    )


class TestDispatchAutoSendCallsWebsocketAndWebPush:
    """test_dispatch_auto_send_calls_websocket_and_web_push"""

    @pytest.mark.asyncio
    async def test_dispatch_auto_send_calls_websocket_and_web_push(self):
        """route=AUTO_SEND: both WebSocketDispatcher and WebPushDispatcher called."""
        from src.event_pipeline.steps.s12_dispatch import DispatchStep

        ws_dispatcher = AsyncMock()
        ws_dispatcher.push = AsyncMock()

        web_push_dispatcher = AsyncMock()
        web_push_dispatcher.push = AsyncMock()

        hil_enqueuer = AsyncMock()
        hil_enqueuer.enqueue = AsyncMock()

        step = DispatchStep(
            websocket_dispatcher=ws_dispatcher,
            web_push_dispatcher=web_push_dispatcher,
            hil_enqueuer=hil_enqueuer,
        )
        state = _make_state(AlertRoute.AUTO_SEND)

        await step.execute(state)

        ws_dispatcher.push.assert_called_once()
        web_push_dispatcher.push.assert_called_once()
        hil_enqueuer.enqueue.assert_not_called()


class TestDispatchHilEnqueuesItem:
    """test_dispatch_hil_enqueues_item"""

    @pytest.mark.asyncio
    async def test_dispatch_hil_enqueues_item(self):
        """route=HIL_QUEUE: HilEnqueuer.enqueue called; dispatchers not called."""
        from src.event_pipeline.steps.s12_dispatch import DispatchStep

        ws_dispatcher = AsyncMock()
        ws_dispatcher.push = AsyncMock()

        web_push_dispatcher = AsyncMock()
        web_push_dispatcher.push = AsyncMock()

        hil_enqueuer = AsyncMock()
        hil_enqueuer.enqueue = AsyncMock()

        step = DispatchStep(
            websocket_dispatcher=ws_dispatcher,
            web_push_dispatcher=web_push_dispatcher,
            hil_enqueuer=hil_enqueuer,
        )
        state = _make_state(AlertRoute.HIL_QUEUE)

        await step.execute(state)

        hil_enqueuer.enqueue.assert_called_once()
        ws_dispatcher.push.assert_not_called()
        web_push_dispatcher.push.assert_not_called()


class TestDispatchBlockedSuppressesAllSends:
    """test_dispatch_blocked_suppresses_all_sends"""

    @pytest.mark.asyncio
    async def test_dispatch_blocked_suppresses_all_sends(self):
        """route=BLOCKED: no dispatcher called."""
        from src.event_pipeline.steps.s12_dispatch import DispatchStep

        ws_dispatcher = AsyncMock()
        ws_dispatcher.push = AsyncMock()

        web_push_dispatcher = AsyncMock()
        web_push_dispatcher.push = AsyncMock()

        hil_enqueuer = AsyncMock()
        hil_enqueuer.enqueue = AsyncMock()

        step = DispatchStep(
            websocket_dispatcher=ws_dispatcher,
            web_push_dispatcher=web_push_dispatcher,
            hil_enqueuer=hil_enqueuer,
        )
        state = _make_state(AlertRoute.BLOCKED)

        await step.execute(state)

        ws_dispatcher.push.assert_not_called()
        web_push_dispatcher.push.assert_not_called()
        hil_enqueuer.enqueue.assert_not_called()


class TestAlertFormatterIncludesConfidenceAndDisclaimer:
    """test_alert_formatter_includes_confidence_and_disclaimer"""

    def test_alert_formatter_includes_confidence_and_disclaimer(self):
        """AlertFormatter includes confidence and disclaimer text in payload."""
        from src.event_pipeline.dispatch.alert_formatter import AlertFormatter

        state = _make_state(AlertRoute.AUTO_SEND, alert_text="Test alert")

        formatter = AlertFormatter()
        payload = formatter.format(state)

        assert payload.confidence == state.confidence
        assert payload.sample_size == len(state.analogues)
        assert len(payload.disclaimer) > 0
        assert "investment" in payload.disclaimer.lower() or "recommendation" in payload.disclaimer.lower()
