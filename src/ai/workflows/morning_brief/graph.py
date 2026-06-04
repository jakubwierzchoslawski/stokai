"""
ai.workflows.morning_brief.graph — MorningBriefGraph stub.

Node execution order:
  1. fetch_portfolio_state     (DeterministicNode)
  2. market_scan_agent         (AgentNode)
  3. portfolio_impact_agent    (AgentNode)
  4. recommendation_agent      (AgentNode)
  5. evaluate_quality          (DeterministicNode — Tier-1 LLM judge, PLAN-F-016)
  6. narrative_writer          (AgentNode — LAST)

Topology: evaluate_quality is second-to-last; narrative_writer is last.
"""
from __future__ import annotations

import logging
from typing import Any

from src.ai.evaluation.nodes.evaluate_quality_node import evaluate_quality_node
from src.ai.workflows.state import WorkflowState

logger = logging.getLogger(__name__)

# The canonical node sequence for WorkflowStructureValidator (AC-004).
_NODE_SEQUENCE = [
    "fetch_portfolio_state",
    "market_scan_agent",
    "portfolio_impact_agent",
    "recommendation_agent",
    "evaluate_quality",
    "narrative_writer",
]


class MorningBriefGraph:
    """
    Stub sequential executor for the Morning Brief workflow.

    Full implementation is delivered in a later PLAN. This stub establishes
    the correct node ordering so that evaluate_quality appears before
    narrative_writer as required by PLAN-F-016.
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

    async def ainvoke(
        self, state: WorkflowState, config: Any = None
    ) -> WorkflowState:
        """Execute nodes in order; evaluate_quality runs before narrative_writer."""
        # Tier-1 eval (second-to-last before narrative_writer)
        if self._tier1_judge is not None:
            state = await evaluate_quality_node(
                state, tier1_judge=self._tier1_judge
            )
        # narrative_writer stub — last node
        logger.debug(
            "MorningBriefGraph.ainvoke: stub run for workflow_id=%s",
            state.workflow_id,
        )
        return state


def build_morning_brief_graph(
    registry: Any,
    cost_ceiling_usd: float,
    tier1_judge: Any | None = None,
) -> MorningBriefGraph:
    """Build and return the morning brief graph."""
    return MorningBriefGraph(
        registry=registry,
        cost_ceiling_usd=cost_ceiling_usd,
        tier1_judge=tier1_judge,
    )
