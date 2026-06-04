"""
ai.workflows.watchlist_scan.tasks — Celery task for the Watchlist Scan workflow.

Task: run_watchlist_scan
  - Cron-triggered at 17:30 daily via Celery beat.
  - Executes the Watchlist Scan LangGraph for all portfolio companies.
  - Wraps graph invocation in WorkflowSoftTimeoutGuard (PLAN-N-002).
  - Hard and soft time limits sourced from WORKFLOW_TIMEOUT_CONFIGS.

PLAN-F-008 (watchlist scan workflow)
PLAN-N-002 TASK-005 (timeout enforcement)
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, AsyncGenerator
from uuid import UUID, uuid4

from src.ai.workflows.state import WorkflowState, WorkflowStatus, WorkflowType
from src.ai.workflows.timeout_guard import WORKFLOW_TIMEOUT_CONFIGS, WorkflowSoftTimeoutGuard

logger = logging.getLogger(__name__)

_WS_CFG = WORKFLOW_TIMEOUT_CONFIGS[WorkflowType.WATCHLIST_SCAN]

# Lazy import of celery to allow tests without celery installed
try:
    from celery import shared_task
    _CELERY_AVAILABLE = True
except ImportError:  # pragma: no cover
    _CELERY_AVAILABLE = False

    def shared_task(*args, **kwargs):  # type: ignore[misc]
        def decorator(fn):
            return fn
        return decorator


# ── Session factory helper ────────────────────────────────────────────────────


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


def _get_langfuse_client() -> Any | None:
    """Return a configured Langfuse client or None."""
    try:
        from src.config.settings import get_settings
        settings = get_settings()
        if not getattr(settings, "LANGFUSE_HOST", None) or not getattr(settings, "LANGFUSE_SECRET_KEY", None):
            return None
        from langfuse import Langfuse
        return Langfuse(
            secret_key=settings.LANGFUSE_SECRET_KEY,
            public_key=settings.LANGFUSE_PUBLIC_KEY,
            host=settings.LANGFUSE_HOST,
        )
    except Exception:
        return None


# ── Async core ─────────────────────────────────────────────────────────────────


async def _run_watchlist_scan_async(
    tenant_id: str,
    user_id: str,
    workflow_id: str | None = None,
) -> dict:
    """Async core of the watchlist scan task.

    Returns:
        dict with workflow_id, status, and cost_usd.
    """
    from src.ai.workflows.watchlist_scan.graph import build_watchlist_scan_graph
    from src.storage.repositories.workflow_run_repository import WorkflowRunRepository

    wf_id = UUID(workflow_id) if workflow_id else uuid4()
    tenant_uuid = UUID(tenant_id)
    user_uuid = UUID(user_id)

    state = WorkflowState(
        workflow_id=wf_id,
        workflow_type=WorkflowType.WATCHLIST_SCAN,
        tenant_id=tenant_uuid,
        user_id=user_uuid,
        started_at=datetime.now(tz=timezone.utc),
    )

    langfuse_client = _get_langfuse_client()

    try:
        from src.ai.startup import get_agent_registry
        registry = get_agent_registry()
    except Exception:
        logger.warning("Agent registry unavailable for watchlist scan; using None stub")
        registry = None

    graph = build_watchlist_scan_graph(registry=registry)

    final_state: WorkflowState = state
    try:
        async with _get_db_session() as guard_session:
            guard_repo = WorkflowRunRepository(guard_session)
            guard = WorkflowSoftTimeoutGuard(state, guard_repo, langfuse_client)
            async with guard:
                result = await graph.ainvoke(state)

        if guard._final_state.status == WorkflowStatus.TIMEOUT:
            final_state = guard._final_state
        elif isinstance(result, WorkflowState):
            final_state = result
        else:
            final_state = state.model_copy(update={"status": WorkflowStatus.COMPLETED})

    except Exception as exc:
        logger.exception(
            "run_watchlist_scan: failed workflow_id=%s: %s", wf_id, exc
        )
        final_state = state.model_copy(
            update={"status": WorkflowStatus.FAILED, "error_detail": str(exc)}
        )

    logger.info(
        "run_watchlist_scan: workflow_id=%s status=%s cost=$%.4f",
        wf_id,
        final_state.status.value,
        final_state.cost_usd,
    )

    return {
        "workflow_id": str(wf_id),
        "status": final_state.status.value,
        "cost_usd": final_state.cost_usd,
    }


# ── Celery task ────────────────────────────────────────────────────────────────


@shared_task(
    name="ai.run_watchlist_scan",
    bind=True,
    time_limit=_WS_CFG.hard_limit_seconds,
    soft_time_limit=_WS_CFG.soft_limit_seconds,
    max_retries=1,
    acks_late=True,
)
def run_watchlist_scan(
    self,
    tenant_id: str,
    user_id: str,
    workflow_id: str | None = None,
) -> dict:
    """Celery task: orchestrate the Watchlist Scan workflow.

    Args:
        tenant_id:   Tenant UUID string.
        user_id:     User UUID string (system user for automated runs).
        workflow_id: Optional pre-generated workflow UUID string.

    Returns:
        dict with workflow_id, status, cost_usd.
    """
    logger.info(
        "run_watchlist_scan: starting tenant_id=%s", tenant_id
    )
    return asyncio.get_event_loop().run_until_complete(
        _run_watchlist_scan_async(
            tenant_id=tenant_id,
            user_id=user_id,
            workflow_id=workflow_id,
        )
    )
