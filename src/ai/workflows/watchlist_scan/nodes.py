"""
ai.workflows.watchlist_scan.nodes — All nodes for the Watchlist Scan workflow.

Provides DeterministicNodes and AgentNodes used by build_watchlist_scan_graph.

DeterministicNodes:
  fetch_watchlist          — merges watchlist + portfolio company IDs (dedup)
  fetch_today_events       — fetches today's geo-events for scoped companies
  recompute_scores         — recomputes exposure scores for affected companies
  evaluate_quality_node    — computes overall_confidence = min(confidence_scores)
  dispatch_node            — inserts Brief, sends email (confidence >= 0.70)
  hil_enqueue_node         — enqueues in HIL queue with 17:45 UTC deadline
  block_and_notify_node    — logs, does not dispatch

AgentNodes:
  relevance_analyst_node     — filters today_events to relevant ones (LLM)
  anomaly_detector_node      — detects anomalies, populates high_anomaly_company_ids
  historical_context_node    — historical analogies per high-anomaly company (conditional)
  recommendation_synthesizer_node — synthesizes action recommendations
  narrative_writer_node      — produces final HTML report (last AgentNode)

PLAN-F-008 TASK-003, TASK-004, TASK-005, TASK-006, TASK-007,
           TASK-008, TASK-009, TASK-010, TASK-013, TASK-014
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

if TYPE_CHECKING:
    from src.ai.workflows.watchlist_scan.cost_guard import WorkflowCostGuard

from src.ai.workflows.watchlist_scan.state import WatchlistScanState

logger = logging.getLogger(__name__)

# HIL deadline for watchlist scan: 17:45 UTC
_HIL_DEADLINE_HOUR = 17
_HIL_DEADLINE_MINUTE = 45

# Anomaly magnitude threshold for high-anomaly classification
_HIGH_ANOMALY_THRESHOLD = 0.6

# Confidence thresholds (D9)
_AUTO_DISPATCH_THRESHOLD = 0.70
_HIL_THRESHOLD = 0.40


# ── DeterministicNode: fetch_watchlist ─────────────────────────────────────────


async def fetch_watchlist(
    state: WatchlistScanState,
    *,
    tool_library: Any,
) -> WatchlistScanState:
    """Fetch watchlist and portfolio company IDs; merge and deduplicate.

    Sets state.watchlist_companies, state.portfolio_companies, and
    state.scoped_company_ids (deduplicated union, watchlist-first ordering).

    Args:
        state: Current WatchlistScanState.
        tool_library: ToolLibrary with get_watchlist() and get_portfolio_state().

    Returns:
        Updated state with scoped_company_ids populated.
    """
    watchlist_ids: list[UUID] = await tool_library.get_watchlist(
        user_id=state.user_id,
        tenant_id=state.tenant_id,
    )
    portfolio_ids: list[UUID] = await tool_library.get_portfolio_state(
        user_id=state.user_id,
        tenant_id=state.tenant_id,
    )

    # Deduplicate preserving order: watchlist first, then portfolio additions
    seen: set[UUID] = set()
    scoped: list[UUID] = []
    for cid in list(watchlist_ids) + list(portfolio_ids):
        if cid not in seen:
            seen.add(cid)
            scoped.append(cid)

    logger.debug(
        "fetch_watchlist: watchlist=%d portfolio=%d scoped=%d",
        len(watchlist_ids),
        len(portfolio_ids),
        len(scoped),
    )

    state.watchlist_companies = list(watchlist_ids)
    state.portfolio_companies = list(portfolio_ids)
    state.scoped_company_ids = scoped
    return state


# ── DeterministicNode: fetch_today_events ─────────────────────────────────────


async def fetch_today_events(
    state: WatchlistScanState,
    *,
    tool_library: Any,
) -> WatchlistScanState:
    """Fetch today's geo-events using query_recent_events.

    Args:
        state: Current WatchlistScanState.
        tool_library: ToolLibrary with query_recent_events().

    Returns:
        Updated state with today_events populated.

    Raises:
        RuntimeError: If query_recent_events raises InsufficientData (re-raised
            with additional context).
    """
    now = datetime.now(tz=timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    try:
        events = await tool_library.query_recent_events(
            since=today_start,
            until=now,
        )
    except Exception as exc:
        raise RuntimeError(
            f"fetch_today_events: failed to retrieve today's events "
            f"for workflow {state.workflow_id}: {exc}"
        ) from exc

    logger.debug(
        "fetch_today_events: fetched %d events for workflow=%s",
        len(events),
        state.workflow_id,
    )

    state.today_events = list(events)
    return state


# ── DeterministicNode: recompute_scores ───────────────────────────────────────


async def recompute_scores(
    state: WatchlistScanState,
    *,
    tool_library: Any,
) -> WatchlistScanState:
    """Recompute exposure scores for scoped companies that appear in relevant_events.

    Only processes companies present in both scoped_company_ids AND relevant_events.
    Uses asyncio.gather for concurrent score history fetches.

    Args:
        state: Current WatchlistScanState (must have relevant_events and
            scoped_company_ids populated).
        tool_library: ToolLibrary with get_company_score_history().

    Returns:
        Updated state with score_changes populated.
    """
    if not state.relevant_events:
        logger.debug("recompute_scores: no relevant_events; skipping")
        return state

    # Determine which scoped companies appear in relevant_events
    affected_in_events: set[UUID] = set()
    for ev in state.relevant_events:
        company_ids_in_event = ev.get("company_ids", []) if hasattr(ev, "get") else []
        company_id = ev.get("company_id") if hasattr(ev, "get") else None
        if company_id:
            try:
                affected_in_events.add(UUID(str(company_id)))
            except (ValueError, AttributeError):
                pass
        for cid in company_ids_in_event:
            try:
                affected_in_events.add(UUID(str(cid)))
            except (ValueError, AttributeError):
                pass

    # Intersect with scoped_company_ids
    scoped_set = set(state.scoped_company_ids)
    companies_to_score = list(affected_in_events & scoped_set)

    if not companies_to_score:
        logger.debug(
            "recompute_scores: no scoped companies found in relevant_events"
        )
        return state

    async def _compute_one(company_id: UUID) -> dict:
        history = await tool_library.get_company_score_history(
            company_id=company_id,
            tenant_id=state.tenant_id,
        )
        prior_score = history.get("prior_score", 0.0) if history else 0.0
        new_score = history.get("current_score", 0.0) if history else 0.0
        delta = new_score - prior_score
        return {
            "company_id": company_id,
            "prior_score": prior_score,
            "new_score": new_score,
            "delta": delta,
        }

    score_changes = await asyncio.gather(
        *[_compute_one(cid) for cid in companies_to_score]
    )

    logger.debug(
        "recompute_scores: computed %d score changes for workflow=%s",
        len(score_changes),
        state.workflow_id,
    )

    state.score_changes = list(score_changes)
    return state


# ── AgentNode: relevance_analyst_node ─────────────────────────────────────────


async def relevance_analyst_node(
    state: WatchlistScanState,
    *,
    registry: Any,
    tool_library: Any,
    cost_guard: WorkflowCostGuard,
) -> WatchlistScanState:
    """Filter today_events to those relevant to scoped_company_ids.

    Resolves the relevance_analyst agent from AgentRegistry and invokes it.
    Filters agent output to only include events touching scoped companies.
    Updates cost_usd and confidence_scores["relevance_analyst"].
    Calls cost_guard.check_and_accumulate().

    Args:
        state: Current WatchlistScanState.
        registry: AgentRegistry providing the relevance_analyst agent.
        tool_library: ToolLibrary (passed to agent invocation context).
        cost_guard: WorkflowCostGuard for per-run cost enforcement.

    Returns:
        Updated state with relevant_events, cost_usd, confidence_scores updated.

    Raises:
        WorkflowBudgetExceededError: If accumulated cost exceeds ceiling.
    """
    definition = registry.resolve("relevance_analyst")

    # Invoke the agent (stub pattern — real implementation calls LLM)
    result = await _invoke_agent(definition, {
        "today_events": state.today_events,
        "scoped_company_ids": [str(cid) for cid in state.scoped_company_ids],
    })

    raw_relevant: list = result.get("relevant_events", state.today_events)
    agent_cost: float = result.get("cost_usd", 0.0)
    confidence: float = result.get("confidence", 0.0)

    # Filter: only keep events that touch scoped companies
    scoped_set = {str(cid) for cid in state.scoped_company_ids}
    filtered = []
    for ev in raw_relevant:
        if not hasattr(ev, "get"):
            continue
        company_id = ev.get("company_id")
        company_ids = ev.get("company_ids", [])
        ev_companies = set()
        if company_id:
            ev_companies.add(str(company_id))
        for cid in company_ids:
            ev_companies.add(str(cid))
        if not ev_companies or ev_companies & scoped_set:
            filtered.append(ev)

    # If no filtering metadata provided (empty company_ids), keep as-is
    if not filtered and raw_relevant:
        filtered = list(raw_relevant)

    # Sentinel: no relevant events AND there were events to filter → low confidence
    # If today_events was already empty, this is expected (no penalty).
    if not filtered and state.today_events:
        confidence = min(confidence, 0.1)

    new_confidence_scores = dict(state.confidence_scores)
    new_confidence_scores["relevance_analyst"] = confidence
    state.relevant_events = filtered
    state.confidence_scores = new_confidence_scores

    cost_guard.check_and_accumulate(state, agent_cost)

    logger.debug(
        "relevance_analyst_node: %d relevant events; cost=%.4f confidence=%.4f",
        len(filtered),
        agent_cost,
        confidence,
    )

    return state


# ── AgentNode: anomaly_detector_node ──────────────────────────────────────────


async def anomaly_detector_node(
    state: WatchlistScanState,
    *,
    registry: Any,
    tool_library: Any,
    cost_guard: WorkflowCostGuard,
) -> WatchlistScanState:
    """Detect anomalies in score_changes and relevant_events.

    Populates state.anomalies and state.high_anomaly_company_ids.
    IDs with anomaly.magnitude >= 0.6 are classified as high-anomaly.

    Args:
        state: Current WatchlistScanState.
        registry: AgentRegistry providing the anomaly_detector agent.
        tool_library: ToolLibrary (passed to agent invocation context).
        cost_guard: WorkflowCostGuard for per-run cost enforcement.

    Returns:
        Updated state with anomalies, high_anomaly_company_ids, cost_usd,
        confidence_scores updated.

    Raises:
        WorkflowBudgetExceededError: If accumulated cost exceeds ceiling.
    """
    definition = registry.resolve("anomaly_detector")

    result = await _invoke_agent(definition, {
        "score_changes": state.score_changes,
        "relevant_events": state.relevant_events,
    })

    anomalies: list = result.get("anomalies", [])
    agent_cost: float = result.get("cost_usd", 0.0)
    confidence: float = result.get("confidence", 0.0)

    # Classify high-anomaly: magnitude >= 0.6
    high_anomaly_ids: list[UUID] = []
    for anomaly in anomalies:
        magnitude = anomaly.get("magnitude", 0.0) if hasattr(anomaly, "get") else 0.0
        company_id = anomaly.get("company_id") if hasattr(anomaly, "get") else None
        if magnitude >= _HIGH_ANOMALY_THRESHOLD and company_id is not None:
            try:
                high_anomaly_ids.append(UUID(str(company_id)))
            except (ValueError, AttributeError):
                pass

    new_confidence_scores = dict(state.confidence_scores)
    new_confidence_scores["anomaly_detector"] = confidence
    state.anomalies = anomalies
    state.high_anomaly_company_ids = high_anomaly_ids
    state.confidence_scores = new_confidence_scores

    cost_guard.check_and_accumulate(state, agent_cost)

    logger.debug(
        "anomaly_detector_node: %d anomalies; %d high-anomaly; cost=%.4f",
        len(anomalies),
        len(high_anomaly_ids),
        agent_cost,
    )

    return state


# ── AgentNode: historical_context_node ────────────────────────────────────────


async def historical_context_node(
    state: WatchlistScanState,
    *,
    registry: Any,
    tool_library: Any,
    cost_guard: WorkflowCostGuard,
) -> WatchlistScanState:
    """Retrieve historical analogies for high-anomaly companies only.

    Guard: if high_anomaly_company_ids is empty, returns state unchanged (no-op).
    Otherwise invokes historical_context_agent once per high-anomaly company
    using asyncio.gather for concurrent execution.

    Args:
        state: Current WatchlistScanState.
        registry: AgentRegistry providing the historical_context_agent.
        tool_library: ToolLibrary (passed to agent invocation context).
        cost_guard: WorkflowCostGuard for per-run cost enforcement.

    Returns:
        Updated state with analogies dict, cost_usd, confidence_scores updated.
        If no high-anomaly companies, returns state unchanged.

    Raises:
        WorkflowBudgetExceededError: If accumulated cost exceeds ceiling.
    """
    if not state.high_anomaly_company_ids:
        logger.debug(
            "historical_context_node: no high-anomaly companies; skipping"
        )
        return state

    definition = registry.resolve("historical_context_agent")

    async def _invoke_for_company(company_id: UUID) -> tuple[UUID, dict]:
        result = await _invoke_agent(definition, {
            "company_id": str(company_id),
            "tenant_id": str(state.tenant_id),
            "anomalies": [
                a for a in state.anomalies
                if hasattr(a, "get") and str(a.get("company_id")) == str(company_id)
            ],
        })
        return company_id, result

    results = await asyncio.gather(
        *[_invoke_for_company(cid) for cid in state.high_anomaly_company_ids]
    )

    analogies: dict[str, Any] = dict(state.analogies)
    total_cost = 0.0
    total_confidence = 0.0

    for company_id, result in results:
        analogies[str(company_id)] = result.get("analogies", [])
        total_cost += result.get("cost_usd", 0.0)
        total_confidence += result.get("confidence", 0.0)

    avg_confidence = (
        total_confidence / len(results) if results else 0.0
    )

    new_confidence_scores = dict(state.confidence_scores)
    new_confidence_scores["historical_context_agent"] = avg_confidence
    state.analogies = analogies
    state.confidence_scores = new_confidence_scores

    cost_guard.check_and_accumulate(state, total_cost)

    logger.debug(
        "historical_context_node: analogies for %d companies; total_cost=%.4f",
        len(results),
        total_cost,
    )

    return state


# ── AgentNode: recommendation_synthesizer_node ────────────────────────────────


async def recommendation_synthesizer_node(
    state: WatchlistScanState,
    *,
    registry: Any,
    tool_library: Any,
    cost_guard: WorkflowCostGuard,
) -> WatchlistScanState:
    """Synthesize action recommendations from relevant_events, anomalies, analogies.

    Produces a list of Recommendation objects with action_signal, company_id,
    confidence, and rationale. Valid action_signal values:
    {HOLD, WATCH, BUY_OPP, REDUCE_RISK, HEDGE, CONTRARIAN}.

    Args:
        state: Current WatchlistScanState.
        registry: AgentRegistry providing the recommendation_synthesizer agent.
        tool_library: ToolLibrary (passed to agent invocation context).
        cost_guard: WorkflowCostGuard for per-run cost enforcement.

    Returns:
        Updated state with recommendations, cost_usd, confidence_scores updated.

    Raises:
        WorkflowBudgetExceededError: If accumulated cost exceeds ceiling.
    """
    definition = registry.resolve("recommendation_synthesizer")

    result = await _invoke_agent(definition, {
        "relevant_events": state.relevant_events,
        "anomalies": state.anomalies,
        "analogies": state.analogies,
    })

    recommendations: list = result.get("recommendations", [])
    agent_cost: float = result.get("cost_usd", 0.0)
    confidence: float = result.get("confidence", 0.0)

    new_confidence_scores = dict(state.confidence_scores)
    new_confidence_scores["recommendation_synthesizer"] = confidence
    state.recommendations = recommendations
    state.confidence_scores = new_confidence_scores

    cost_guard.check_and_accumulate(state, agent_cost)

    logger.debug(
        "recommendation_synthesizer_node: %d recommendations; cost=%.4f",
        len(recommendations),
        agent_cost,
    )

    return state


# ── AgentNode: narrative_writer_node (last AgentNode) ─────────────────────────


async def narrative_writer_node(
    state: WatchlistScanState,
    *,
    registry: Any,
    tool_library: Any,
    cost_guard: WorkflowCostGuard,
) -> WatchlistScanState:
    """Convert structured outputs to a human-readable HTML report.

    This is the LAST AgentNode in the graph. It must be positioned immediately
    before evaluate_quality_node in the graph definition.

    Produces an HTML report in FT-columnist voice from state.recommendations
    and state.analogies.

    Args:
        state: Current WatchlistScanState.
        registry: AgentRegistry providing the narrative_writer agent.
        tool_library: ToolLibrary (passed to agent invocation context).
        cost_guard: WorkflowCostGuard for per-run cost enforcement.

    Returns:
        Updated state with report (HTML string), cost_usd,
        confidence_scores updated.

    Raises:
        WorkflowBudgetExceededError: If accumulated cost exceeds ceiling.
    """
    definition = registry.resolve("narrative_writer")

    result = await _invoke_agent(definition, {
        "recommendations": state.recommendations,
        "analogies": state.analogies,
        "overall_confidence": state.overall_confidence,
    })

    report = result.get("report") or result.get("output")
    agent_cost: float = result.get("cost_usd", 0.0)
    confidence: float = result.get("confidence", 0.0)

    # Ensure we have an HTML report
    if report is None:
        report = {
            "content": "<html><body><p>Watchlist scan report</p></body></html>",
            "recommendations": state.recommendations,
        }

    new_confidence_scores = dict(state.confidence_scores)
    new_confidence_scores["narrative_writer"] = confidence
    state.report = report
    state.confidence_scores = new_confidence_scores

    cost_guard.check_and_accumulate(state, agent_cost)

    logger.debug(
        "narrative_writer_node: report generated; cost=%.4f confidence=%.4f",
        agent_cost,
        confidence,
    )

    return state


# ── DeterministicNode: evaluate_quality_node (second-to-last) ─────────────────


async def evaluate_quality_node(
    state: WatchlistScanState,
    *,
    memory_service: Any | None = None,
) -> WatchlistScanState:
    """Compute overall_confidence = min(confidence_scores.values()).

    Sets requires_hil=True and hil_reason when 0.40 <= overall_confidence < 0.70.
    Sets requires_hil=False when overall_confidence >= 0.70.
    Does NOT set requires_hil when < 0.40 (the router handles block branch).

    Must be positioned second-to-last in the graph (immediately before the
    conditional branch, which leads to dispatch, hil_enqueue, or block_and_notify).

    Writes a workflow_run episodic memory entry with final confidence and cost.

    Args:
        state: Current WatchlistScanState (must have confidence_scores populated).
        memory_service: Optional memory service for episodic logging.

    Returns:
        Updated state with overall_confidence, requires_hil, and hil_reason set.
    """
    if state.confidence_scores:
        overall_confidence = min(state.confidence_scores.values())
    else:
        overall_confidence = 0.0

    requires_hil = False
    hil_reason: str | None = None

    if _AUTO_DISPATCH_THRESHOLD <= overall_confidence:
        requires_hil = False
    elif _HIL_THRESHOLD <= overall_confidence < _AUTO_DISPATCH_THRESHOLD:
        requires_hil = True
        hil_reason = (
            f"confidence={overall_confidence:.4f} in HIL range "
            f"[{_HIL_THRESHOLD:.2f}, {_AUTO_DISPATCH_THRESHOLD:.2f})"
        )
    # else: < 0.40 — router decides block; no requires_hil override here

    state.overall_confidence = overall_confidence
    state.requires_hil = requires_hil
    state.hil_reason = hil_reason

    # Write episodic log entry
    if memory_service is not None:
        try:
            await memory_service.record_workflow_run(
                workflow_id=state.workflow_id,
                confidence=overall_confidence,
                cost_usd=state.cost_usd,
            )
        except Exception:
            logger.warning(
                "evaluate_quality_node: failed to write episodic memory entry"
            )

    logger.info(
        "evaluate_quality_node: overall_confidence=%.4f requires_hil=%s",
        overall_confidence,
        requires_hil,
    )

    return state


# ── DeterministicNode: dispatch_node ─────────────────────────────────────────


async def dispatch_node(
    state: WatchlistScanState,
    *,
    brief_repo: Any,
    alert_service: Any,
    memory_service: Any | None = None,
) -> WatchlistScanState:
    """Persist report and send email.

    Only reached on the auto-send branch (confidence >= 0.70) or after HIL
    approval. Inserts a brief row with type="watchlist_scan" and
    hil_status="approved" (auto-approved). Renders HTML and sends email.
    Sets sent_at on success. Writes episodic workflow_run row with
    status="completed".

    Args:
        state: Current WatchlistScanState.
        brief_repo: Repository with insert_brief(brief) method.
        alert_service: Alert service with send_email(user_id, subject, html_body).
        memory_service: Optional memory service for episodic logging.

    Returns:
        Updated state with brief_id set.

    Raises:
        Exception: If alert_service.send_email raises; sent_at is NOT set.
    """
    brief_id = uuid4()
    report_content = state.report or {}

    # Render HTML report body
    if hasattr(report_content, "get"):
        html_body = report_content.get("content") or str(report_content)
    else:
        html_body = str(report_content)

    # Insert brief row (hil_status="approved" — auto-approved)
    brief_data = {
        "brief_id": brief_id,
        "type": "watchlist_scan",
        "hil_status": "approved",
        "tenant_id": state.tenant_id,
        "user_id": state.user_id,
        "workflow_id": state.workflow_id,
        "content": report_content,
        "confidence": state.overall_confidence,
        "cost_usd": state.cost_usd,
        "sent_at": None,
    }

    # Persist brief
    brief_row = await brief_repo.insert_brief(brief_data)
    persisted_id = getattr(brief_row, "brief_id", brief_id)

    # Send email — may raise; sent_at stays None on failure
    subject = "Afternoon Watchlist Scan Report"
    await alert_service.send_email(
        user_id=state.user_id,
        subject=subject,
        html_body=html_body,
    )

    # Update sent_at after successful send
    sent_at = datetime.now(tz=timezone.utc)
    try:
        await brief_repo.update_sent_at(brief_id=persisted_id, sent_at=sent_at)
    except Exception:
        logger.warning(
            "dispatch_node: failed to update sent_at for brief_id=%s", persisted_id
        )

    # Write episodic log
    if memory_service is not None:
        try:
            await memory_service.record_workflow_completed(
                workflow_id=state.workflow_id,
                status="completed",
                confidence=state.overall_confidence,
            )
        except Exception:
            logger.warning("dispatch_node: failed to write episodic log")

    logger.info(
        "dispatch_node: dispatched brief_id=%s for workflow=%s",
        persisted_id,
        state.workflow_id,
    )

    state.brief_id = persisted_id
    return state


# ── DeterministicNode: hil_enqueue_node ──────────────────────────────────────


async def hil_enqueue_node(
    state: WatchlistScanState,
    *,
    hil_service: Any,
    celery_app: Any | None = None,
) -> WatchlistScanState:
    """Enqueue report in HIL queue with 17:45 UTC deadline.

    Persists report to brief table with hil_status="pending".
    Enqueues HIL review item via hil_service.enqueue().
    Schedules check_hil_deadline Celery task at 17:45 (idempotent).

    Args:
        state: Current WatchlistScanState.
        hil_service: HIL service with enqueue(report_id, deadline, workflow_type).
        celery_app: Optional Celery app for scheduling deadline check task.

    Returns:
        Updated state with requires_hil=True.
    """
    now = datetime.now(tz=timezone.utc)

    # Compute the 17:45 UTC deadline
    candidate = now.replace(
        hour=_HIL_DEADLINE_HOUR,
        minute=_HIL_DEADLINE_MINUTE,
        second=0,
        microsecond=0,
    )
    if candidate <= now:
        candidate = candidate + timedelta(days=1)
    deadline = candidate

    report_id = state.brief_id or uuid4()

    # Enqueue HIL review item (idempotent — service handles deduplication)
    await hil_service.enqueue(
        report_id=report_id,
        deadline=deadline,
        workflow_type="watchlist_scan",
        workflow_id=state.workflow_id,
        user_id=state.user_id,
        tenant_id=state.tenant_id,
        confidence=state.overall_confidence,
    )

    # Schedule deadline enforcement task
    if celery_app is not None:
        try:
            celery_app.send_task(
                "ai.check_hil_deadline",
                kwargs={
                    "report_id": str(report_id),
                    "workflow_type": "watchlist_scan",
                },
                eta=deadline,
            )
        except Exception:
            logger.warning(
                "hil_enqueue_node: failed to schedule check_hil_deadline task"
            )

    logger.info(
        "hil_enqueue_node: queued workflow=%s with deadline=%s",
        state.workflow_id,
        deadline.isoformat(),
    )

    state.requires_hil = True
    state.hil_reason = (
        state.hil_reason or
        f"confidence={state.overall_confidence:.4f} in HIL range"
    )
    return state


# ── DeterministicNode: block_and_notify_node ─────────────────────────────────


async def block_and_notify_node(
    state: WatchlistScanState,
    *,
    memory_service: Any | None = None,
    notification_service: Any | None = None,
) -> WatchlistScanState:
    """Block report and notify user that no report was delivered.

    Writes episodic log entry with status="blocked" and confidence recorded.
    Sends system notification to user (no report content sent).
    Does NOT send report content.

    Args:
        state: Current WatchlistScanState.
        memory_service: Optional memory service for episodic logging.
        notification_service: Optional notification service for user notification.

    Returns:
        State with hil_reason updated to reflect blocked status.
    """
    logger.warning(
        "block_and_notify_node: watchlist scan blocked workflow=%s "
        "overall_confidence=%.4f (below %.2f threshold)",
        state.workflow_id,
        state.overall_confidence,
        _HIL_THRESHOLD,
    )

    # Write episodic log entry with blocked status
    if memory_service is not None:
        try:
            await memory_service.record_workflow_completed(
                workflow_id=state.workflow_id,
                status="blocked",
                confidence=state.overall_confidence,
            )
        except Exception:
            logger.warning("block_and_notify_node: failed to write episodic log")

    # Notify user that no report was delivered (no report content)
    if notification_service is not None:
        try:
            await notification_service.notify_user(
                user_id=state.user_id,
                message="Your watchlist scan report could not be delivered due to low confidence.",
                notification_type="scan_blocked",
            )
        except Exception:
            logger.warning(
                "block_and_notify_node: failed to send user notification"
            )

    state.hil_reason = (
        f"blocked: confidence={state.overall_confidence:.4f} < {_HIL_THRESHOLD:.2f}"
    )
    return state


# ── Internal helper: _invoke_agent ────────────────────────────────────────────


async def _invoke_agent(definition: Any, payload: dict) -> dict:
    """Invoke an agent definition with a payload.

    This is a thin async wrapper that calls definition.invoke(payload) if
    available, or definition.ainvoke(payload) for async agents.

    In production this is replaced by the actual LLM invocation through
    the AgentDefinition + LLM client chain. In tests it is patched directly.

    Returns:
        dict with keys: relevant_events, anomalies, recommendations, report,
        cost_usd, confidence, analogies, output — depending on agent type.
    """
    try:
        # Try async first
        if hasattr(definition, "ainvoke"):
            result = await definition.ainvoke(payload)
        elif hasattr(definition, "invoke"):
            result = definition.invoke(payload)
        else:
            # Stub fallback for testing
            result = {}
    except Exception as exc:
        logger.error("_invoke_agent: invocation failed: %s", exc)
        raise

    if isinstance(result, dict):
        return result
    # Handle object responses (MagicMock etc.)
    return {
        "relevant_events": getattr(result, "relevant_events", []),
        "anomalies": getattr(result, "anomalies", []),
        "recommendations": getattr(result, "recommendations", []),
        "report": getattr(result, "report", None),
        "output": getattr(result, "output", None),
        "analogies": getattr(result, "analogies", []),
        "cost_usd": getattr(result, "cost_usd", 0.0),
        "confidence": getattr(result, "confidence", 0.0),
    }
