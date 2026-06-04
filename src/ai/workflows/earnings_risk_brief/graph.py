"""
ai.workflows.earnings_risk_brief.graph — EarningsRiskBriefGraph stub.

Node execution order:
  1. fetch_earnings_calendar    (DeterministicNode)
  2. earnings_context_agent     (AgentNode)
  3. risk_assessment_agent      (AgentNode)
  4. recommendation_agent       (AgentNode)
  5. evaluate_quality           (DeterministicNode — Tier-1 LLM judge, PLAN-F-016)
  6. narrative_writer           (AgentNode — LAST)

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
    "fetch_earnings_calendar",
    "earnings_context_agent",
    "risk_assessment_agent",
    "recommendation_agent",
    "evaluate_quality",
    "narrative_writer",
]


class EarningsRiskBriefGraph:
    """
    Stub sequential executor for the Earnings Risk Brief workflow.

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
        if self._tier1_judge is not None:
            state = await evaluate_quality_node(
                state, tier1_judge=self._tier1_judge
            )
        logger.debug(
            "EarningsRiskBriefGraph.ainvoke: stub run for workflow_id=%s",
            state.workflow_id,
        )
        return state


def build_earnings_risk_brief_graph(
    registry: Any,
    cost_ceiling_usd: float,
    tier1_judge: Any | None = None,
) -> EarningsRiskBriefGraph:
    """Build and return the earnings risk brief graph."""
    return EarningsRiskBriefGraph(
        registry=registry,
        cost_ceiling_usd=cost_ceiling_usd,
        tier1_judge=tier1_judge,
    )
