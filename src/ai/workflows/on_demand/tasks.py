"""
ai.workflows.on_demand.tasks — Celery task: on_demand_analysis_task.

Celery task for triggering an on-demand company analysis workflow (Mode B).

Steps:
  1. Open LangfuseWorkflowTracer trace.
  2. Construct WorkflowState.
  3. Create workflow_run DB row.
  4. Invoke graph.
  5. Persist final state + update status.
  6. WebSocket notification via WorkflowNotifier.
  7. Catch SoftTimeLimitExceeded → status=TIMEOUT, persist, notify.

PLAN-F-007 TASK-007
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, AsyncGenerator
from uuid import UUID

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded

from src.ai.workflows.on_demand.graph import build_on_demand_graph
from src.ai.workflows.state import WorkflowState, WorkflowStatus, WorkflowType
from src.ai.workflows.timeout_guard import WORKFLOW_TIMEOUT_CONFIGS, WorkflowSoftTimeoutGuard
from src.ai.workflows.tracer import LangfuseWorkflowTracer
from src.storage.repositories.workflow_run_repository import WorkflowRunRepository

_OD_CFG = WORKFLOW_TIMEOUT_CONFIGS[WorkflowType.ON_DEMAND]

logger = logging.getLogger(__name__)


# ── Lazy imports to avoid circular dependencies at module level ───────────────


def _get_langfuse_client() -> Any | None:
    """Return a Langfuse client if LANGFUSE_HOST is configured, else None."""
    try:
        from src.config.settings import get_settings
        settings = get_settings()
        if not settings.LANGFUSE_HOST or not settings.LANGFUSE_SECRET_KEY:
            return None
        from langfuse import Langfuse
        return Langfuse(
            secret_key=settings.LANGFUSE_SECRET_KEY,
            public_key=settings.LANGFUSE_PUBLIC_KEY,
            host=settings.LANGFUSE_HOST,
        )
    except Exception:
        logger.exception("Failed to create Langfuse client")
        return None


def _get_registry() -> Any:
    """Return the agent registry (lazy to avoid import-time side-effects)."""
    from src.ai.startup import get_agent_registry
    return get_agent_registry()


@asynccontextmanager
async def _get_db_session() -> AsyncGenerator[Any, None]:
    """Provide an async SQLAlchemy session."""
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


class WorkflowNotifier:
    """WebSocket push notification on workflow completion.

    No-op if client is disconnected or WebSocket manager is unavailable.
    """

    @staticmethod
    async def notify(workflow_id: str, status: str, tenant_id: str) -> None:
        """Push a status update via WebSocket.

        Args:
            workflow_id: UUID of the completed workflow run.
            status: Final status string.
            tenant_id: Tenant identifier for routing.
        """
        try:
            from src.api.websocket.workflow_notifier import push_workflow_update
            await push_workflow_update(
                workflow_id=workflow_id,
                status=status,
                tenant_id=tenant_id,
            )
        except Exception:
            # WebSocket notifications are best-effort — never break the task
            logger.debug(
                "WorkflowNotifier: no-op for workflow_id=%s (WebSocket unavailable)",
                workflow_id,
            )


async def _run_on_demand_analysis(
    workflow_id: str,
    company_id: str,
    tenant_id: str,
    user_id: str,
) -> dict:
    """Async core of the on-demand analysis task (extracted for testability).

    Returns:
        dict with workflow_id, status, and cost_usd.
    """
    wf_id = UUID(workflow_id)
    company_uuid = UUID(company_id)
    tenant_uuid = UUID(tenant_id)
    user_uuid = UUID(user_id)

    state = WorkflowState(
        workflow_id=wf_id,
        workflow_type=WorkflowType.ON_DEMAND,
        tenant_id=tenant_uuid,
        user_id=user_uuid,
        company_id=company_uuid,
        started_at=datetime.now(tz=timezone.utc),
    )

    langfuse_client = _get_langfuse_client()
    tracer = LangfuseWorkflowTracer(state=state, client=langfuse_client)

    try:
        registry = _get_registry()
    except Exception:
        logger.warning("Agent registry unavailable; using None registry stub")
        registry = None

    graph = build_on_demand_graph(
        registry=registry,
        cost_ceiling_usd=1.50,
        pg_checkpointer=None,
    )

    with tracer:
        async with _get_db_session() as session:
            repo = WorkflowRunRepository(session)
            await repo.create(state)

        final_state: WorkflowState = state
        try:
            async with _get_db_session() as guard_session:
                guard_repo = WorkflowRunRepository(guard_session)
                guard = WorkflowSoftTimeoutGuard(state, guard_repo, langfuse_client)
                async with guard:
                    result_state_dict = await graph.ainvoke(state)

            # ainvoke may return a WorkflowState or a dict
            if guard._final_state.status == WorkflowStatus.TIMEOUT:
                # Guard handled SoftTimeLimitExceeded and persisted partial state
                final_state = guard._final_state
            elif isinstance(result_state_dict, WorkflowState):
                final_state = result_state_dict
            else:
                final_state = state.model_copy(
                    update={"status": WorkflowStatus.COMPLETED}
                )

        except Exception as exc:
            logger.exception(
                "on_demand_analysis_task failed for workflow=%s: %s",
                workflow_id,
                exc,
            )
            final_state = state.model_copy(
                update={"status": WorkflowStatus.FAILED, "error_detail": str(exc)}
            )

        async with _get_db_session() as session:
            repo = WorkflowRunRepository(session)
            await repo.save_final_state(wf_id, final_state)

        await WorkflowNotifier.notify(
            workflow_id=workflow_id,
            status=final_state.status.value,
            tenant_id=tenant_id,
        )

    return {
        "workflow_id": workflow_id,
        "status": final_state.status.value,
        "cost_usd": final_state.cost_usd,
    }


@shared_task(
    name="ai.on_demand_analysis",
    bind=True,
    time_limit=_OD_CFG.hard_limit_seconds,
    soft_time_limit=_OD_CFG.soft_limit_seconds,
    max_retries=0,
)
def on_demand_analysis_task(
    self,
    workflow_id: str,
    company_id: str,
    tenant_id: str,
    user_id: str,
) -> dict:
    """Celery task: run on-demand company analysis.

    Dispatched by POST /api/v1/companies/{company_id}/analysis.

    Args:
        workflow_id: Pre-generated UUID for the workflow run.
        company_id: UUID of the company to analyse.
        tenant_id: Tenant identifier (from JWT).
        user_id: User identifier (from JWT).

    Returns:
        dict with workflow_id, status, and cost_usd.
    """
    return asyncio.get_event_loop().run_until_complete(
        _run_on_demand_analysis(
            workflow_id=workflow_id,
            company_id=company_id,
            tenant_id=tenant_id,
            user_id=user_id,
        )
    )
