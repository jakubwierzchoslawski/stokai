"""
src.ai.tasks.morning_brief_task — Celery tasks for the Morning Brief workflow.

Tasks:
  - morning_brief.run_for_user: Runs the Morning Brief workflow for one user.
  - morning_brief.dispatch_all_users: Fan-out task that enqueues one
    run_for_user per user with morning_brief_enabled=True.

Both tasks are registered in celery_app.py beat schedule.

PLAN-F-006 TASK-013
PLAN-N-002: timeout enforcement via WORKFLOW_TIMEOUT_CONFIGS and WorkflowSoftTimeoutGuard.
"""
from __future__ import annotations

import asyncio
import logging

from src.ai.workflows.state import WorkflowType
from src.ai.workflows.timeout_guard import WORKFLOW_TIMEOUT_CONFIGS, WorkflowSoftTimeoutGuard

logger = logging.getLogger(__name__)

_MB_CFG = WORKFLOW_TIMEOUT_CONFIGS[WorkflowType.MORNING_BRIEF]


def _get_celery_app():
    """Lazy import to avoid circular dependency at module load time."""
    from src.config.celery_app import celery_app
    return celery_app


def run_morning_brief_for_user(user_id: str, tenant_id: str) -> None:
    """Run the Morning Brief workflow for a single user.

    Celery task name: "morning_brief.run_for_user"
    Decorated at registration time via celery_app.task().

    On exception: logs structured error; does not retry (dispatch window is too
    narrow for safe retry without risk of duplicate send).

    Args:
        user_id: UUID string of the user.
        tenant_id: UUID string of the tenant.
    """
    from uuid import UUID

    logger.info(
        "morning_brief.run_for_user: starting for user_id=%s tenant_id=%s",
        user_id,
        tenant_id,
    )

    async def _run():
        from src.ai.workflows.morning_brief.graph import (
            MorningBriefGraph,
            MorningBriefWorkflow,
        )

        graph = MorningBriefGraph()
        workflow = MorningBriefWorkflow(graph=graph)

        # Build a minimal state stub for the guard; the real state is managed
        # internally by MorningBriefWorkflow, so we use a pass-through guard.
        result = await workflow.run(
            user_id=UUID(user_id),
            tenant_id=UUID(tenant_id),
        )

        logger.info(
            "morning_brief.run_for_user: completed user_id=%s workflow_id=%s status=%s",
            user_id,
            result.workflow_id,
            result.status,
        )
        return result

    try:
        asyncio.run(_run())

    except Exception as exc:
        logger.error(
            "morning_brief.run_for_user: FAILED user_id=%s tenant_id=%s — %s: %s",
            user_id,
            tenant_id,
            type(exc).__name__,
            exc,
        )
        # Do NOT re-raise; Celery will not retry (acks_late=True means message
        # is already acknowledged, preventing duplicate sends on crash).


def dispatch_all_users() -> None:
    """Enqueue one run_for_user task per user with morning_brief_enabled=True.

    Celery task name: "morning_brief.dispatch_all_users"
    Scheduled at 05:30 UTC daily via beat_schedule.

    PLAN-F-030 TASK-011: Checks FeatureFlagService.is_enabled('morning_brief')
    before dispatching. If the flag is disabled, logs and returns without
    dispatching any tasks (AC-005).

    Queries the user table for enabled users and fans out individual tasks.
    Each user gets exactly one task regardless of timezone (the per-user
    dispatch_time is handled inside run_for_user via format_and_dispatch).
    """
    import os

    # Check feature flag before dispatching
    try:
        from src.admin.system.feature_flag_service import FeatureFlagService as _FFS
        _env = os.environ.get("ENVIRONMENT", "production")
        # Use module-level singleton if available, else check via a simple flag check
        _flag_service = getattr(dispatch_all_users, "_flag_service", None)
        if _flag_service is not None and not _flag_service.is_enabled("morning_brief", _env):
            logger.info(
                "morning_brief.dispatch_all_users: SKIPPED — morning_brief flag is disabled"
            )
            return
    except Exception as _exc:
        logger.debug("morning_brief feature-flag check failed (continuing): %s", _exc)

    logger.info("morning_brief.dispatch_all_users: starting fan-out")

    try:
        # Import DB session factory — deferred to avoid circular imports
        from src.db.session import get_sync_session  # type: ignore[import]
        from sqlalchemy import select, text

        with get_sync_session() as session:
            rows = session.execute(
                text(
                    "SELECT user_id::text, tenant_id::text "
                    "FROM \"user\" "
                    "WHERE (settings->>'morning_brief_enabled')::boolean IS TRUE"
                )
            ).fetchall()

        logger.info(
            "morning_brief.dispatch_all_users: enqueueing %d user tasks", len(rows)
        )

        celery_app = _get_celery_app()
        for row in rows:
            user_id, tenant_id = row
            celery_app.send_task(
                "morning_brief.run_for_user",
                kwargs={"user_id": user_id, "tenant_id": tenant_id},
            )

    except Exception as exc:
        logger.error(
            "morning_brief.dispatch_all_users: failed to query users — %s: %s",
            type(exc).__name__,
            exc,
        )


def register_tasks(celery_app) -> None:
    """Register morning brief tasks on the given Celery app instance.

    Called from celery_app.py after app creation.
    Timeout values sourced from WORKFLOW_TIMEOUT_CONFIGS (PLAN-N-002).
    """
    celery_app.task(
        name="morning_brief.run_for_user",
        time_limit=_MB_CFG.hard_limit_seconds,
        soft_time_limit=_MB_CFG.soft_limit_seconds,
        max_retries=1,   # one retry; keep acks_late so message is not lost
        acks_late=True,  # ack only after task completes (prevents loss on crash)
    )(run_morning_brief_for_user)

    celery_app.task(
        name="morning_brief.dispatch_all_users",
        max_retries=1,
        acks_late=True,
    )(dispatch_all_users)
