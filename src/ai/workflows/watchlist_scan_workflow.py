"""
ai.workflows.watchlist_scan_workflow — WatchlistScanWorkflow LangGraph graph.

Constructs and compiles the watchlist scan StateGraph.

Node execution order:
  1. fetch_scoped_companies  (DeterministicNode)
  2. fetch_today_events      (DeterministicNode)
  3. fetch_score_changes     (DeterministicNode)
  4. filter_relevant_events  (AgentNode — LLM)
  5. detect_anomalies        (AgentNode — LLM)
  6. fetch_analogies         (DeterministicNode)
  7. run_watchlist_analyst   (AgentNode — LLM)
  8. evaluate_quality        (DeterministicNode — Tier1 judge)
  9. narrative_writer        (AgentNode — LLM) ← must be last
     ↓ conditional: route_after_quality
  10a. dispatch              → Brief insert + email
  10b. hil_enqueue           → HIL queue (deadline 17:45)
  10c. block_and_notify      → log only

HIL resume:
  - Approval  → dispatch
  - Rejection → block_and_notify

WorkflowStructureValidator is called before the graph is returned (AC-004).

PLAN-F-008 TASK-005, TASK-011
"""
from __future__ import annotations

import logging
from typing import Any

from src.ai.validators.workflow_structure_validator import WorkflowStructureValidator
from src.ai.workflows.watchlist_scan_state import WatchlistScanState, route_after_quality

logger = logging.getLogger(__name__)

# Canonical node sequence (the validator requires evaluate_quality → narrative_writer tail)
_NODE_SEQUENCE = [
    "fetch_scoped_companies",
    "fetch_today_events",
    "fetch_score_changes",
    "filter_relevant_events",
    "detect_anomalies",
    "fetch_analogies",
    "run_watchlist_analyst",
    "evaluate_quality",
    "narrative_writer",
]


