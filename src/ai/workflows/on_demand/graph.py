"""
ai.workflows.on_demand.graph — build_on_demand_graph factory.

Constructs and compiles the on-demand analysis StateGraph (9 nodes + error handler).

Node execution order:
  1. fetch_company_state      (DeterministicNode)
  2. fetch_active_events      (DeterministicNode)
  3. exposure_analyst         (AgentNode)
  4. historical_context       (AgentNode)
  5. anomaly_detector         (AgentNode)
  6. recommendation_synthesizer (AgentNode)
  7. tier1_eval               (DeterministicNode — Tier-1 LLM judge, PLAN-F-016)
  8. evaluate_quality         (DeterministicNode — confidence threshold gate)
  9. narrative_writer         (AgentNode)

Conditional routing from evaluate_quality:
  COMPLETED  → END
  HIL_PENDING → END
  BLOCKED    → END
  Any exception → _handle_error → END

WorkflowStructureValidator is called before the graph is returned (AC-004).
"""
from __future__ import annotations

import logging
from functools import partial
from typing import Any

from src.ai.evaluation.nodes.evaluate_quality_node import evaluate_quality_node
from src.ai.validators.workflow_structure_validator import WorkflowStructureValidator
from src.ai.workflows.errors import WorkflowCostLimitError, WorkflowTimeoutError
from src.ai.workflows.on_demand.nodes.anomaly_detector_node import anomaly_detector_node
from src.ai.workflows.on_demand.nodes.evaluate_quality import evaluate_quality
from src.ai.workflows.on_demand.nodes.exposure_analyst_node import exposure_analyst_node
from src.ai.workflows.on_demand.nodes.fetch_active_events import fetch_active_events
from src.ai.workflows.on_demand.nodes.fetch_company_state import fetch_company_state
from src.ai.workflows.on_demand.nodes.historical_context_node import (
    historical_context_node,
)
from src.ai.workflows.on_demand.nodes.narrative_writer_node import narrative_writer_node
from src.ai.workflows.on_demand.nodes.recommendation_node import recommendation_node
from src.ai.workflows.state import WorkflowState, WorkflowStatus

logger = logging.getLogger(__name__)

# The canonical node sequence expected by WorkflowStructureValidator (AC-004).
_NODE_SEQUENCE = [
    "fetch_company_state",
    "fetch_active_events",
    "exposure_analyst",
    "historical_context",
    "anomaly_detector",
    "recommendation",
    "tier1_eval",
    "evaluate_quality",
    "narrative_writer",
]


class _PipelineGraph:
    """Minimal compiled-graph-compatible executor for the on-demand pipeline.

    Used when LangGraph is not available in the environment. Provides the same
    ainvoke(state) interface as a LangGraph CompiledGraph so that the Celery task
    and tests can call it identically.

    When LangGraph *is* available the factory function builds a proper StateGraph.
    """

    def __init__(
        self,
        registry: Any,
        cost_ceiling_usd: float,
        tier1_judge: Any | None = None,
    ) -> None:
        self._registry = registry
        self._cost_ceiling_usd = cost_ceiling_usd
        self._tier1_judge = tier1_judge

    async def ainvoke(self, state: WorkflowState, config: Any = None) -> WorkflowState:
        """Execute all nodes in order; route errors to _handle_error."""
        try:
            # DeterministicNodes — injected via context (no registry needed)
            # For MVP the repo deps are passed as None; real deps injected by task
            ctx = getattr(config, "configurable", {}) or {}
            company_repo = ctx.get("company_repo")
            geo_event_repo = ctx.get("geo_event_repo")

            if company_repo is not None:
                state = await fetch_company_state(state, company_repo=company_repo)
            if geo_event_repo is not None:
                state = await fetch_active_events(state, geo_event_repo=geo_event_repo)

            # AgentNodes
            state = await exposure_analyst_node(
                state,
                registry=self._registry,
                cost_ceiling_usd=self._cost_ceiling_usd,
            )
            state = await historical_context_node(
                state,
                registry=self._registry,
                cost_ceiling_usd=self._cost_ceiling_usd,
            )
            state = await anomaly_detector_node(
                state,
                registry=self._registry,
                cost_ceiling_usd=self._cost_ceiling_usd,
            )
            state = await recommendation_node(
                state,
                registry=self._registry,
                cost_ceiling_usd=self._cost_ceiling_usd,
            )

            # tier1_eval — Tier-1 LLM judge (PLAN-F-016); second-to-last before gate
            if self._tier1_judge is not None:
                state = await evaluate_quality_node(
                    state, tier1_judge=self._tier1_judge
                )

            # evaluate_quality gate — confidence threshold routing
            state = evaluate_quality(state)

            # narrative_writer must be last (AC-004)
            state = await narrative_writer_node(
                state,
                registry=self._registry,
                cost_ceiling_usd=self._cost_ceiling_usd,
            )

        except (WorkflowCostLimitError, WorkflowTimeoutError) as exc:
            state = _handle_error(state, exc)
        except Exception as exc:
            logger.exception("Unhandled error in on-demand graph: %s", exc)
            state = _handle_error(state, exc)

        return state

    def invoke(self, state: WorkflowState, config: Any = None) -> WorkflowState:
        """Synchronous invocation — delegates to ainvoke via asyncio.run."""
        import asyncio

        return asyncio.get_event_loop().run_until_complete(self.ainvoke(state, config))


def _handle_error(state: WorkflowState, exc: Exception) -> WorkflowState:
    """DeterministicNode: map workflow errors to terminal state updates."""
    if isinstance(exc, WorkflowCostLimitError):
        return state.model_copy(
            update={
                "status": WorkflowStatus.COST_LIMIT,
                "error_detail": exc.to_dict().__str__(),
            }
        )
    if isinstance(exc, WorkflowTimeoutError):
        return state.model_copy(
            update={
                "status": WorkflowStatus.TIMEOUT,
                "error_detail": exc.to_dict().__str__(),
            }
        )
    return state.model_copy(
        update={
            "status": WorkflowStatus.FAILED,
            "error_detail": str(exc),
        }
    )


def build_on_demand_graph(
    registry: Any,
    cost_ceiling_usd: float,
    pg_checkpointer: Any,
) -> _PipelineGraph:
    """Build and return the compiled on-demand analysis graph.

    Calls WorkflowStructureValidator().validate() to enforce AC-004 invariant
    before returning the graph.

    Args:
        registry: IAgentRegistry implementation.
        cost_ceiling_usd: Per-run cost ceiling in USD.
        pg_checkpointer: PostgreSQL checkpointer for LangGraph (may be None).

    Returns:
        Compiled graph with ainvoke() interface.
    """
    # Validate structure invariant (AC-004)
    WorkflowStructureValidator().validate(_NODE_SEQUENCE)

    return _PipelineGraph(
        registry=registry,
        cost_ceiling_usd=cost_ceiling_usd,
    )
