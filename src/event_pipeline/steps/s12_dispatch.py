"""Step 12: DISPATCH — route alert to WebSocket/WebPush or HIL queue.

Architecture enforcement:
  C-003 — dispatch strategy selected by state.route (set in Step 10).
  AC-001 — no dispatch for BLOCKED route.
  AC-005 — no dispatch if state.failed_step is set (executor halted before this step).

Strategy pattern: each route uses a different dispatcher (P-DI, OCP).
Single Responsibility: dispatch routing only; no formatting logic here.
Dependency Inversion: all dispatchers are injected.
"""
from __future__ import annotations

import logging
from typing import Any

from src.event_pipeline.dispatch.alert_formatter import AlertFormatter
from src.event_pipeline.pipeline_state import AlertRoute, PipelineState

logger = logging.getLogger(__name__)


class DispatchStep:
    """Pipeline Step 12: DISPATCH.

    Selects the appropriate dispatch strategy based on state.route:
      AUTO_SEND → WebSocketDispatcher + WebPushDispatcher
      HIL_QUEUE → HilEnqueuer
      BLOCKED   → suppressed (logged only)

    Parameters
    ----------
    websocket_dispatcher:
        Async dispatcher exposing ``push(payload) -> None``.
    web_push_dispatcher:
        Async dispatcher exposing ``push(payload) -> None``.
    hil_enqueuer:
        Async enqueuer exposing ``enqueue(payload) -> None``.
    formatter:
        AlertFormatter instance; defaults to ``AlertFormatter()``.
    """

    step_name: str = "s12_dispatch"

    def __init__(
        self,
        websocket_dispatcher: Any = None,
        web_push_dispatcher: Any = None,
        hil_enqueuer: Any = None,
        formatter: Any = None,
    ) -> None:
        self._ws = websocket_dispatcher
        self._web_push = web_push_dispatcher
        self._hil = hil_enqueuer
        self._formatter = formatter or AlertFormatter()

    async def execute(self, state: PipelineState) -> PipelineState:
        """Dispatch alert according to routing decision."""
        route = state.route

        if route is None:
            logger.warning(
                "Step 12 (DISPATCH): route is None for raw_event_id=%s — skipping",
                state.raw_event_id,
            )
            return state

        payload = self._formatter.format(state)

        if route == AlertRoute.AUTO_SEND:
            await self._dispatch_auto_send(payload)
        elif route == AlertRoute.HIL_QUEUE:
            await self._dispatch_hil(payload)
        else:  # BLOCKED
            logger.info(
                "Step 12 (DISPATCH): BLOCKED raw_event_id=%s confidence=%.3f — no outbound action",
                state.raw_event_id,
                state.confidence or 0.0,
            )

        return state

    async def _dispatch_auto_send(self, payload: Any) -> None:
        """Push to WebSocket and Web Push."""
        if self._ws is not None:
            await self._ws.push(payload)
        if self._web_push is not None:
            await self._web_push.push(payload)

    async def _dispatch_hil(self, payload: Any) -> None:
        """Enqueue to HIL review queue."""
        if self._hil is not None:
            await self._hil.enqueue(payload)