class WatchlistScanWorkflow:
    """Compiled watchlist scan workflow graph with ainvoke() interface.

    Provides the same interface as a LangGraph CompiledGraph.
    WorkflowStructureValidator is called at build time (AC-004).

    Parameters
    ----------
    watchlist_repo:
        Repository with list_company_ids(user_id, tenant_id).
    portfolio_repo:
        Repository with list_company_ids(user_id, tenant_id).
    geo_event_repo:
        Repository with list_for_companies(...).
    score_repo:
        Repository with list_score_changes(...).
    analogy_repo:
        Repository with get_analogies_for_events(...).
    hil_repo:
        HILQueueRepository instance.
    brief_repo:
        IBriefRepository instance.
    email_service:
        Email service with send_watchlist_scan(state).
    filter_agent:
        Agent for filter_relevant_events.
    anomaly_agent:
        Agent for detect_anomalies.
    analyst_agent:
        Agent for run_watchlist_analyst.
    writer_agent:
        Agent for narrative_writer.
    tier1_judge:
        Tier1JudgeService instance.
    cost_ceiling_usd:
        Per-run cost ceiling (default $1.00).
    celery_app:
        Celery application for high-anomaly dispatch (optional).
    """

    def __init__(
        self,
        watchlist_repo: Any,
        portfolio_repo: Any,
        geo_event_repo: Any,
        score_repo: Any,
        analogy_repo: Any,
        hil_repo: Any,
        brief_repo: Any,
        email_service: Any,
        filter_agent: Any,
        anomaly_agent: Any,
        analyst_agent: Any,
        writer_agent: Any,
        tier1_judge: Any,
        cost_ceiling_usd: float = 1.00,
        celery_app: Any = None,
    ) -> None:
        from src.ai.workflows.cost_guard import CostCeilingGuard

        self._watchlist_repo = watchlist_repo
        self._portfolio_repo = portfolio_repo
        self._geo_event_repo = geo_event_repo
        self._score_repo = score_repo
        self._analogy_repo = analogy_repo
        self._hil_repo = hil_repo
        self._brief_repo = brief_repo
        self._email_service = email_service
        self._filter_agent = filter_agent
        self._anomaly_agent = anomaly_agent
        self._analyst_agent = analyst_agent
        self._writer_agent = writer_agent
        self._tier1_judge = tier1_judge
        self._cost_guard = CostCeilingGuard(cost_ceiling_usd)
        self._celery_app = celery_app

        # Validate structure invariant (AC-004)
        WorkflowStructureValidator().validate(_NODE_SEQUENCE)

    async def ainvoke(
        self,
        state: WatchlistScanState,
        config: Any = None,
    ) -> WatchlistScanState:
        """Execute all workflow nodes in order; route from narrative_writer.

        Args:
            state: Initial WatchlistScanState.
            config: Optional LangGraph config (ignored — for interface compat).

        Returns:
            Final WatchlistScanState after all nodes complete.
        """
        from src.ai.workflows.watchlist_scan_nodes import (
            block_and_notify,
            detect_anomalies,
            dispatch,
            dispatch_high_anomalies,
            evaluate_quality,
            fetch_analogies,
            fetch_score_changes,
            fetch_scoped_companies,
            fetch_today_events,
            filter_relevant_events,
            hil_enqueue,
            narrative_writer,
            run_watchlist_analyst,
        )

        try:
            # ── DeterministicNode: fetch companies ───────────────────────────
            state = await fetch_scoped_companies(
                state,
                watchlist_repo=self._watchlist_repo,
                portfolio_repo=self._portfolio_repo,
            )

            # ── DeterministicNode: fetch events ──────────────────────────────
            state = await fetch_today_events(state, geo_event_repo=self._geo_event_repo)

            # ── DeterministicNode: fetch score changes ───────────────────────
            state = await fetch_score_changes(state, score_repo=self._score_repo)

            # ── AgentNode: filter relevant events ────────────────────────────
            state = await filter_relevant_events(
                state, agent=self._filter_agent, cost_guard=self._cost_guard
            )

            # ── AgentNode: detect anomalies ───────────────────────────────────
            state = await detect_anomalies(
                state, agent=self._anomaly_agent, cost_guard=self._cost_guard
            )

            # ── DeterministicNode: fetch analogies ───────────────────────────
            state = await fetch_analogies(state, analogy_repo=self._analogy_repo)

            # ── AgentNode: watchlist analyst ──────────────────────────────────
            state = await run_watchlist_analyst(
                state, agent=self._analyst_agent, cost_guard=self._cost_guard
            )

            # ── DeterministicNode: evaluate quality ───────────────────────────
            state = await evaluate_quality(state, tier1_judge=self._tier1_judge)

            # ── AgentNode: narrative writer (must be last in sequence) ────────
            state = await narrative_writer(
                state, agent=self._writer_agent, cost_guard=self._cost_guard
            )

            # ── Conditional routing after narrative_writer ────────────────────
            route = route_after_quality(state)
            logger.info(
                "WatchlistScanWorkflow: routing to %s (confidence=%.4f)",
                route,
                state.overall_confidence,
            )

            if route == "dispatch":
                state = await dispatch(
                    state,
                    brief_repo=self._brief_repo,
                    email_service=self._email_service,
                )
                # High-anomaly deep-dive dispatch (TASK-016)
                if self._celery_app is not None:
                    state = await dispatch_high_anomalies(
                        state, celery_app=self._celery_app
                    )
            elif route == "hil_enqueue":
                state = await hil_enqueue(state, hil_repo=self._hil_repo)
            else:
                state = await block_and_notify(state)

        except Exception as exc:
            logger.exception(
                "WatchlistScanWorkflow: unhandled error for workflow=%s: %s",
                state.workflow_id,
                exc,
            )
            raise

        return state

    def invoke(self, state: WatchlistScanState, config: Any = None) -> WatchlistScanState:
        """Synchronous invocation — delegates to ainvoke via asyncio.get_event_loop."""
        import asyncio
        return asyncio.get_event_loop().run_until_complete(self.ainvoke(state, config))

    # ── HIL resume ────────────────────────────────────────────────────────────

    async def resume_from_hil(
        self,
        state: WatchlistScanState,
        *,
        approved: bool,
    ) -> WatchlistScanState:
        """Resume workflow after HIL review decision.

        Args:
            state: WatchlistScanState at the point of HIL pause.
            approved: True if reviewer approved dispatch; False if rejected.

        Returns:
            Updated state after resuming.
        """
        from src.ai.workflows.watchlist_scan_nodes import (
            block_and_notify,
            dispatch,
            dispatch_high_anomalies,
        )

        logger.info(
            "WatchlistScanWorkflow.resume_from_hil: workflow=%s approved=%s",
            state.workflow_id,
            approved,
        )

        if approved:
            state = await dispatch(
                state,
                brief_repo=self._brief_repo,
                email_service=self._email_service,
            )
            if self._celery_app is not None:
                state = await dispatch_high_anomalies(
                    state, celery_app=self._celery_app
                )
        else:
            state = await block_and_notify(state)

        return state


def build_watchlist_scan_workflow(**kwargs: Any) -> WatchlistScanWorkflow:
    """Factory function: build and return a WatchlistScanWorkflow instance.

    All keyword arguments are forwarded to WatchlistScanWorkflow.__init__.
    WorkflowStructureValidator is called inside the constructor.

    Returns:
        WatchlistScanWorkflow with ainvoke() interface.
    """
    return WatchlistScanWorkflow(**kwargs)
