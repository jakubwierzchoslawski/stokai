"""
ai.workflows.watchlist_scan_nodes — All nodes for the Watchlist Scan workflow.

Provides DeterministicNodes and AgentNodes used by the WatchlistScanWorkflow
LangGraph graph (PLAN-F-008).

DeterministicNodes:
  fetch_scoped_companies   — merges watchlist + portfolio company IDs (dedup)
  fetch_today_events       — fetches today's geo-events for scoped companies
  fetch_score_changes      — fetches non-zero score deltas for scoped companies
  fetch_analogies          — fetches historical analogies per event_id
  evaluate_quality         — calls Tier1JudgeService, sets overall_confidence
  hil_enqueue              — enqueues in HIL queue with 17:45 UTC deadline
  block_and_notify         — logs, does not dispatch
  dispatch                 — inserts Brief, sends email
  dispatch_high_anomalies  — fire-and-forget event_deep_dive_task per anomaly

AgentNodes:
  filter_relevant_events   — filters today_events to relevant ones (LLM)
  detect_anomalies         — detects anomalies, populates high_anomaly_company_ids
  run_watchlist_analyst    — main analyst: sets overall_confidence, recommendations
  narrative_writer         — produces final report dict

PLAN-F-008 TASK-002, TASK-003, TASK-004, TASK-014, TASK-016
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from src.ai.workflows.cost_guard import CostCeilingGuard
from src.ai.workflows.watchlist_scan_state import WatchlistScanState

logger = logging.getLogger(__name__)

# Cost ceiling for the watchlist scan workflow
WATCHLIST_COST_CEILING_USD = 1.00
_COST_WARNING_THRESHOLD_USD = 0.80

# HIL deadline for watchlist scan: 17:45 UTC
_HIL_DEADLINE_HOUR = 17
_HIL_DEADLINE_MINUTE = 45


# ── DeterministicNodes ────────────────────────────────────────────────────────


async def fetch_scoped_companies(
    state: WatchlistScanState,
    *,
    watchlist_repo: Any,
    portfolio_repo: Any,
) -> WatchlistScanState:
    """Fetch watchlist and portfolio company IDs and merge them (dedup).

    Sets state.watchlist_companies, state.portfolio_companies, and
    state.scoped_company_ids (deduplicated union as a list).

    Args:
        state: Current WatchlistScanState.
        watchlist_repo: Repository for fetching user watchlist.
        portfolio_repo: Repository for fetching user portfolio.

    Returns:
        Updated state with scoped_company_ids populated.
    """
    watchlist_ids: list[UUID] = await watchlist_repo.list_company_ids(
        user_id=state.user_id,
        tenant_id=state.tenant_id,
    )
    portfolio_ids: list[UUID] = await portfolio_repo.list_company_ids(
        user_id=state.user_id,
        tenant_id=state.tenant_id,
    )

    # Deduplicate preserving order: watchlist first, then portfolio additions
    seen: set[UUID] = set()
    scoped: list[UUID] = []
    for cid in watchlist_ids + portfolio_ids:
        if cid not in seen:
            seen.add(cid)
            scoped.append(cid)

    logger.debug(
        "fetch_scoped_companies: watchlist=%d portfolio=%d scoped=%d",
        len(watchlist_ids),
        len(portfolio_ids),
        len(scoped),
    )

    return state.model_copy(
        update={
            "watchlist_companies": watchlist_ids,
            "portfolio_companies": portfolio_ids,
            "scoped_company_ids": scoped,
        }
    )


async def fetch_today_events(
    state: WatchlistScanState,
    *,
    geo_event_repo: Any,
) -> WatchlistScanState:
    """Fetch today's geo-events for all scoped companies.

    Args:
        state: Current WatchlistScanState (must have scoped_company_ids set).
        geo_event_repo: Repository for fetching geo-events.

    Returns:
        Updated state with today_events populated.
    """
    if not state.scoped_company_ids:
        logger.warning("fetch_today_events: scoped_company_ids is empty")
        return state

    events: list[dict] = await geo_event_repo.list_for_companies(
        company_ids=state.scoped_company_ids,
        tenant_id=state.tenant_id,
        since_date=datetime.now(tz=timezone.utc).date(),
    )

    logger.debug(
        "fetch_today_events: fetched %d events for %d companies",
        len(events),
        len(state.scoped_company_ids),
    )

    return state.model_copy(update={"today_events": events})


async def fetch_score_changes(
    state: WatchlistScanState,
    *,
    score_repo: Any,
) -> WatchlistScanState:
    """Fetch non-zero score deltas for scoped companies since yesterday.

    Only includes records where the score delta is non-zero.

    Args:
        state: Current WatchlistScanState (must have scoped_company_ids set).
        score_repo: Repository for fetching score changes.

    Returns:
        Updated state with score_changes populated (non-zero deltas only).
    """
    if not state.scoped_company_ids:
        return state

    raw_changes: list[dict] = await score_repo.list_score_changes(
        company_ids=state.scoped_company_ids,
        tenant_id=state.tenant_id,
    )

    # Filter to non-zero deltas
    nonzero = [c for c in raw_changes if c.get("delta", 0) != 0]

    logger.debug(
        "fetch_score_changes: %d total, %d non-zero deltas",
        len(raw_changes),
        len(nonzero),
    )

    return state.model_copy(update={"score_changes": nonzero})


async def fetch_analogies(
    state: WatchlistScanState,
    *,
    analogy_repo: Any,
) -> WatchlistScanState:
    """Fetch historical analogies for each relevant event.

    Builds a dict keyed by event_id with analogy data.

    Args:
        state: Current WatchlistScanState (must have relevant_events set).
        analogy_repo: Repository for fetching analogies.

    Returns:
        Updated state with analogies dict populated.
    """
    if not state.relevant_events:
        return state

    event_ids = [e.get("event_id") for e in state.relevant_events if e.get("event_id")]
    analogies: dict = await analogy_repo.get_analogies_for_events(
        event_ids=event_ids,
        tenant_id=state.tenant_id,
    )

    logger.debug(
        "fetch_analogies: fetched analogies for %d events",
        len(analogies),
    )

    return state.model_copy(update={"analogies": analogies})


# ── AgentNodes ────────────────────────────────────────────────────────────────


async def filter_relevant_events(
    state: WatchlistScanState,
    *,
    agent: Any,
    cost_guard: CostCeilingGuard | None = None,
) -> WatchlistScanState:
    """LLM agent: filter today_events to those relevant to the watchlist/portfolio.

    Args:
        state: Current WatchlistScanState.
        agent: Agent instance with invoke(state) method.
        cost_guard: Optional CostCeilingGuard; raises WorkflowCostLimitError if
                    the cost ceiling is reached.

    Returns:
        Updated state with relevant_events populated.
    """
    if cost_guard is not None:
        cost_guard.check(state)

    output = agent.invoke(state)

    new_cost = state.cost_usd + getattr(output, "cost_usd", 0.0)
    if new_cost >= _COST_WARNING_THRESHOLD_USD:
        logger.warning(
            "filter_relevant_events: cost $%.4f approaching ceiling $%.2f",
            new_cost,
            WATCHLIST_COST_CEILING_USD,
        )

    relevant = getattr(output, "relevant_events", state.today_events)

    return state.model_copy(
        update={
            "relevant_events": relevant,
            "cost_usd": new_cost,
        }
    )


async def detect_anomalies(
    state: WatchlistScanState,
    *,
    agent: Any,
    cost_guard: CostCeilingGuard | None = None,
) -> WatchlistScanState:
    """LLM agent: detect anomalies in score changes and events.

    Populates state.anomalies and state.high_anomaly_company_ids.

    Args:
        state: Current WatchlistScanState.
        agent: Agent instance with invoke(state) method.
        cost_guard: Optional CostCeilingGuard.

    Returns:
        Updated state with anomalies and high_anomaly_company_ids populated.
    """
    if cost_guard is not None:
        cost_guard.check(state)

    output = agent.invoke(state)

    new_cost = state.cost_usd + getattr(output, "cost_usd", 0.0)
    if new_cost >= _COST_WARNING_THRESHOLD_USD:
        logger.warning(
            "detect_anomalies: cost $%.4f approaching ceiling $%.2f",
            new_cost,
            WATCHLIST_COST_CEILING_USD,
        )

    anomalies = getattr(output, "anomalies", [])
    high_anomaly_ids: list[UUID] = getattr(output, "high_anomaly_company_ids", [])

    return state.model_copy(
        update={
            "anomalies": anomalies,
            "high_anomaly_company_ids": high_anomaly_ids,
            "cost_usd": new_cost,
        }
    )


async def run_watchlist_analyst(
    state: WatchlistScanState,
    *,
    agent: Any,
    cost_guard: CostCeilingGuard | None = None,
) -> WatchlistScanState:
    """LLM agent: main watchlist analyst.

    Produces recommendations and sets overall_confidence.

    Args:
        state: Current WatchlistScanState.
        agent: Agent instance with invoke(state) method.
        cost_guard: Optional CostCeilingGuard.

    Returns:
        Updated state with recommendations and overall_confidence set.
    """
    if cost_guard is not None:
        cost_guard.check(state)

    output = agent.invoke(state)

    new_cost = state.cost_usd + getattr(output, "cost_usd", 0.0)
    if new_cost >= _COST_WARNING_THRESHOLD_USD:
        logger.warning(
            "run_watchlist_analyst: cost $%.4f approaching ceiling $%.2f",
            new_cost,
            WATCHLIST_COST_CEILING_USD,
        )

    recommendations = getattr(output, "recommendations", [])
    overall_confidence = getattr(output, "overall_confidence", 0.0)
    confidence_scores = dict(state.confidence_scores)
    confidence_scores["watchlist_analyst"] = overall_confidence

    return state.model_copy(
        update={
            "recommendations": recommendations,
            "overall_confidence": overall_confidence,
            "confidence_scores": confidence_scores,
            "cost_usd": new_cost,
        }
    )


async def narrative_writer(
    state: WatchlistScanState,
    *,
    agent: Any,
    cost_guard: CostCeilingGuard | None = None,
) -> WatchlistScanState:
    """LLM agent: produce the final report dict.

    Args:
        state: Current WatchlistScanState.
        agent: Agent instance with invoke(state) method.
        cost_guard: Optional CostCeilingGuard.

    Returns:
        Updated state with report populated.
    """
    if cost_guard is not None:
        cost_guard.check(state)

    output = agent.invoke(state)

    new_cost = state.cost_usd + getattr(output, "cost_usd", 0.0)
    report = getattr(output, "report", None)
    if report is None:
        report = {
            "recommendations": state.recommendations,
            "anomalies": state.anomalies,
            "confidence": state.overall_confidence,
        }

    return state.model_copy(
        update={
            "report": report,
            "cost_usd": new_cost,
        }
    )


# ── Routing / dispatch nodes ──────────────────────────────────────────────────


async def evaluate_quality(
    state: WatchlistScanState,
    *,
    tier1_judge: Any,
) -> WatchlistScanState:
    """DeterministicNode: call Tier1JudgeService, set overall_confidence.

    Args:
        state: Current WatchlistScanState.
        tier1_judge: Tier1JudgeService instance with evaluate(state) method.

    Returns:
        Updated state with overall_confidence set.
    """
    result = await tier1_judge.evaluate(state)
    confidence = getattr(result, "confidence", state.overall_confidence)

    logger.info(
        "evaluate_quality: overall_confidence=%.4f",
        confidence,
    )

    return state.model_copy(update={"overall_confidence": confidence})


async def hil_enqueue(
    state: WatchlistScanState,
    *,
    hil_repo: Any,
) -> WatchlistScanState:
    """DeterministicNode: enqueue state in the HIL queue with 17:45 UTC deadline.

    Args:
        state: Current WatchlistScanState.
        hil_repo: HILQueueRepository instance.

    Returns:
        Updated state with requires_hil=True.
    """
    from src.storage.repositories.hil_queue_repository import HILQueueItemCreate

    now = datetime.now(tz=timezone.utc)
    # Compute the 17:45 UTC deadline
    candidate = now.replace(
        hour=_HIL_DEADLINE_HOUR,
        minute=_HIL_DEADLINE_MINUTE,
        second=0,
        microsecond=0,
    )
    from datetime import timedelta
    if candidate <= now:
        candidate = candidate + timedelta(days=1)
    deadline = candidate

    lc_checkpoint_id = f"hil:{state.workflow_id}"

    dto = HILQueueItemCreate(
        workflow_run_id=state.workflow_id,
        workflow_type="watchlist_scan",
        user_id=state.user_id,
        tenant_id=state.tenant_id,
        confidence=state.overall_confidence,
        scheduled_send_at=deadline,
        lc_checkpoint_id=lc_checkpoint_id,
    )

    await hil_repo.create(dto)

    logger.info(
        "hil_enqueue: queued workflow %s with deadline %s",
        state.workflow_id,
        deadline.isoformat(),
    )

    return state.model_copy(
        update={
            "requires_hil": True,
            "hil_reason": f"confidence={state.overall_confidence:.4f} < 0.70",
        }
    )


async def block_and_notify(
    state: WatchlistScanState,
) -> WatchlistScanState:
    """DeterministicNode: log and block — do NOT dispatch.

    Args:
        state: Current WatchlistScanState.

    Returns:
        Updated state (unchanged — no dispatch occurs).
    """
    logger.warning(
        "block_and_notify: watchlist scan blocked for workflow=%s "
        "overall_confidence=%.4f (below 0.40 threshold)",
        state.workflow_id,
        state.overall_confidence,
    )

    return state.model_copy(
        update={
            "requires_hil": False,
            "hil_reason": f"blocked: confidence={state.overall_confidence:.4f} < 0.40",
        }
    )


async def dispatch(
    state: WatchlistScanState,
    *,
    brief_repo: Any,
    email_service: Any,
) -> WatchlistScanState:
    """DeterministicNode: insert Brief row and send email.

    Args:
        state: Current WatchlistScanState.
        brief_repo: IBriefRepository instance.
        email_service: Email service with send_watchlist_scan(state) method.

    Returns:
        Updated state with brief_id set.
    """
    from src.ai.workflows.event_deep_dive.state import BriefCreate

    brief = BriefCreate(
        brief_id=uuid4(),
        type="watchlist_scan",
        event_id=uuid4(),   # watchlist scans are not tied to a single event
        tenant_id=state.tenant_id,
        content=state.report or {},
        confidence=state.overall_confidence,
        cost_usd=state.cost_usd,
        cost_limited=False,
    )

    orm_row = await brief_repo.insert_memo(brief)

    logger.info(
        "dispatch: inserted Brief brief_id=%s for workflow=%s",
        brief.brief_id,
        state.workflow_id,
    )

    # Send email
    await email_service.send_watchlist_scan(state)

    return state.model_copy(update={"brief_id": orm_row.brief_id})


async def dispatch_high_anomalies(
    state: WatchlistScanState,
    *,
    celery_app: Any,
) -> WatchlistScanState:
    """DeterministicNode: fire-and-forget event_deep_dive_task per high-anomaly company.

    Dispatches non-blocking Celery tasks for each company in
    state.high_anomaly_company_ids. Does not wait for results.

    Args:
        state: Current WatchlistScanState.
        celery_app: Celery application instance.

    Returns:
        State unchanged (dispatch is non-blocking).
    """
    if not state.high_anomaly_company_ids:
        logger.debug("dispatch_high_anomalies: no high-anomaly companies, skipping")
        return state

    for company_id in state.high_anomaly_company_ids:
        try:
            celery_app.send_task(
                "ai.event_deep_dive",
                kwargs={
                    "company_id": str(company_id),
                    "tenant_id": str(state.tenant_id),
                    "user_id": str(state.user_id),
                    "workflow_id": str(uuid4()),
                    "triggered_by": "watchlist_scan_anomaly",
                },
            )
            logger.info(
                "dispatch_high_anomalies: fired event_deep_dive for company=%s",
                company_id,
            )
        except Exception:
            # Fire-and-forget: log but never raise
            logger.exception(
                "dispatch_high_anomalies: failed to dispatch for company=%s",
                company_id,
            )

    return state
