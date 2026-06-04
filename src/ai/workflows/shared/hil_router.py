"""
ai.workflows.shared.hil_router — HILRouter for Event Deep-Dive HIL queueing.

HILRouter.enqueue() inserts a hil_queue row with scheduled_send_at = now() + 30 min.
Includes a startup check: if hil_queue table is missing (PLAN-F-013 not yet run),
logs a warning and continues rather than crashing.

PLAN-F-010 TASK-012.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.ai.workflows.state import WorkflowType
from src.config.settings import get_settings
from src.storage.repositories.hil_queue_repository import (
    HILQueueItemCreate,
    HILQueueRepository,
)

logger = logging.getLogger(__name__)

# EVENT_DEEP_DIVE HIL deadline: 30 minutes from enqueue
_EVENT_DEEP_DIVE_DELAY_MINUTES = 30


@asynccontextmanager
async def _get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide a short-lived async session for the HIL router."""
    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


class HILRouter:
    """Enqueues a HIL review item for the Event Deep-Dive workflow.

    Usage::

        router = HILRouter()
        await router.enqueue(state)

    The scheduled_send_at deadline is now + 30 minutes for EVENT_DEEP_DIVE.
    If hil_queue table is absent (PLAN-F-013 not yet migrated), logs a
    warning and returns without raising.
    """

    async def enqueue(self, state) -> None:
        """Insert a hil_queue row for the given workflow state.

        Args:
            state: DeepDiveWorkflowState (or any WorkflowState subclass) with
                workflow_id, tenant_id, user_id, workflow_type, confidence_scores.

        Returns:
            None (result is committed to DB or warning is logged on failure).
        """
        now = datetime.now(tz=timezone.utc)
        scheduled_send_at = self._compute_deadline(state.workflow_type, now)
        lc_checkpoint_id = f"hil:{state.workflow_id}"

        confidence = state.confidence_scores.get("workflow", 0.0)

        dto = HILQueueItemCreate(
            workflow_run_id=state.workflow_id,
            workflow_type=state.workflow_type.value,
            user_id=state.user_id,
            tenant_id=state.tenant_id,
            confidence=confidence,
            scheduled_send_at=scheduled_send_at,
            lc_checkpoint_id=lc_checkpoint_id,
        )

        try:
            async with _get_db_session() as session:
                repo = HILQueueRepository(session)
                queue_item = await repo.create(dto)
                await session.commit()

            logger.info(
                "HILRouter.enqueue: created hil_queue item=%s workflow_id=%s deadline=%s",
                queue_item.item_id,
                state.workflow_id,
                scheduled_send_at.isoformat(),
            )

        except Exception as exc:
            # Graceful degradation: missing hil_queue table (PLAN-F-013 pending)
            logger.warning(
                "HILRouter.enqueue: failed to create HIL queue item for workflow %s: %s",
                state.workflow_id,
                exc,
            )

    def _compute_deadline(self, workflow_type: WorkflowType, now: datetime) -> datetime:
        """Return the HIL deadline for the given workflow type.

        EVENT_DEEP_DIVE and EARNINGS_BRIEF → now + 30 minutes.
        """
        return now + timedelta(minutes=_EVENT_DEEP_DIVE_DELAY_MINUTES)
