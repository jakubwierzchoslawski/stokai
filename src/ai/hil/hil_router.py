"""
ai.hil.hil_router — LangGraph conditional edge for HIL pause routing.

Implements hil_router_edge(state: WorkflowState) -> str.

When state.requires_hil is True:
  1. Computes scheduled_send_at deadline based on workflow type.
  2. Builds an lc_checkpoint_id from the workflow_id (the actual LangGraph
     checkpoint is managed externally via AsyncPostgresSaver; this module
     stores the correlation key).
  3. Inserts a hil_queue_item row via HILQueueRepository.
  4. Returns "hil" — routing the graph to the hil_pending terminal node.

When state.requires_hil is False:
  Returns "narrative_writer" — routing the graph to the narrative writer node.

Timing windows (Architecture §7.6):
  - MORNING_BRIEF  → next 05:45 UTC
  - WATCHLIST_SCAN → next 17:45 UTC
  - ON_DEMAND      → now + 10 minutes
  - EVENT_DEEP_DIVE / EARNINGS_BRIEF → now + 30 minutes

PLAN-F-013 TASK-003
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from src.ai.workflows.state import WorkflowState, WorkflowType
from src.config.settings import get_settings
from src.storage.repositories.hil_queue_repository import (
    HILQueueItemCreate,
    HILQueueRepository,
)

logger = logging.getLogger(__name__)

# ── Timing constants ──────────────────────────────────────────────────────────
_MORNING_BRIEF_HOUR = 5
_MORNING_BRIEF_MINUTE = 45
_WATCHLIST_HOUR = 17
_WATCHLIST_MINUTE = 45
_ON_DEMAND_DELAY_MINUTES = 10
_EVENT_DEEP_DIVE_DELAY_MINUTES = 30


# ── DB session helper ─────────────────────────────────────────────────────────

@asynccontextmanager
async def _get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide a short-lived async session for the HIL router edge.

    This is a lightweight session factory used only within the conditional edge.
    The main application dependency-injection chain is not available here since
    this function is called as a LangGraph edge, outside the FastAPI request scope.
    """
    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


# ── Scheduling logic ──────────────────────────────────────────────────────────

def compute_scheduled_send_at(
    workflow_type: WorkflowType,
    now: datetime,
) -> datetime:
    """Return the deadline datetime for a workflow type.

    All times are UTC. If the fixed-time deadline (Morning Brief / Watchlist)
    has already passed today, the next-day deadline is returned.

    Args:
        workflow_type: The type of workflow being scheduled.
        now: The current UTC datetime (injected for testability).

    Returns:
        A timezone-aware UTC datetime representing the review deadline.
    """
    if workflow_type == WorkflowType.MORNING_BRIEF:
        return _next_fixed_time(now, _MORNING_BRIEF_HOUR, _MORNING_BRIEF_MINUTE)
    elif workflow_type == WorkflowType.WATCHLIST_SCAN:
        return _next_fixed_time(now, _WATCHLIST_HOUR, _WATCHLIST_MINUTE)
    elif workflow_type == WorkflowType.ON_DEMAND:
        return now + timedelta(minutes=_ON_DEMAND_DELAY_MINUTES)
    else:
        # EVENT_DEEP_DIVE and EARNINGS_BRIEF both get 30-minute windows
        return now + timedelta(minutes=_EVENT_DEEP_DIVE_DELAY_MINUTES)


def _next_fixed_time(now: datetime, hour: int, minute: int) -> datetime:
    """Return the next occurrence of HH:MM UTC that is strictly in the future.

    If today's HH:MM has not yet passed, return today's occurrence.
    Otherwise return tomorrow's occurrence.
    """
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= now:
        candidate = candidate + timedelta(days=1)
    return candidate


# ── Conditional edge ──────────────────────────────────────────────────────────

async def hil_router_edge(state: WorkflowState) -> str:
    """LangGraph conditional edge function.

    Inspects state.requires_hil and routes accordingly.

    Returns:
        "hil" — when requires_hil is True; creates the queue item and parks.
        "narrative_writer" — when requires_hil is False; continues normally.
    """
    if not state.requires_hil:
        logger.debug(
            "hil_router_edge: requires_hil=False for workflow %s — routing to narrative_writer",
            state.workflow_id,
        )
        return "narrative_writer"

    now = datetime.now(tz=timezone.utc)
    scheduled_send_at = compute_scheduled_send_at(state.workflow_type, now)

    # Build a stable checkpoint reference from the workflow_id.
    # In production, the LangGraph AsyncPostgresSaver is configured at the
    # StateGraph compile step and stores checkpoints independently. The
    # lc_checkpoint_id recorded here is the correlation key used by
    # HILResumeService to locate the correct graph checkpoint.
    lc_checkpoint_id = f"hil:{state.workflow_id}"

    dto = HILQueueItemCreate(
        workflow_run_id=state.workflow_id,
        workflow_type=state.workflow_type.value,
        user_id=state.user_id,
        tenant_id=state.tenant_id,
        confidence=state.overall_confidence or 0.0,
        scheduled_send_at=scheduled_send_at,
        lc_checkpoint_id=lc_checkpoint_id,
    )

    try:
        async with _get_db_session() as session:
            repo = HILQueueRepository(session)
            queue_item = await repo.create(dto)
            await session.commit()

        logger.info(
            "hil_router_edge: HIL queue item created item_id=%s workflow_id=%s "
            "tenant_id=%s scheduled_send_at=%s",
            queue_item.item_id,
            state.workflow_id,
            state.tenant_id,
            scheduled_send_at.isoformat(),
        )
    except Exception:
        logger.exception(
            "hil_router_edge: failed to create HIL queue item for workflow %s",
            state.workflow_id,
        )
        raise

    return "hil"
