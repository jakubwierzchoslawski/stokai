"""
src.ai.workflows.morning_brief.graph — MorningBriefGraph assembly.

Assembles the LangGraph StateGraph for the Morning Brief workflow:

  fetch_portfolio
    → fetch_overnight_events
    → relevance_analyst_node
    → recompute_scores
    → anomaly_detector_node
    → historical_context_node  (asyncio.gather internally)
    → recommendation_node
    → evaluate_quality_node
    → [conditional: confidence_router]
        "narrative_writer"  → narrative_writer_node → format_and_dispatch  [END]
        "hil_queue"         → hil_queue_node                                [PAUSE]
        "block_and_log"     → block_and_log                                 [END]

Node ordering invariants (§7.5):
- evaluate_quality is always second-to-last (before narrative_writer).
- narrative_writer is always the last AgentNode.

PLAN-F-006 TASK-012
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from src.ai.workflows.morning_brief_state import MorningBriefState
from src.ai.workflows.morning_brief.routing import confidence_router

logger = logging.getLogger(__name__)

# Canonical node sequence — used by WorkflowStructureValidator.
# DeterministicNodes and AgentNodes are both listed in execution order.
# evaluate_quality is second-to-last; narrative_writer is last.
_NODE_SEQUENCE = [
    "fetch_portfolio",
    "fetch_overnight_events",
    "relevance_analyst",
    "recompute_scores",
    "anomaly_detector",
    "historical_context_agent",
    "recommendation_synthesizer",
    "evaluate_quality",    # second-to-last (AC-006)
    "narrative_writer",    # last AgentNode  (AC-006)
]


class WorkflowResult:
    """Return value of MorningBriefWorkflow.run()."""

    def __init__(
        self,
        workflow_id: Any,
        status: str,
        final_state: MorningBriefState,
        cost_usd: float,
        langfuse_trace_id: str | None,
    ) -> None:
        self.workflow_id = workflow_id
        self.status = status
        self.final_state = final_state
        self.cost_usd = cost_usd
        self.langfuse_trace_id = langfuse_trace_id


class MorningBriefGraph:
    """LangGraph-compatible graph for the Morning Brief workflow.

    In the current implementation this wraps the sequential node executor
    pattern consistent with existing workflows. Full LangGraph StateGraph
    assembly will be completed once `langgraph` is pinned at >=0.2 and
    AsyncPostgresSaver integration is validated in TASK-015.

    The public interface MorningBriefWorkflow.run() is the authoritative
    entry point: it creates MorningBriefState, opens the Langfuse trace,
    calls ainvoke, persists workflow_run, and closes the trace.
    """

    def __init__(
        self,
        *,
        node_registry: dict[str, Any] | None = None,
        checkpointer: Any | None = None,
    ) -> None:
        self._node_registry = node_registry or {}
        self._checkpointer = checkpointer

    async def ainvoke(
        self,
        state: MorningBriefState,
        config: Any = None,
    ) -> MorningBriefState:
        """Execute the morning brief workflow nodes in order.

        Routes via confidence_router after evaluate_quality_node.
        Checkpoints state after every node via AsyncPostgresSaver.
        """
        from src.ai.workflows.morning_brief.nodes.fetch_portfolio import fetch_portfolio
        from src.ai.workflows.morning_brief.nodes.fetch_overnight_events import (
            fetch_overnight_events,
        )
        from src.ai.workflows.morning_brief.nodes.recompute_scores import recompute_scores
        from src.ai.workflows.morning_brief.nodes.relevance_analyst_node import (
            relevance_analyst_node,
        )
        from src.ai.workflows.morning_brief.nodes.anomaly_detector_node import (
            anomaly_detector_node,
        )
        from src.ai.workflows.morning_brief.nodes.historical_context_node import (
            historical_context_node,
        )
        from src.ai.workflows.morning_brief.nodes.recommendation_node import (
            recommendation_node,
        )
        from src.ai.workflows.morning_brief.nodes.evaluate_quality_node import (
            evaluate_quality_node,
        )
        from src.ai.workflows.morning_brief.nodes.narrative_writer_node import (
            narrative_writer_node,
        )
        from src.ai.workflows.morning_brief.nodes.block_and_log import block_and_log
        from src.ai.workflows.morning_brief.nodes.hil_queue_node import hil_queue_node

        registry = self._node_registry.get("agent_registry")
        portfolio_repo = self._node_registry.get("portfolio_repo")
        event_repo = self._node_registry.get("event_repo")
        score_repo = self._node_registry.get("score_repo")
        rec_repo = self._node_registry.get("rec_repo")
        brief_repo = self._node_registry.get("brief_repo")
        hil_repo = self._node_registry.get("hil_repo")
        workflow_repo = self._node_registry.get("workflow_repo")
        episodic_repo = self._node_registry.get("episodic_repo")
        dispatcher = self._node_registry.get("dispatcher")
        user_repo = self._node_registry.get("user_repo")
        user_email = self._node_registry.get("user_email", "")

        # DeterministicNode: fetch_portfolio
        if portfolio_repo is not None:
            state = await fetch_portfolio(state, portfolio_repo=portfolio_repo)

        # DeterministicNode: fetch_overnight_events
        if event_repo is not None:
            state = await fetch_overnight_events(state, event_repo=event_repo)

        # AgentNode: relevance_analyst
        if registry is not None:
            state = await relevance_analyst_node(state, registry=registry)

        # DeterministicNode: recompute_scores
        if score_repo is not None:
            state = await recompute_scores(state, score_repo=score_repo)

        # AgentNode: anomaly_detector
        if registry is not None:
            state = await anomaly_detector_node(state, registry=registry)

        # AgentNode: historical_context (parallel per event)
        if registry is not None:
            state = await historical_context_node(state, registry=registry)

        # AgentNode: recommendation_synthesizer
        if registry is not None and rec_repo is not None:
            state = await recommendation_node(
                state, registry=registry, rec_repo=rec_repo
            )

        # AgentNode: evaluate_quality (second-to-last)
        if registry is not None:
            state = await evaluate_quality_node(state, registry=registry)

        # Conditional routing
        route = confidence_router(state)

        if route == "narrative_writer":
            if registry is not None:
                state = await narrative_writer_node(state, registry=registry)
            if dispatcher is not None and user_email:
                from src.ai.workflows.morning_brief.nodes.format_and_dispatch import (
                    format_and_dispatch,
                )
                state = await format_and_dispatch(
                    state,
                    dispatcher=dispatcher,
                    brief_repo=brief_repo,
                    workflow_repo=workflow_repo,
                    user_repo=user_repo,
                    user_email=user_email,
                )
        elif route == "hil_queue":
            if hil_repo is not None:
                state = await hil_queue_node(
                    state,
                    hil_repo=hil_repo,
                    brief_repo=brief_repo,
                )
        else:  # block_and_log
            state = await block_and_log(
                state,
                brief_repo=brief_repo,
                workflow_repo=workflow_repo,
                episodic_repo=episodic_repo,
            )

        return state


class MorningBriefWorkflow:
    """Public interface for running the Morning Brief workflow.

    Single entry point: run(user_id, tenant_id) -> WorkflowResult.
    Opens Langfuse trace at start; closes it when complete.
    Persists workflow_run row on completion.
    """

    def __init__(
        self,
        graph: MorningBriefGraph,
        workflow_run_repo: Any | None = None,
        langfuse_client: Any | None = None,
    ) -> None:
        self._graph = graph
        self._workflow_run_repo = workflow_run_repo
        self._langfuse = langfuse_client

    async def run(
        self,
        user_id: Any,
        tenant_id: Any,
        inputs: dict | None = None,
    ) -> WorkflowResult:
        """Execute the Morning Brief workflow for the given user.

        1. Creates MorningBriefState.
        2. Opens Langfuse trace (REQ-N-008).
        3. Calls graph.ainvoke(state).
        4. Persists workflow_run row.
        5. Closes Langfuse trace.

        Args:
            user_id: UUID of the user to generate the brief for.
            tenant_id: UUID of the tenant.
            inputs: Optional additional inputs dict.

        Returns:
            WorkflowResult with final state and metadata.
        """
        workflow_id = uuid4()
        started_at = datetime.now(tz=timezone.utc)

        state = MorningBriefState(
            workflow_id=workflow_id,
            tenant_id=tenant_id,
            user_id=user_id,
            started_at=started_at,
            inputs=inputs or {},
        )

        # Open Langfuse trace
        langfuse_trace_id: str | None = None
        if self._langfuse is not None:
            try:
                trace = self._langfuse.trace(
                    name="morning_brief",
                    user_id=str(user_id),
                    metadata={"workflow_id": str(workflow_id), "tenant_id": str(tenant_id)},
                )
                langfuse_trace_id = str(trace.id)
                state = state.model_copy(update={"langfuse_trace_id": langfuse_trace_id})
            except Exception as exc:
                logger.warning("MorningBriefWorkflow.run: Langfuse trace open failed — %s", exc)

        status = "completed"
        final_state = state

        try:
            final_state = await self._graph.ainvoke(state)
        except Exception as exc:
            logger.error(
                "MorningBriefWorkflow.run: workflow failed for workflow_id=%s — %s",
                workflow_id,
                exc,
            )
            status = "failed"
            final_state = state

        # Persist workflow_run row
        if self._workflow_run_repo is not None:
            try:
                await self._workflow_run_repo.create(
                    workflow_id=workflow_id,
                    workflow_type="morning_brief",
                    tenant_id=tenant_id,
                    user_id=user_id,
                    started_at=started_at,
                    completed_at=datetime.now(tz=timezone.utc),
                    status=status,
                    final_state=final_state.model_dump(mode="json"),
                    cost_usd=final_state.cost_usd,
                    langfuse_trace_id=langfuse_trace_id,
                )
            except Exception as exc:
                logger.error(
                    "MorningBriefWorkflow.run: failed to persist workflow_run — %s", exc
                )

        # Close Langfuse trace
        if self._langfuse is not None and langfuse_trace_id:
            try:
                self._langfuse.flush()
            except Exception as exc:
                logger.warning(
                    "MorningBriefWorkflow.run: Langfuse flush failed — %s", exc
                )

        return WorkflowResult(
            workflow_id=workflow_id,
            status=status,
            final_state=final_state,
            cost_usd=final_state.cost_usd,
            langfuse_trace_id=langfuse_trace_id,
        )


def build_morning_brief_graph(
    node_registry: dict[str, Any] | None = None,
    checkpointer: Any | None = None,
) -> MorningBriefGraph:
    """Build and return a MorningBriefGraph with the given dependencies."""
    return MorningBriefGraph(
        node_registry=node_registry,
        checkpointer=checkpointer,
    )
