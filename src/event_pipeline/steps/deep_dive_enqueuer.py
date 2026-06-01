"""DeepDiveEnqueuer — enqueues Celery deep-dive task for AUTO_SEND/HIL events.

Architecture enforcement:
  C-003 — deep-dive only fired for AUTO_SEND or HIL_QUEUE routes; suppressed for BLOCKED.

Single Responsibility: Celery task publishing only.
Dependency Inversion: Celery task object injected.
"""
from __future__ import annotations

import logging
from typing import Any

from src.event_pipeline.pipeline_state import AlertRoute, PipelineState

logger = logging.getLogger(__name__)


class DeepDiveEnqueuer:
    """Publishes a ``run_deep_dive`` Celery task for eligible pipeline events.

    Parameters
    ----------
    celery_task:
        A Celery task object exposing ``apply_async(args=[...], queue=...)`` method.
        If None, the enqueuer is a no-op.
    deep_dive_queue:
        Queue name (default: 'event_deep_dive').
    """

    def __init__(
        self,
        celery_task: Any = None,
        deep_dive_queue: str = "event_deep_dive",
    ) -> None:
        self._task = celery_task
        self._queue = deep_dive_queue

    async def enqueue(self, state: PipelineState) -> None:
        """Publish deep-dive task if route is not BLOCKED."""
        if state.route == AlertRoute.BLOCKED:
            logger.info(
                "DeepDiveEnqueuer: suppressed for BLOCKED route raw_event_id=%s",
                state.raw_event_id,
            )
            return

        if self._task is None:
            logger.info(
                "DeepDiveEnqueuer: no task configured; skipping enqueue raw_event_id=%s",
                state.raw_event_id,
            )
            return

        self._task.apply_async(
            args=[str(state.raw_event_id), str(state.tenant_id)],
            queue=self._queue,
        )
        logger.info(
            "DeepDiveEnqueuer: enqueued deep-dive raw_event_id=%s queue=%s",
            state.raw_event_id,
            self._queue,
        )
