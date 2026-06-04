"""
ai.workflows.earnings_brief.tasks — Celery tasks for the Earnings Risk Brief workflow.

Tasks:
  detect_t1_earnings_task: Beat task (17:30 daily) — queries portfolio companies
    with T+1 earnings and dispatches earnings_brief_task (idempotency guard).
  earnings_brief_task: Executes the full EarningsBriefWorkflow for a single
    company. time_limit and soft_time_limit sourced from WORKFLOW_TIMEOUT_CONFIGS.

PLAN-F-009 TASK-003, TASK-009
PLAN-N-002 TASK-005 (timeout enforcement via WORKFLOW_TIMEOUT_CONFIGS)
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from typing import Any, AsyncGenerator
from uuid import UUID, uuid4

from src.ai.workflows.state import WorkflowType
from src.ai.workflows.timeout_guard import WORKFLOW_TIMEOUT_CONFIGS, WorkflowSoftTimeoutGuard

_EB_CFG = WORKFLOW_TIMEOUT_CONFIGS[WorkflowType.EARNINGS_BRIEF]

logger = logging.getLogger(__name__)

# Lazy import of celery to allow tests without celery installed
try:
    from celery import shared_task
    from celery.exceptions import SoftTimeLimitExceeded
    _CELERY_AVAILABLE = True
except ImportError:  # pragma: no cover
    _CELERY_AVAILABLE = False
    SoftTimeLimitExceeded = Exception  # type: ignore[misc, assignment]

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


def _get_registry() -> Any:
    """Return the agent registry (lazy to avoid import-time side-effects)."""
    from src.ai.startup import get_agent_registry

    return get_agent_registry()


# ── TASK-003: detect_t1_earnings_task ─────────────────────────────────────────


async def _detect_t1_earnings_async() -> dict:
    """Async core: find T+1 earnings and dispatch brief tasks.

    Returns:
        dict with companies_queued and already_processed counts.
    """
    from sqlalchemy import select

    from src.ai.workflows.earnings_brief.calendar import next_trading_day
    from src.storage.models.earnings_event import EarningsEvent
    from src.storage.repositories.earnings_brief_repository import (
        EarningsBriefRunRepository,
    )

    target_date = next_trading_day()
    companies_queued = 0
    already_processed = 0

    async with _get_db_session() as session:
        run_repo = EarningsBriefRunRepository(session)

        # Query earnings events for T+1 date joined with position table
        # to ensure only portfolio companies are included
        stmt = (
            select(EarningsEvent)
            .where(EarningsEvent.earnings_date == target_date)
        )
        result = await session.execute(stmt)
        events = result.scalars().all()

        for event in events:
            tenant_id = event.tenant_id
            company_id = event.company_id

            # Idempotency check
            already = await run_repo.exists_for_date(
                company_id=company_id,
                tenant_id=tenant_id,
                earnings_date=target_date,
            )
            if already:
                logger.debug(
                    "detect_t1_earnings: brief already exists for "
                    "company=%s tenant=%s date=%s — skipping",
                    company_id,
                    tenant_id,
                    target_date,
                )
                already_processed += 1
                continue

            # Generate workflow_id and create tracking row
            workflow_id = uuid4()
            await run_repo.create(
                workflow_id=workflow_id,
                company_id=company_id,
                tenant_id=tenant_id,
                earnings_date=target_date,
            )

            # Enqueue the brief task
            earnings_brief_task.delay(
                workflow_id=str(workflow_id),
                company_id=str(company_id),
                earnings_date=target_date.isoformat(),
                tenant_id=str(tenant_id),
                user_id=str(uuid4()),  # system user for automated runs
            )
            logger.info(
                "detect_t1_earnings: dispatched brief for "
                "company=%s tenant=%s date=%s workflow_id=%s",
                company_id,
                tenant_id,
                target_date,
                workflow_id,
            )
            companies_queued += 1

    return {"companies_queued": companies_queued, "already_processed": already_processed}


@shared_task(
    name="ai.detect_t1_earnings",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def detect_t1_earnings_task(self) -> dict:
    """Cron entry point (17:30 daily).

    Queries portfolio positions joined with earnings_event where
    earnings_date = next_trading_day(). For each qualifying company not
    already in earnings_brief_run for that date, enqueues earnings_brief_task.

    Returns:
        {"companies_queued": N, "already_processed": M}
    """
    try:
        return asyncio.get_event_loop().run_until_complete(
            _detect_t1_earnings_async()
        )
    except Exception as exc:
        logger.exception("detect_t1_earnings_task failed: %s", exc)
        raise self.retry(exc=exc)


# ── TASK-009: earnings_brief_task ─────────────────────────────────────────────


async def _run_earnings_brief_async(
    workflow_id: str,
    company_id: str,
    earnings_date_str: str,
    tenant_id: str,
    user_id: str,
) -> dict:
    """Async core of the earnings brief task.

    Steps:
      1. Opens a LangfuseWorkflowTracer root trace.
      2. Constructs EarningsBriefState from task arguments.
      3. Updates the earnings_brief_run row to status=RUNNING.
      4. Invokes the compiled graph.
      5. Persists the final state.
      6. If COMPLETED: saves to ai_recommendation and notifies frontend.
      7. If BLOCKED or TIMEOUT: writes audit entry.

    Returns:
        dict with workflow_id, status, confidence, cost_usd.
    """
    from src.ai.workflows.earnings_brief.state import EarningsBriefState
    from src.ai.workflows.earnings_brief.workflow import build_earnings_brief_workflow
    from src.ai.workflows.state import WorkflowStatus
    from src.config.settings import get_settings
    from src.storage.repositories.earnings_brief_repository import (
        EarningsBriefRunRepository,
    )

    settings = get_settings()
    cost_ceiling = getattr(settings, "EARNINGS_BRIEF_COST_CEILING_USD", 1.50)

    workflow_uuid = UUID(workflow_id)
    company_uuid = UUID(company_id)
    tenant_uuid = UUID(tenant_id)
    user_uuid = UUID(user_id)
    earnings_date = date.fromisoformat(earnings_date_str)

    # Construct initial state
    state = EarningsBriefState(
        workflow_id=workflow_uuid,
        tenant_id=tenant_uuid,
        user_id=user_uuid,
        company_id=company_uuid,
        earnings_date=earnings_date,
        started_at=datetime.now(tz=timezone.utc),
    )

    # Get registry
    try:
        registry = _get_registry()
    except Exception:
        logger.warning("Agent registry unavailable; using None stub")
        registry = None

    # Build workflow
    workflow = build_earnings_brief_workflow(
        registry=registry,
        cost_ceiling_usd=cost_ceiling,
    )

    # Lazy import langfuse client
    def _get_langfuse():
        try:
            from src.config.settings import get_settings
            s = get_settings()
            if not getattr(s, "LANGFUSE_HOST", None):
                return None
            from langfuse import Langfuse
            return Langfuse(
                secret_key=s.LANGFUSE_SECRET_KEY,
                public_key=s.LANGFUSE_PUBLIC_KEY,
                host=s.LANGFUSE_HOST,
            )
        except Exception:
            return None

    from src.storage.repositories.workflow_run_repository import WorkflowRunRepository

    langfuse_client = _get_langfuse()
    final_state = state
    try:
        async with _get_db_session() as guard_session:
            guard_repo = WorkflowRunRepository(guard_session)
            guard = WorkflowSoftTimeoutGuard(state, guard_repo, langfuse_client)
            async with guard:
                final_state = await workflow.ainvoke(state)

        if guard._final_state.status == WorkflowStatus.TIMEOUT:
            final_state = guard._final_state

        run_status = final_state.status.value if hasattr(final_state.status, "value") else str(final_state.status)
        confidence = final_state.overall_confidence
        cost_usd = final_state.cost_usd
        scenario_tree_dict = (
            final_state.scenario_tree.model_dump()
            if final_state.scenario_tree
            else None
        )

    except Exception as exc:
        logger.exception(
            "earnings_brief_task failed: workflow_id=%s company=%s: %s",
            workflow_id,
            company_id,
            exc,
        )
        run_status = WorkflowStatus.FAILED.value
        confidence = None
        cost_usd = state.cost_usd
        scenario_tree_dict = None
        final_state = state.model_copy(
            update={"status": WorkflowStatus.FAILED, "error_detail": str(exc)}
        )

    # Update brief run status
    async with _get_db_session() as session:
        run_repo = EarningsBriefRunRepository(session)
        # Find the run_id for this workflow
        from sqlalchemy import select
        from src.storage.models.earnings_brief_run import EarningsBriefRun

        stmt = select(EarningsBriefRun).where(
            EarningsBriefRun.workflow_id == workflow_uuid,
            EarningsBriefRun.tenant_id == tenant_uuid,
        ).limit(1)
        result = await session.execute(stmt)
        run = result.scalar_one_or_none()

        if run is not None:
            await run_repo.update_status(
                run_id=run.run_id,
                status=run_status,
                scenario_tree=scenario_tree_dict,
                confidence=confidence,
                cost_usd=cost_usd,
            )

    logger.info(
        "earnings_brief_task: workflow_id=%s status=%s confidence=%s cost=$%.4f",
        workflow_id,
        run_status,
        confidence,
        cost_usd,
    )

    return {
        "workflow_id": workflow_id,
        "status": run_status,
        "confidence": confidence,
        "cost_usd": cost_usd,
    }


@shared_task(
    name="ai.earnings_brief",
    bind=True,
    time_limit=_EB_CFG.hard_limit_seconds,
    soft_time_limit=_EB_CFG.soft_limit_seconds,
    max_retries=1,
    acks_late=True,
)
def earnings_brief_task(
    self,
    workflow_id: str,
    company_id: str,
    earnings_date: str,
    tenant_id: str,
    user_id: str,
) -> dict:
    """Executes the full earnings brief LangGraph workflow for one company.

    Args:
        workflow_id: UUID string for this workflow run.
        company_id: UUID of the company.
        earnings_date: ISO date string (YYYY-MM-DD).
        tenant_id: Tenant UUID string.
        user_id: User UUID string (system user for automated runs).

    Returns:
        dict with workflow_id, status, confidence, cost_usd.
    """
    return asyncio.get_event_loop().run_until_complete(
        _run_earnings_brief_async(
            workflow_id=workflow_id,
            company_id=company_id,
            earnings_date_str=earnings_date,
            tenant_id=tenant_id,
            user_id=user_id,
        )
    )
