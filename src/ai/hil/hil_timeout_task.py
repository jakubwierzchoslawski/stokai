"""
ai.hil.hil_timeout_task — Celery beat task: expire overdue HIL queue items.

expire_overdue_hil_items runs every 60 seconds. It:
  1. Queries HILQueueRepository for all pending items with
     scheduled_send_at < now (crossed their deadline without reviewer action).
  2. For each item: calls HILActionService.apply_action(action='reject') using
     the SYSTEM_REVIEWER_ID sentinel UUID (settings.HIL_SYSTEM_REVIEWER_ID).
  3. Updates the item status to 'timed_out' (overrides 'rejected' so operators
     can distinguish automatic timeout from deliberate rejection).
  4. Writes an episodic Layer 1 audit row with event_type='hil_timeout'.

PLAN-F-013 TASK-006
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from src.config.celery_app import celery_app
from src.storage.repositories.hil_queue_repository import HILQueueRepository, HILStatus

logger = logging.getLogger(__name__)

# Sentinel system reviewer ID used for all timeout actions.
# This UUID distinguishes system-initiated rejections from human ones.
# Configurable via settings.HIL_SYSTEM_REVIEWER_ID when that setting is added.
_SYSTEM_REVIEWER_ID = UUID("00000000-0000-0000-0000-000000000001")


# ── Async core (extracted for testability) ────────────────────────────────────


async def _run_expire_overdue_hil_items(
    hil_repo: HILQueueRepository,
    action_service,  # HILActionService — avoid circular import at type level
    workflow_run_repo=None,
) -> None:
    """Process all overdue pending HIL items.

    Extracted from the Celery task so it can be unit-tested with mocked
    collaborators without spinning up a real Celery worker.

    Args:
        hil_repo: HILQueueRepository providing list_timed_out_pending / update_status.
        action_service: HILActionService.apply_action for reject + audit.
        workflow_run_repo: Optional WorkflowRunRepository for audit rows.
    """
    now = datetime.now(tz=timezone.utc)
    overdue_items = await hil_repo.list_timed_out_pending(now)

    if not overdue_items:
        logger.debug("expire_overdue_hil_items: no overdue items at %s", now.isoformat())
        return

    logger.info(
        "expire_overdue_hil_items: found %d overdue item(s) at %s",
        len(overdue_items),
        now.isoformat(),
    )

    for item in overdue_items:
        try:
            # Step 1: apply reject via HILActionService (also writes user_feedback
            # and calls HILResumeService.terminate_workflow)
            await action_service.apply_action(
                item_id=item.item_id,
                tenant_id=item.tenant_id,
                reviewer_id=_SYSTEM_REVIEWER_ID,
                action="reject",
            )

            # Step 2: override status to 'timed_out' — distinguishes automatic
            # timeout from explicit operator rejection (AC-005)
            await hil_repo.update_status(
                item_id=item.item_id,
                tenant_id=item.tenant_id,
                status=HILStatus.TIMED_OUT,
            )

            # Step 3: write episodic Layer 1 audit row (REQ-N-012)
            if workflow_run_repo is not None:
                try:
                    await workflow_run_repo.append_audit_event(
                        workflow_run_id=item.workflow_run_id,
                        event_type="hil_timeout",
                        payload={
                            "item_id": str(item.item_id),
                            "tenant_id": str(item.tenant_id),
                            "scheduled_send_at": item.scheduled_send_at.isoformat()
                            if hasattr(item.scheduled_send_at, "isoformat")
                            else str(item.scheduled_send_at),
                            "timed_out_at": now.isoformat(),
                        },
                    )
                except AttributeError:
                    # append_audit_event not yet available (PLAN-F-015)
                    logger.debug(
                        "expire_overdue_hil_items: append_audit_event unavailable "
                        "for item %s; audit skipped",
                        item.item_id,
                    )

            logger.info(
                "expire_overdue_hil_items: timed out item_id=%s tenant_id=%s",
                item.item_id,
                item.tenant_id,
            )

        except Exception:
            logger.exception(
                "expire_overdue_hil_items: failed to process item_id=%s",
                item.item_id,
            )
            # Continue processing remaining items even if one fails


# ── Celery task ────────────────────────────────────────────────────────────────


@celery_app.task(name="src.ai.hil.hil_timeout_task.expire_overdue_hil_items")
def expire_overdue_hil_items() -> None:
    """Celery beat task: expire overdue HIL queue items every 60 seconds.

    This task is a thin synchronous wrapper around the async core. It creates
    a short-lived async event loop to run the DB operations.

    Registered in beat_schedule in src/config/celery_app.py.
    """
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

    from src.ai.hil.hil_action_service import HILActionService, UserFeedbackRepository
    from src.ai.hil.hil_resume import HILResumeService
    from src.config.settings import get_settings
    from src.storage.repositories.workflow_run_repository import WorkflowRunRepository

    settings = get_settings()

    async def _run() -> None:
        engine = create_async_engine(settings.DATABASE_URL, echo=False)
        factory = async_sessionmaker(engine, expire_on_commit=False)

        async with factory() as session:
            hil_repo = HILQueueRepository(session)
            workflow_run_repo = WorkflowRunRepository(session)
            feedback_repo = UserFeedbackRepository(session)
            resume_service = HILResumeService(workflow_run_repo=workflow_run_repo)

            action_service = HILActionService(
                hil_queue_repo=hil_repo,
                resume_service=resume_service,
                feedback_repo=feedback_repo,
                workflow_run_repo=workflow_run_repo,
            )

            await _run_expire_overdue_hil_items(
                hil_repo=hil_repo,
                action_service=action_service,
                workflow_run_repo=workflow_run_repo,
            )
            await session.commit()

        await engine.dispose()

    asyncio.run(_run())
