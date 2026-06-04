"""
ai.workflows.earnings_brief.hil.fallback_task — HIL deadline fallback task.

Implements Architecture §7.6 Earnings Risk Brief HIL fallback:
  - Runs every 60 seconds as a Celery beat task.
  - Queries earnings_brief_run for rows with status=HIL_PENDING where
    created_at < NOW() - 15 minutes (past the 17:45 deadline).
  - For each: updates status to HIL_HOLD, writes audit entry, notifies user.

PLAN-F-009 TASK-010
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncGenerator

logger = logging.getLogger(__name__)

try:
    from celery import shared_task
    _CELERY_AVAILABLE = True
except ImportError:  # pragma: no cover
    _CELERY_AVAILABLE = False

    def shared_task(*args, **kwargs):  # type: ignore[misc]
        def decorator(fn):
            return fn
        return decorator


@asynccontextmanager
async def _get_db_session() -> AsyncGenerator[Any, None]:
    """Provide an async SQLAlchemy session from settings."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from src.config.settings import get_settings

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await engine.dispose()


async def _run_hil_fallback_async() -> dict:
    """Async core: find overdue HIL pending briefs and transition to HIL_HOLD.

    Returns:
        dict with transitioned count.
    """
    from sqlalchemy import select, update

    from src.storage.models.earnings_brief_run import EarningsBriefRun

    now = datetime.now(tz=timezone.utc)
    deadline_cutoff = now - timedelta(minutes=15)
    transitioned = 0

    async with _get_db_session() as session:
        # Find HIL_PENDING runs past the 15-minute window
        stmt = (
            select(EarningsBriefRun)
            .where(
                EarningsBriefRun.status == "HIL_PENDING",
                EarningsBriefRun.created_at < deadline_cutoff,
            )
        )
        result = await session.execute(stmt)
        overdue_runs = result.scalars().all()

        for run in overdue_runs:
            # Update status to HIL_HOLD
            await session.execute(
                update(EarningsBriefRun)
                .where(EarningsBriefRun.run_id == run.run_id)
                .values(
                    status="HIL_HOLD",
                    hil_status="pending",
                )
            )
            logger.info(
                "earnings_hil_fallback: run_id=%s company_id=%s transitioned to HIL_HOLD",
                run.run_id,
                run.company_id,
            )

            # Write audit entry (workflow_run row with status=HIL_HOLD)
            # In production this would create a workflow_run audit record
            # For MVP: log the event for the Admin AI Audit Console

            # Notify user (via notification infrastructure)
            # In production: send notification to the user associated with this brief
            # For MVP: log the notification intent
            logger.info(
                "earnings_hil_fallback: notify user for run_id=%s "
                "— brief on hold pending review at /admin/hil",
                run.run_id,
            )

            transitioned += 1

    return {"transitioned": transitioned}


@shared_task(
    name="ai.earnings_hil_fallback",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
)
def earnings_hil_fallback_task(self) -> dict:
    """Beat task (every 60 seconds): enforce HIL deadline for earnings briefs.

    Queries earnings_brief_run for HIL_PENDING rows past the 15-minute window
    (Architecture §7.6: hold deadline = 17:45; beat task transitions them).

    Returns:
        dict with transitioned count.
    """
    try:
        return asyncio.get_event_loop().run_until_complete(
            _run_hil_fallback_async()
        )
    except Exception as exc:
        logger.exception("earnings_hil_fallback_task failed: %s", exc)
        raise self.retry(exc=exc)
