"""
DeepDiveEnqueuer — Mode A→Mode B handoff service (step 11).

Enqueues the `event_deep_dive` Celery task when:
- event intensity >= 4, OR
- the event matched a portfolio company (has_portfolio_match=True)

Scheduled 2 minutes into the future to allow Mode A to complete first.
Must complete in <1s — no DB calls, no async waits.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from src.events.interfaces.i_workflow_queue import IWorkflowQueue

logger = logging.getLogger(__name__)

_DEEP_DIVE_WORKFLOW_TYPE = "event_deep_dive"
_SCHEDULE_DELAY_MINUTES = 2
_INTENSITY_THRESHOLD = 4


class DeepDiveEnqueuer:
    """Enqueues Mode B deep-dive jobs based on event intensity and portfolio match.

    Args:
        workflow_queue: IWorkflowQueue implementation for enqueuing Celery tasks.
    """

    def __init__(self, workflow_queue: IWorkflowQueue) -> None:
        self._queue = workflow_queue

    async def maybe_enqueue(
        self,
        event_id: UUID,
        intensity: int,
        has_portfolio_match: bool,
        tenant_id: UUID,
    ) -> bool:
        """Enqueue an event_deep_dive task if criteria are met.

        Args:
            event_id: UUID of the event to analyse in Mode B.
            intensity: Classified event intensity (1–5).
            has_portfolio_match: True when the event matched a portfolio company.
            tenant_id: Owning tenant for the deep-dive job.

        Returns:
            True if the job was enqueued, False if criteria were not met.
        """
        should_enqueue = intensity >= _INTENSITY_THRESHOLD or has_portfolio_match

        if not should_enqueue:
            logger.debug(
                "DeepDiveEnqueuer.maybe_enqueue: skipped event=%s intensity=%d portfolio_match=%s",
                event_id,
                intensity,
                has_portfolio_match,
            )
            return False

        scheduled_for = datetime.now(tz=timezone.utc) + timedelta(minutes=_SCHEDULE_DELAY_MINUTES)

        self._queue.enqueue(
            workflow_type=_DEEP_DIVE_WORKFLOW_TYPE,
            inputs={
                "event_id": str(event_id),
                "tenant_id": str(tenant_id),
            },
            priority="normal",
            scheduled_for=scheduled_for,
        )

        logger.info(
            "DeepDiveEnqueuer.maybe_enqueue: enqueued event=%s intensity=%d "
            "portfolio_match=%s scheduled_for=%s",
            event_id,
            intensity,
            has_portfolio_match,
            scheduled_for.isoformat(),
        )
        return True
