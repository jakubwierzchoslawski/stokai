"""WebSocketDispatcher — pushes alerts via WebSocket.

Architecture enforcement:
  Single Responsibility — WebSocket push only.
  Dependency Inversion — WebSocket manager injected, not instantiated here.

In production this calls the FastAPI WebSocket connection manager.
In tests it is mocked.
"""
from __future__ import annotations

import logging
from typing import Any

from src.event_pipeline.dispatch.alert_formatter import AlertPayload

logger = logging.getLogger(__name__)


class WebSocketDispatcher:
    """Pushes an AlertPayload to all connected WebSocket clients for the tenant.

    Parameters
    ----------
    ws_manager:
        WebSocket connection manager exposing ``broadcast(tenant_id, data) -> Awaitable``.
        If None, the dispatcher is a no-op (test/offline mode).
    """

    def __init__(self, ws_manager: Any = None) -> None:
        self._ws_manager = ws_manager

    async def push(self, payload: AlertPayload) -> None:
        """Push alert to WebSocket clients."""
        if self._ws_manager is None:
            logger.info(
                "WebSocketDispatcher: no manager configured; skipping push tenant=%s",
                payload.tenant_id,
            )
            return

        await self._ws_manager.broadcast(
            tenant_id=payload.tenant_id,
            data=payload.model_dump(),
        )
        logger.info(
            "WebSocketDispatcher: pushed alert tenant=%s event=%s",
            payload.tenant_id,
            payload.raw_event_id,
        )
