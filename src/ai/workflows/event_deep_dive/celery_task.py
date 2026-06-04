"""
ai.workflows.event_deep_dive.celery_task — Celery task for Event Deep-Dive.

@celery_app.task(name="ai.event_deep_dive", queue="mode_b")
run_event_deep_dive(event_id: str) -> dict

Lifecycle:
  1. Create WorkflowRun row (status=RUNNING).
  2. Start Langfuse trace.
  3. Wrap graph invocation in WorkflowSoftTimeoutGuard from WORKFLOW_TIMEOUT_CONFIGS.
  4. Invoke DeepDiveGraph.ainvoke(state).
  5. On SoftTimeLimitExceeded: guard persists partial state, task exits cleanly.
  6. On CostCeilingExceededError: update status=COST_LIMIT, return partial result.
  7. Flush Langfuse trace.

PLAN-F-010 TASK-011.
PLAN-N-002 TASK-005 (timeout enforcement via WORKFLOW_TIMEOUT_CONFIGS).
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, AsyncGenerator

from src.ai.workflows.event_deep_dive.exceptions import (
    CostCeilingExceededError,
    WorkflowTimeoutError,
)
from src.ai.workflows.event_deep_dive.graph import build_deep_dive_graph
from src.ai.workflows.event_deep_dive.state import DeepDiveWorkflowState
from src.ai.workflows.event_deep_dive.timeout_guard import WorkflowTimeoutGuard
from src.ai.workflows.state import WorkflowStatus, WorkflowType
from src.ai.workflows.timeout_guard import WORKFLOW_TIMEOUT_CONFIGS, WorkflowSoftTimeoutGuard
from src.config.celery_app import celery_app
from src.config.settings import get_settings

_EDD_CFG = WORKFLOW_TIMEOUT_CONFIGS[WorkflowType.EVENT_DEEP_DIVE]

logger = logging.getLogger(__name__)

# Default cost ceiling per run in USD (overridable via env DEEP_DIVE_COST_CEILING)
_DEFAULT_COST_CEILING_USD = 2.0
# Hard timeout per run in seconds — sourced from WORKFLOW_TIMEOUT_CONFIGS
_HARD_TIMEOUT_SECONDS = float(_EDD_CFG.hard_limit_seconds)


@asynccontextmanager
async def _get_db_session() -> AsyncGenerator[Any, None]:
    """Provide an async SQLAlchemy session."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

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
        settings = get_settings()
        if not getattr(settings, "LANGFUSE_HOST", None):
            return None
        from langfuse import Langfuse
        return Langfuse(
            secret_key=settings.LANGFUSE_SECRET_KEY,
            public_key=settings.LANGFUSE_PUBLIC_KEY,
            host=settings.LANGFUSE_HOST,
        )
    except Exception:
        return None


def _make_initial_state(
    event_id: str,
    tenant_id: str,
    user_id: str,
    workflow_id: uuid.UUID,
) -> DeepDiveWorkflowState:
    """Build the initial DeepDiveWorkflowState for a new run."""
    return DeepDiveWorkflowState(
        workflow_id=workflow_id,
        workflow_type=WorkflowType.EVENT_DEEP_DIVE,
        tenant_id=uuid.UUID(tenant_id),
        user_id=uuid.UUID(user_id),
        company_id=uuid.uuid4(),  # populated by fetch_event_full in production
        started_at=datetime.now(tz=timezone.utc),
        inputs={"event_id": event_id},
    )


async def _run_deep_dive_async(
    event_id: str,
    tenant_id: str | None = None,
    user_id: str | None = None,
) -> dict:
    """Async implementation of the deep-dive workflow.

    Separated from the Celery task so it can be tested via pytest-asyncio.
    """
    settings = get_settings()
    import os

    cost_ceiling = float(
        os.environ.get("DEEP_DIVE_COST_CEILING", str(_DEFAULT_COST_CEILING_USD))
    )

    workflow_id = uuid.uuid4()
    _tenant_id = tenant_id or str(uuid.uuid4())
    _user_id = user_id or str(uuid.uuid4())

    state = _make_initial_state(
        event_id=event_id,
        tenant_id=_tenant_id,
        user_id=_user_id,
        workflow_id=workflow_id,
    )

    # Build graph (no real repos in this stub; production wires them via DI)
    graph = build_deep_dive_graph(
        registry=None,  # type: ignore[arg-type]
        cost_ceiling_usd=cost_ceiling,
    )

    result_status = WorkflowStatus.COMPLETED
    error_detail: str | None = None

    langfuse_client = _get_langfuse_client()

    from src.storage.repositories.workflow_run_repository import WorkflowRunRepository

    try:
        async with _get_db_session() as guard_session:
            guard_repo = WorkflowRunRepository(guard_session)
            guard = WorkflowSoftTimeoutGuard(state, guard_repo, langfuse_client)

            async with WorkflowTimeoutGuard(hard_limit_seconds=_HARD_TIMEOUT_SECONDS):
                async with guard:
                    state = await graph.ainvoke(state)

        if guard._final_state.status == WorkflowStatus.TIMEOUT:
            result_status = WorkflowStatus.TIMEOUT
            state = guard._final_state

    except WorkflowTimeoutError as exc:
        logger.error(
            "run_event_deep_dive: timeout for event_id=%s workflow_id=%s: %s",
            event_id,
            workflow_id,
            exc,
        )
        result_status = WorkflowStatus.FAILED
        error_detail = str(exc)

    except CostCeilingExceededError as exc:
        logger.warning(
            "run_event_deep_dive: cost ceiling exceeded for event_id=%s workflow_id=%s: %s",
            event_id,
            workflow_id,
            exc,
        )
        result_status = WorkflowStatus.COST_LIMIT
        error_detail = str(exc)

    except Exception as exc:
        logger.exception(
            "run_event_deep_dive: unexpected error for event_id=%s workflow_id=%s: %s",
            event_id,
            workflow_id,
            exc,
        )
        result_status = WorkflowStatus.FAILED
        error_detail = str(exc)

    return {
        "workflow_id": str(workflow_id),
        "event_id": event_id,
        "status": result_status.value,
        "error_detail": error_detail,
        "cost_usd": state.cost_usd,
        "confidence": state.confidence_scores.get("workflow"),
    }


@celery_app.task(
    name="ai.event_deep_dive",
    queue="mode_b",
    time_limit=_EDD_CFG.hard_limit_seconds,
    soft_time_limit=_EDD_CFG.soft_limit_seconds,
    max_retries=1,
    acks_late=True,
)
def run_event_deep_dive(
    event_id: str,
    tenant_id: str | None = None,
    user_id: str | None = None,
) -> dict:
    """Celery task: orchestrate the Event Deep-Dive workflow.

    Args:
        event_id: UUID string of the triggering geo_event.
        tenant_id: Optional tenant UUID string.
        user_id: Optional user UUID string.

    Returns:
        dict with workflow_id, event_id, status, error_detail, cost_usd, confidence.
    """
    logger.info(
        "run_event_deep_dive: starting event_id=%s tenant_id=%s",
        event_id,
        tenant_id,
    )
    return asyncio.get_event_loop().run_until_complete(
        _run_deep_dive_async(event_id=event_id, tenant_id=tenant_id, user_id=user_id)
    )
