"""HilEnqueuer — enqueues items to the HIL (Human-In-the-Loop) review queue.

Architecture enforcement:
  Single Responsibility — HIL queue write only.
  Dependency Inversion — repository injected.
  P-08 Immutable — writes are INSERT only to hil_queue table.
"""
from __future__ import annotations

import logging
from typing import Any

from src.event_pipeline.dispatch.alert_formatter import AlertPayload

logger = logging.getLogger(__name__)


class HilEnqueuer:
    """Writes an AlertPayload to the ``hil_queue`` table for human review.

    Parameters
    ----------
    repo:
        Repository exposing ``write_hil_item(tenant_id, payload, confidence) -> Awaitable``.
        If None, the enqueuer is a no-op (test/offline mode).
    """

    def __init__(self, repo: Any = None) -> None:
        self._repo = repo

    async def enqueue(self, payload: AlertPayload) -> None:
        """Insert a HIL queue item."""
        if self._repo is None:
            logger.info(
                "HilEnqueuer: no repo configured; skipping enqueue tenant=%s",
                payload.tenant_id,
            )
            return

        await self._repo.write_hil_item(
            tenant_id=payload.tenant_id,
            payload=payload.model_dump(),
            confidence=payload.confidence or 0.0,
        )
        logger.info(
            "HilEnqueuer: enqueued HIL item tenant=%s event=%s confidence=%.3f",
            payload.tenant_id,
            payload.raw_event_id,
            payload.confidence or 0.0,
        )
