"""
ai.workflows.morning_brief_nodes — all node functions for the Morning Brief workflow.

Deterministic nodes (no LLM calls):
  - fetch_portfolio_state   — loads positions + watchlist for the user
  - fetch_overnight_events  — queries 24-hour event window
  - fetch_score_changes     — returns nonzero score deltas for portfolio companies
  - fetch_analogies         — returns historical analogies keyed by event_id

Agent nodes (LLM calls with CostCeilingGuard):
  - filter_relevant_events  — selects events material to the portfolio
  - detect_anomalies        — flags statistical outliers
  - run_analyst_agent       — main analyst: recommendations + confidence
  - narrative_writer        — composes final HTML brief

Routing nodes (terminal):
  - hil_queue               — enqueues to HIL queue with 05:45 UTC deadline
  - block_and_log           — logs WARNING, sets BLOCK route, no email
  - dispatch_brief          — inserts Brief row, sends SendGrid email

PLAN-F-006 TASK-003, TASK-004, TASK-005.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from src.ai.workflows.morning_brief_state import ConfidenceRoute, MorningBriefState

logger = logging.getLogger(__name__)

# Morning brief cost ceiling per run (USD) — $2.00 per PLAN-F-006 spec
_COST_CEILING_USD = 2.0
# 80% threshold for context-reduction signal
_REDUCE_CONTEXT_THRESHOLD = 0.80
# HIL deadline for morning brief: 05:45 UTC
_HIL_HOUR = 5
_HIL_MINUTE = 45


# ══════════════════════════════════════════════════════════════════════════════
# DeterministicNodes — TASK-003
# ══════════════════════════════════════════════════════════════════════════════


async def fetch_portfolio_state(
    state: MorningBriefState,
    *,
    portfolio_repo: Any,
    user_id: Any = None,
    tenant_id: Any = None,
) -> MorningBriefState:
    """Load positions and watchlist for the workflow user.

    Calls portfolio_repo.get_positions(user_id, tenant_id) and
    portfolio_repo.get_watchlist(user_id, tenant_id).  Merges the results
    into a single portfolio_state dict.

    Args:
        state: Current MorningBriefState.
        portfolio_repo: Repository with get_positions() and get_watchlist().
        user_id: Override user_id (defaults to state.user_id).
        tenant_id: Override tenant_id (defaults to state.tenant_id).

    Returns:
        Updated state with portfolio_state populated.
    """
    _user_id = user_id or state.user_id
    _tenant_id = tenant_id or state.tenant_id

    positions = await portfolio_repo.get_positions(_user_id, _tenant_id)
    watchlist = await portfolio_repo.get_watchlist(_user_id, _tenant_id)

    portfolio_state = {
        "positions": positions or [],
        "watchlist": watchlist or [],
    }

    logger.debug(
        "fetch_portfolio_state: loaded %d positions, %d watchlist items for user=%s",
        len(portfolio_state["positions"]),
        len(portfolio_state["watchlist"]),
        _user_id,
    )

    return state.model_copy(update={"portfolio_state": portfolio_state})


async def fetch_overnight_events(
    state: MorningBriefState,
    *,
    event_repo: Any,
    lookback_hours: int = 24,
) -> MorningBriefState:
    """Query the event repository for events in the last 24 hours.

    Calls event_repo.get_events_in_window(tenant_id, hours=lookback_hours).

    Args:
        state: Current MorningBriefState.
        event_repo: Repository with get_events_in_window().
        lookback_hours: How many hours back to query (default 24).

    Returns:
        Updated state with events list populated.
    """
    events = await event_repo.get_events_in_window(
        tenant_id=state.tenant_id,
        hours=lookback_hours,
    )

    logger.debug(
        "fetch_overnight_events: fetched %d events for tenant=%s (last %dh)",
        len(events or []),
        state.tenant_id,
        lookback_hours,
    )

    return state.model_copy(update={"events": events or []})


async def fetch_score_changes(
    state: MorningBriefState,
    *,
    score_repo: Any,
) -> MorningBriefState:
    """Fetch nonzero score deltas for portfolio companies since yesterday.

    Calls score_repo.get_score_changes(tenant_id, company_ids) where
    company_ids are extracted from state.portfolio_state['positions'].

    Returns only deltas with delta != 0.0.

    Args:
        state: Current MorningBriefState (portfolio_state must be populated).
        score_repo: Repository with get_score_changes().

    Returns:
        Updated state with score_changes list populated.
    """
    company_ids: list = []
    if state.portfolio_state:
        company_ids = [
            p.get("company_id")
            for p in state.portfolio_state.get("positions", [])
            if p.get("company_id")
        ]

    all_changes = await score_repo.get_score_changes(
        tenant_id=state.tenant_id,
        company_ids=company_ids,
    )

    # Filter to nonzero deltas
    nonzero = [c for c in (all_changes or []) if c.get("delta", 0.0) != 0.0]

    logger.debug(
        "fetch_score_changes: %d nonzero score deltas for tenant=%s",
        len(nonzero),
        state.tenant_id,
    )

    return state.model_copy(update={"score_changes": nonzero})


async def fetch_analogies(
    state: MorningBriefState,
    *,
    analogy_repo: Any,
) -> MorningBriefState:
    """Fetch historical analogies for events in state.events.

    Calls analogy_repo.get_analogies_for_events(event_ids) and returns a dict
    keyed by event_id.

    Args:
        state: Current MorningBriefState (events must be populated).
        analogy_repo: Repository with get_analogies_for_events().

    Returns:
        Updated state with analogies dict populated (keyed by event_id str).
    """
    event_ids = [e.get("event_id") for e in state.events if e.get("event_id")]

    if not event_ids:
        return state.model_copy(update={"analogies": {}})

    raw = await analogy_repo.get_analogies_for_events(event_ids)

    # Normalise to dict[str, list[dict]]
    analogies: dict = {}
    if isinstance(raw, dict):
        analogies = {str(k): v for k, v in raw.items()}

    logger.debug(
        "fetch_analogies: got analogies for %d/%d event_ids",
        len(analogies),
        len(event_ids),
    )

    return state.model_copy(update={"analogies": analogies})


# ══════════════════════════════════════════════════════════════════════════════
# AgentNodes — TASK-004
# ══════════════════════════════════════════════════════════════════════════════


async def _invoke_llm_stub(
    role_id: str,
    state: MorningBriefState,
    definition: Any,
) -> dict:
    """Stub LLM invocation — patched in tests and replaced in production.

    Returns a dict with: output, confidence, cost_usd, input_tokens, output_tokens.
    """
    return {
        "output": {"result": f"{role_id} stub output"},
        "confidence": 0.80,
        "cost_usd": 0.0,
        "input_tokens": 0,
        "output_tokens": 0,
    }


def _check_cost_ceiling(
    state: MorningBriefState,
    ceiling_usd: float = _COST_CEILING_USD,
) -> str | None:
    """Check cost ceiling phases.

    Returns:
        None     — below 80%, continue normally.
        "reduce" — at or above 80%, caller should reduce context.

    Raises:
        WorkflowCostCeilingExceeded — at or above 100% of ceiling.
    """
    from src.ai.workflows.morning_brief_nodes import WorkflowCostCeilingExceeded

    ratio = state.cost_usd / ceiling_usd if ceiling_usd > 0 else 1.0

    if ratio >= 1.0:
        raise WorkflowCostCeilingExceeded(
            accumulated=state.cost_usd,
            ceiling=ceiling_usd,
            workflow_id=state.workflow_id,
        )
    if ratio >= _REDUCE_CONTEXT_THRESHOLD:
        return "reduce"
    return None


class WorkflowCostCeilingExceeded(Exception):
    """Raised when the Morning Brief workflow exceeds its $2.00 cost ceiling.

    PLAN-F-006 TASK-004, TASK-014.
    """

    def __init__(self, accumulated: float, ceiling: float, workflow_id: Any) -> None:
        super().__init__(
            f"Morning Brief workflow {workflow_id} exceeded cost ceiling: "
            f"${accumulated:.4f} >= ${ceiling:.4f}"
        )
        self.accumulated = accumulated
        self.ceiling = ceiling
        self.workflow_id = workflow_id

    def to_dict(self) -> dict:
        return {
            "error": "WorkflowCostCeilingExceeded",
            "workflow_id": str(self.workflow_id),
            "accumulated_usd": self.accumulated,
            "ceiling_usd": self.ceiling,
        }


def _accumulate_cost(
    state: MorningBriefState,
    cost_usd: float,
    role_id: str,
    confidence: float,
) -> MorningBriefState:
    """Return updated state with cost and confidence accumulated."""
    new_scores = dict(state.confidence_scores)
    new_scores[role_id] = confidence
    return state.model_copy(
        update={
            "cost_usd": state.cost_usd + cost_usd,
            "confidence_scores": new_scores,
        }
    )


async def filter_relevant_events(
    state: MorningBriefState,
    *,
    registry: Any,
    cost_ceiling_usd: float = _COST_CEILING_USD,
    _invoke_llm: Any = None,
) -> MorningBriefState:
    """Filter events to those material to the portfolio (AgentNode).

    Uses the relevance_analyst agent to score and filter events.
    CostCeilingGuard applied after the call.

    Args:
        state: Current MorningBriefState (events must be populated).
        registry: IAgentRegistry.
        cost_ceiling_usd: Per-run cost ceiling.
        _invoke_llm: Optional override for LLM invocation (test injection).

    Returns:
        Updated state with relevant_events populated.
    """
    role_id = "relevance-analyst"
    definition = registry.resolve(role_id)

    invoke = _invoke_llm or _invoke_llm_stub
    result = await invoke(role_id, state, definition)

    output = result.get("output") or {}
    relevant = output.get("relevant_events", [])
    if not isinstance(relevant, list):
        relevant = []

    updated = _accumulate_cost(
        state,
        cost_usd=result.get("cost_usd", 0.0),
        role_id=role_id,
        confidence=result.get("confidence", 0.0),
    )
    updated = updated.model_copy(update={"relevant_events": relevant})

    _check_cost_ceiling_and_signal(updated, cost_ceiling_usd)

    return updated


async def detect_anomalies(
    state: MorningBriefState,
    *,
    registry: Any,
    cost_ceiling_usd: float = _COST_CEILING_USD,
    _invoke_llm: Any = None,
) -> MorningBriefState:
    """Detect statistical anomalies in score changes and events (AgentNode).

    Uses the anomaly_detector agent. CostCeilingGuard applied after the call.

    Args:
        state: Current MorningBriefState.
        registry: IAgentRegistry.
        cost_ceiling_usd: Per-run cost ceiling.
        _invoke_llm: Optional override for LLM invocation (test injection).

    Returns:
        Updated state with anomalies list populated.
    """
    role_id = "anomaly-detector"
    definition = registry.resolve(role_id)

    invoke = _invoke_llm or _invoke_llm_stub
    result = await invoke(role_id, state, definition)

    output = result.get("output") or {}
    anomalies = output.get("anomalies", [])
    if not isinstance(anomalies, list):
        anomalies = []

    updated = _accumulate_cost(
        state,
        cost_usd=result.get("cost_usd", 0.0),
        role_id=role_id,
        confidence=result.get("confidence", 0.0),
    )
    updated = updated.model_copy(update={"anomalies": anomalies})

    _check_cost_ceiling_and_signal(updated, cost_ceiling_usd)

    return updated


async def run_analyst_agent(
    state: MorningBriefState,
    *,
    registry: Any,
    cost_ceiling_usd: float = _COST_CEILING_USD,
    _invoke_llm: Any = None,
) -> MorningBriefState:
    """Run the main morning brief analyst (AgentNode).

    Uses the morning_brief_analyst agent to generate recommendations and
    confidence scores from relevant_events, score_changes, and anomalies.
    CostCeilingGuard applied after the call.

    Args:
        state: Current MorningBriefState.
        registry: IAgentRegistry.
        cost_ceiling_usd: Per-run cost ceiling.
        _invoke_llm: Optional override for LLM invocation (test injection).

    Returns:
        Updated state with recommendations populated.
    """
    role_id = "morning-brief-analyst"
    definition = registry.resolve(role_id)

    invoke = _invoke_llm or _invoke_llm_stub
    result = await invoke(role_id, state, definition)

    output = result.get("output") or {}
    recommendations = output.get("recommendations", [])
    if not isinstance(recommendations, list):
        recommendations = []

    updated = _accumulate_cost(
        state,
        cost_usd=result.get("cost_usd", 0.0),
        role_id=role_id,
        confidence=result.get("confidence", 0.0),
    )
    updated = updated.model_copy(update={"recommendations": recommendations})

    _check_cost_ceiling_and_signal(updated, cost_ceiling_usd)

    return updated


async def narrative_writer(
    state: MorningBriefState,
    *,
    registry: Any,
    cost_ceiling_usd: float = _COST_CEILING_USD,
    _invoke_llm: Any = None,
) -> MorningBriefState:
    """Compose the final narrative HTML brief (AgentNode — last AgentNode).

    Uses the narrative_writer agent to produce a formatted HTML brief from
    recommendations, anomalies, and analogies.
    CostCeilingGuard applied after the call.

    Args:
        state: Current MorningBriefState.
        registry: IAgentRegistry.
        cost_ceiling_usd: Per-run cost ceiling.
        _invoke_llm: Optional override for LLM invocation (test injection).

    Returns:
        Updated state with report (HTML string) populated.
    """
    role_id = "narrative-writer"
    definition = registry.resolve(role_id)

    invoke = _invoke_llm or _invoke_llm_stub
    result = await invoke(role_id, state, definition)

    output = result.get("output") or {}
    report = output.get("report") or output.get("html") or str(output)

    updated = _accumulate_cost(
        state,
        cost_usd=result.get("cost_usd", 0.0),
        role_id=role_id,
        confidence=result.get("confidence", 0.0),
    )
    updated = updated.model_copy(update={"report": report})

    _check_cost_ceiling_and_signal(updated, cost_ceiling_usd)

    return updated


def _check_cost_ceiling_and_signal(
    state: MorningBriefState,
    ceiling_usd: float,
) -> None:
    """Internal: check cost ceiling after each AgentNode call.

    At 80% ($1.60): logs a WARNING (reduce-context signal, does not raise).
    At 100% ($2.00): raises WorkflowCostCeilingExceeded.
    """
    ratio = state.cost_usd / ceiling_usd if ceiling_usd > 0 else 1.0

    if ratio >= 1.0:
        raise WorkflowCostCeilingExceeded(
            accumulated=state.cost_usd,
            ceiling=ceiling_usd,
            workflow_id=state.workflow_id,
        )

    if ratio >= _REDUCE_CONTEXT_THRESHOLD:
        logger.warning(
            "MorningBrief cost at %.0f%% of ceiling ($%.4f / $%.4f) "
            "for workflow_id=%s — context reduction recommended",
            ratio * 100,
            state.cost_usd,
            ceiling_usd,
            state.workflow_id,
        )


# ══════════════════════════════════════════════════════════════════════════════
# Routing / Terminal Nodes — TASK-005
# ══════════════════════════════════════════════════════════════════════════════


async def hil_queue(
    state: MorningBriefState,
    *,
    hil_repo: Any,
    brief_repo: Any | None = None,
    now: datetime | None = None,
) -> MorningBriefState:
    """Enqueue the brief for human-in-the-loop review (deadline 05:45 UTC).

    Inserts a hil_queue_item row via hil_repo. Sets requires_hil=True and
    confidence_route=HIL on the state.

    If brief_repo is provided, a brief row is inserted with hil_status='pending'
    so the HIL reviewer can access the content.

    Args:
        state: Current MorningBriefState.
        hil_repo: Repository with create(HILQueueItemCreate) method.
        brief_repo: Optional MorningBriefRepository for inserting the brief row.
        now: Current UTC datetime (injected for testability).

    Returns:
        Updated state with requires_hil=True and confidence_route=HIL.
    """
    from src.storage.repositories.hil_queue_repository import (
        HILQueueItemCreate,
        HILStatus,
    )

    _now = now or datetime.now(tz=timezone.utc)
    scheduled_send_at = _compute_hil_deadline(_now)

    # Determine confidence for HIL queue item
    confidence = (
        min(state.confidence_scores.values()) if state.confidence_scores else 0.0
    )

    dto = HILQueueItemCreate(
        workflow_run_id=state.workflow_id,
        workflow_type="morning_brief",
        user_id=state.user_id,
        tenant_id=state.tenant_id,
        confidence=confidence,
        scheduled_send_at=scheduled_send_at,
        lc_checkpoint_id=f"hil:{state.workflow_id}",
    )

    queue_item = await hil_repo.create(dto)

    logger.info(
        "hil_queue: enqueued morning brief for workflow_id=%s "
        "deadline=%s item_id=%s",
        state.workflow_id,
        scheduled_send_at.isoformat(),
        queue_item.item_id,
    )

    updated = state.model_copy(
        update={
            "requires_hil": True,
            "hil_reason": "Confidence below auto-send threshold (0.70)",
            "confidence_route": ConfidenceRoute.HIL,
        }
    )

    return updated


async def block_and_log(
    state: MorningBriefState,
) -> MorningBriefState:
    """Block the brief and log a WARNING (confidence < 0.40).

    No email is dispatched. No HIL queue item is created.
    Sets confidence_route=BLOCK on the state.

    Args:
        state: Current MorningBriefState.

    Returns:
        Updated state with confidence_route=BLOCK.
    """
    confidence = (
        min(state.confidence_scores.values()) if state.confidence_scores else 0.0
    )

    logger.warning(
        "block_and_log: Morning Brief blocked for workflow_id=%s tenant_id=%s "
        "overall_confidence=%.3f (threshold=0.40) — no email dispatched",
        state.workflow_id,
        state.tenant_id,
        confidence,
    )

    return state.model_copy(
        update={
            "confidence_route": ConfidenceRoute.BLOCK,
            "hil_reason": "Confidence too low for delivery (< 0.40)",
        }
    )


async def dispatch_brief(
    state: MorningBriefState,
    *,
    brief_repo: Any,
    email_dispatcher: Any,
    user_email: str,
) -> MorningBriefState:
    """Insert Brief row and dispatch via SendGrid email.

    Steps:
      1. Insert a Brief row in the DB with hil_status='none', sent_at=None.
      2. Send email via email_dispatcher.send_morning_brief().
      3. If email sent: update sent_at on the Brief row.
      4. Set brief_id and confidence_route=AUTO_SEND on the state.

    Args:
        state: Current MorningBriefState (report must be populated).
        brief_repo: MorningBriefRepository.
        email_dispatcher: EmailDispatcher with send_morning_brief().
        user_email: Recipient email address.

    Returns:
        Updated state with brief_id set and confidence_route=AUTO_SEND.
    """
    from src.storage.repositories.morning_brief_repository import MorningBriefCreate

    confidence = (
        min(state.confidence_scores.values()) if state.confidence_scores else 0.0
    )

    # 1. Insert Brief row
    create_dto = MorningBriefCreate(
        user_id=state.user_id,
        tenant_id=state.tenant_id,
        workflow_id=state.workflow_id,
        content=state.report or "",
        confidence=confidence,
        cost_usd=state.cost_usd,
    )
    brief = await brief_repo.insert(create_dto)

    logger.info(
        "dispatch_brief: inserted brief_id=%s for workflow_id=%s",
        brief.brief_id,
        state.workflow_id,
    )

    # 2. Send email
    sent = await email_dispatcher.send_morning_brief(
        to=user_email,
        subject="StokAI Morning Brief",
        html_body=state.report or "",
        brief_id=brief.brief_id,
    )

    # 3. Update sent_at on success
    if sent:
        sent_at = datetime.now(tz=timezone.utc)
        await brief_repo.update_sent_at(brief.brief_id, state.tenant_id, sent_at)
        logger.info(
            "dispatch_brief: email sent to %s brief_id=%s",
            user_email,
            brief.brief_id,
        )
    else:
        logger.warning(
            "dispatch_brief: email send failed to %s brief_id=%s",
            user_email,
            brief.brief_id,
        )

    return state.model_copy(
        update={
            "brief_id": brief.brief_id,
            "confidence_route": ConfidenceRoute.AUTO_SEND,
        }
    )


def _compute_hil_deadline(now: datetime) -> datetime:
    """Return the next 05:45 UTC deadline for morning brief HIL review.

    If 05:45 today is in the future, return today's occurrence.
    Otherwise return tomorrow's.
    """
    candidate = now.replace(
        hour=_HIL_HOUR, minute=_HIL_MINUTE, second=0, microsecond=0
    )
    if candidate <= now:
        candidate = candidate + timedelta(days=1)
    return candidate
