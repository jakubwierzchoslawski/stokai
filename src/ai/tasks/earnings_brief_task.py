"""
ai.tasks.earnings_brief_task — Celery tasks for the Earnings Risk Brief workflow.

Tasks defined here:
  detect_t1_earnings: Beat task (*/15 * * * *) — queries upcoming earnings in
    the next 24 h for each tenant and dispatches earnings_brief_task when no
    brief run exists (idempotency guard via EarningsBriefRunRepository.exists()).

  earnings_brief_task: Executes the full EarningsBriefWorkflow for a single
    company's earnings event. Updates earnings_brief_run status on completion.

PLAN-F-009 TASK-004 (detect_t1_earnings) + TASK-005 (earnings_brief_task)
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from typing import Any, AsyncGenerator
from uuid import UUID, uuid4

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded

logger = logging.getLogger(__name__)


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


# ── TASK-004: detect_t1_earnings ──────────────────────────────────────────────


async def _detect_t1_earnings_async(
    tenant_id_str: str | None = None,
) -> dict:
    """Async core: find upcoming earnings and dispatch brief tasks.

    Args:
        tenant_id_str: Optional tenant UUID string. When None, queries all tenants.

    Returns:
        dict with dispatched and skipped counts.
    """
    from src.storage.repositories.earnings_repositories import (
        EarningsEventRepository,
        EarningsBriefRunRepository,
    )

    dispatched = 0
    skipped = 0

    async with _get_db_session() as session:
        event_repo = EarningsEventRepository(session)
        run_repo = EarningsBriefRunRepository(session)

        if tenant_id_str:
            tenant_ids = [UUID(tenant_id_str)]
        else:
            # Production: query distinct tenant_ids from a tenants table.
            # Stub: no tenants → no events. Real deployment wires this via config.
            tenant_ids = []

        for tenant_id in tenant_ids:
            upcoming = await event_repo.get_upcoming(
                tenant_id=tenant_id,
                hours_ahead=24,
            )
            for event in upcoming:
                already_exists = await run_repo.exists(
                    company_id=event.company_id,
                    tenant_id=tenant_id,
                    earnings_date=event.earnings_date,
                )
                if already_exists:
                    logger.debug(
                        "detect_t1_earnings: brief already exists for "
                        "company=%s tenant=%s date=%s — skipping",
                        event.company_id,
                        tenant_id,
                        event.earnings_date,
                    )
                    skipped += 1
                    continue

                # Dispatch the brief task
                earnings_brief_task.apply_async(
                    kwargs={
                        "company_id": str(event.company_id),
                        "tenant_id": str(tenant_id),
                        "earnings_date": event.earnings_date.isoformat(),
                        "user_id": str(uuid4()),  # system user for automated runs
                    },
                    queue="ai",
                )
                logger.info(
                    "detect_t1_earnings: dispatched earnings_brief for "
                    "company=%s tenant=%s date=%s",
                    event.company_id,
                    tenant_id,
                    event.earnings_date,
                )
                dispatched += 1

    return {"dispatched": dispatched, "skipped": skipped}


@shared_task(
    name="ai.detect_t1_earnings",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def detect_t1_earnings(self) -> dict:
    """Beat task: scan for T-1 earnings events and dispatch brief tasks.

    Runs every 15 minutes (configured in celery_app.beat_schedule).

    Idempotent: skips companies that already have an earnings_brief_run row
    for the target earnings_date (UNIQUE constraint guard).

    Returns:
        dict with dispatched and skipped counts.
    """
    try:
        return asyncio.get_event_loop().run_until_complete(
            _detect_t1_earnings_async()
        )
    except Exception as exc:
        logger.exception("detect_t1_earnings failed: %s", exc)
        raise self.retry(exc=exc)


# ── TASK-005: earnings_brief_task ─────────────────────────────────────────────


async def _run_earnings_brief_async(
    company_id: str,
    tenant_id: str,
    earnings_date_str: str,
    user_id: str,
) -> dict:
    """Async core of the earnings brief task.

    Steps:
      1. Create earnings_brief_run row with status='running'.
      2. Construct EarningsBriefState.
      3. Run EarningsBriefWorkflow.
      4. Update earnings_brief_run status to 'completed' or 'hil'.
      5. Return summary dict.

    Returns:
        dict with workflow_id, status, confidence, cost_usd.
    """
    from src.storage.repositories.earnings_repositories import (
        EarningsBriefRunRepository,
        EarningsBriefRunCreate,
    )
    from src.ai.workflows.earnings_brief.state import EarningsBriefState
    from src.ai.workflows.earnings_brief.workflow import build_earnings_brief_workflow

    workflow_id = uuid4()
    company_uuid = UUID(company_id)
    tenant_uuid = UUID(tenant_id)
    user_uuid = UUID(user_id)
    earnings_date = date.fromisoformat(earnings_date_str)

    # Step 1: Create brief run row (idempotency: UNIQUE key may already exist)
    async with _get_db_session() as session:
        run_repo = EarningsBriefRunRepository(session)
        brief_run = await run_repo.insert(
            EarningsBriefRunCreate(
                workflow_id=workflow_id,
                company_id=company_uuid,
                tenant_id=tenant_uuid,
                earnings_date=earnings_date,
                status="running",
            )
        )
        run_id = brief_run.run_id

    # Step 2: Construct initial state
    state = EarningsBriefState(
        workflow_id=workflow_id,
        tenant_id=tenant_uuid,
        user_id=user_uuid,
        company_id=company_uuid,
        earnings_date=earnings_date,
        started_at=datetime.now(tz=timezone.utc),
    )

    # Step 3: Run workflow
    try:
        registry = _get_registry()
    except Exception:
        logger.warning("Agent registry unavailable; using None stub")
        registry = None

    workflow = build_earnings_brief_workflow(
        registry=registry,
        cost_ceiling_usd=0.50,
    )

    try:
        final_state = await workflow.ainvoke(state)
        status = "hil" if final_state.requires_hil else "completed"
        confidence = final_state.overall_confidence
        cost_usd = final_state.cost_usd
        scenario_tree_dict = (
            final_state.scenario_tree.model_dump()
            if final_state.scenario_tree
            else None
        )

    except SoftTimeLimitExceeded:
        logger.warning(
            "earnings_brief_task soft time limit exceeded: workflow_id=%s", workflow_id
        )
        status = "failed"
        confidence = None
        cost_usd = state.cost_usd
        scenario_tree_dict = None

    except Exception as exc:
        logger.exception(
            "earnings_brief_task failed: workflow_id=%s company=%s: %s",
            workflow_id,
            company_id,
            exc,
        )
        status = "failed"
        confidence = None
        cost_usd = state.cost_usd
        scenario_tree_dict = None

    # Step 4: Update brief run status
    async with _get_db_session() as session:
        run_repo = EarningsBriefRunRepository(session)
        await run_repo.update_status(
            run_id=run_id,
            status=status,
            scenario_tree=scenario_tree_dict,
            confidence=confidence,
            cost_usd=cost_usd,
        )

    logger.info(
        "earnings_brief_task completed: workflow_id=%s status=%s confidence=%s",
        workflow_id,
        status,
        confidence,
    )

    return {
        "workflow_id": str(workflow_id),
        "status": status,
        "confidence": confidence,
        "cost_usd": cost_usd,
    }


@shared_task(
    name="ai.earnings_brief",
    time_limit=600,
    soft_time_limit=240,
    max_retries=0,
)
def earnings_brief_task(
    company_id: str,
    tenant_id: str,
    earnings_date: str,
    user_id: str,
) -> dict:
    """Celery task: run the Earnings Risk Brief workflow for one company.

    Dispatched by detect_t1_earnings when a T-1 earnings event is detected.

    Args:
        company_id: UUID of the company (string).
        tenant_id: Tenant UUID (string).
        earnings_date: ISO date string (YYYY-MM-DD).
        user_id: User UUID string (system user for automated runs).

    Returns:
        dict with workflow_id, status, confidence, cost_usd.
    """
    return asyncio.get_event_loop().run_until_complete(
        _run_earnings_brief_async(
            company_id=company_id,
            tenant_id=tenant_id,
            earnings_date_str=earnings_date,
            user_id=user_id,
        )
    )
