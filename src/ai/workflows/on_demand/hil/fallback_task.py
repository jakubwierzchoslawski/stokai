"""
ai.workflows.on_demand.hil.fallback_task — HIL fallback Celery beat task.

hil_fallback_check_task runs every 60 seconds (Celery beat schedule).

For each HIL_PENDING workflow run that has been waiting > 10 minutes:
  1. Write an audit log entry.
  2. Update status=COMPLETED with low_confidence_banner=True in final_state.
  3. Notify frontend via WorkflowNotifier.

This ensures that analyses stuck in HIL_PENDING do not block users indefinitely
when no human reviewer acts within the SLA window.

PLAN-F-007 TASK-009
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from celery import shared_task
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.celery_app import celery_app
from src.storage.models.workflow_run import WorkflowRun

logger = logging.getLogger(__name__)

_HIL_SLA_MINUTES = 10


async def _run_hil_fallback(session: AsyncSession) -> int:
    """Process all overdue HIL_PENDING workflows.

    Args:
        session: Async SQLAlchemy session.

    Returns:
        Number of workflows promoted from HIL_PENDING → COMPLETED.
    """
    cutoff = datetime.now(tz=timezone.utc) - timedelta(minutes=_HIL_SLA_MINUTES)

    stmt = select(WorkflowRun).where(
        WorkflowRun.status == "HIL_PENDING",
        WorkflowRun.started_at < cutoff,
    )
    result = await session.execute(stmt)
    overdue_runs = result.scalars().all()

    promoted = 0
    for run in overdue_runs:
        logger.info(
            "hil_fallback: auto-completing HIL_PENDING workflow=%s (started=%s)",
            run.workflow_id,
            run.started_at,
        )

        # Merge low_confidence_banner flag into final_state
        existing_final = run.final_state or {}
        new_final = {**existing_final, "low_confidence_banner": True}

        update_stmt = (
            update(WorkflowRun)
            .where(WorkflowRun.workflow_id == run.workflow_id)
            .values(
                status="COMPLETED",
                completed_at=datetime.now(tz=timezone.utc),
                final_state=new_final,
            )
        )
        await session.execute(update_stmt)

        # Best-effort WebSocket notification
        try:
            from src.api.websocket.workflow_notifier import push_workflow_update
            await push_workflow_update(
                workflow_id=str(run.workflow_id),
                status="COMPLETED",
                tenant_id=str(run.tenant_id),
            )
        except Exception:
            logger.debug("hil_fallback: WebSocket notify skipped for %s", run.workflow_id)

        promoted += 1

    if promoted:
        await session.flush()

    return promoted


@shared_task(
    name="ai.hil_fallback_check",
    bind=False,
    max_retries=0,
)
def hil_fallback_check_task() -> dict:
    """Celery beat task: promote overdue HIL_PENDING workflows to COMPLETED.

    Runs every 60 seconds. Adds low_confidence_banner=True to final_state
    so the frontend can display an appropriate notice to the user.
    """
    async def _inner() -> int:
        from sqlalchemy.ext.asyncio import (
            AsyncSession,
            async_sessionmaker,
            create_async_engine,
        )
        from src.config.settings import get_settings

        settings = get_settings()
        engine = create_async_engine(settings.DATABASE_URL, echo=False)
        factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        try:
            async with factory() as session:
                async with session.begin():
                    count = await _run_hil_fallback(session)
            return count
        finally:
            await engine.dispose()

    promoted = asyncio.get_event_loop().run_until_complete(_inner())
    logger.info("hil_fallback_check_task: promoted %d runs", promoted)
    return {"promoted": promoted}
