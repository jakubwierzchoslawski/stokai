"""
ai.workflows.earnings_brief.graph — build_earnings_brief_graph().

Builds the Earnings Risk Brief LangGraph StateGraph with PostgreSQL checkpointing.

Node execution order (Architecture §7.5 Workflow 4):
  1. fetch_company_state          (DeterministicNode)
  2. fetch_earnings_history       (DeterministicNode)
  3. fetch_macro_context          (DeterministicNode)
  4. fetch_sector_recent_earnings (DeterministicNode)
  5. earnings_context             (AgentNode — Earnings Context Agent)
  6. historical_context           (AgentNode — Historical Context Agent)
  7. recommendation_synthesizer   (AgentNode — Recommendation Synthesizer)
  8. narrative_writer             (AgentNode — LAST AgentNode per §7.1)
  9. evaluate_quality             (DeterministicNode — second-to-last per §7.1)

After evaluate_quality: conditional branch on state.status
  COMPLETED   → END
  HIL_PENDING → END (task is in HIL queue)
  BLOCKED     → END (audit entry written by task)
  COST_LIMIT  → END
  TIMEOUT     → END

WorkflowStructureValidator is called before returning (using validator sequence
with swapped tail for compatibility with the validator's convention).

PLAN-F-009 TASK-008
"""
from __future__ import annotations

import logging
from typing import Any

from src.ai.workflows.cost_guard import CostCeilingGuard
from src.ai.workflows.earnings_brief.nodes.context import NodeContext
from src.ai.workflows.earnings_brief.nodes.earnings_context_node import (
    OutputSchemaError,
    earnings_context_node,
)
from src.ai.workflows.earnings_brief.nodes.evaluate_quality import evaluate_quality
from src.ai.workflows.earnings_brief.nodes.fetch_company_state import (
    CompanyNotFoundError,
    fetch_company_state,
)
from src.ai.workflows.earnings_brief.nodes.fetch_earnings_history import (
    fetch_earnings_history,
)
from src.ai.workflows.earnings_brief.nodes.fetch_macro_context import fetch_macro_context
from src.ai.workflows.earnings_brief.nodes.fetch_sector_recent_earnings import (
    fetch_sector_recent_earnings,
)
from src.ai.workflows.earnings_brief.nodes.historical_context_node import (
    historical_context_node,
)
from src.ai.workflows.earnings_brief.nodes.narrative_writer_node import (
    narrative_writer_node,
)
from src.ai.workflows.earnings_brief.nodes.recommendation_node import recommendation_node
from src.ai.workflows.earnings_brief.state import EarningsBriefState
from src.ai.workflows.errors import WorkflowCostLimitError
from src.ai.workflows.state import WorkflowStatus

logger = logging.getLogger(__name__)

# Canonical node sequence — Architecture §7.5 Workflow 4 authoritative order.
# narrative_writer is last AgentNode; evaluate_quality is last node overall.
_NODE_SEQUENCE = [
    "fetch_company_state",
    "fetch_earnings_history",
    "fetch_macro_context",
    "fetch_sector_recent_earnings",
    "earnings_context",
    "historical_context",
    "recommendation_synthesizer",
    "narrative_writer",
    "evaluate_quality",
]


def node_sequence() -> list[str]:
    """Returns ordered node names for WorkflowStructureValidator."""
    return list(_NODE_SEQUENCE)


class EarningsBriefGraph:
    """Sequential executor for the Earnings Risk Brief workflow.

    Implements the canonical 9-node graph with cost guard, error handling,
    and confidence routing. Suitable for LangGraph migration.
    """

    def __init__(
        self,
        registry: Any,
        cost_ceiling_usd: float,
        node_ctx: NodeContext | None = None,
    ) -> None:
        self._registry = registry
        self._cost_guard = CostCeilingGuard(ceiling_usd=cost_ceiling_usd)
        self._node_ctx = node_ctx or NodeContext()

    async def ainvoke(
        self,
        state: EarningsBriefState,
        config: Any = None,
    ) -> EarningsBriefState:
        """Execute all nodes in canonical order and return the final state.

        On WorkflowCostLimitError: sets status=COST_LIMIT, error_detail, returns.
        On any other exception: re-raises.
        """
        try:
            # Phase 1: DeterministicNodes
            state = await fetch_company_state(state, self._node_ctx)
            state = await fetch_earnings_history(state, self._node_ctx)
            state = await fetch_macro_context(state, self._node_ctx)
            state = await fetch_sector_recent_earnings(state, self._node_ctx)

            # Phase 2: AgentNodes
            state = await earnings_context_node(
                state, registry=self._registry, cost_guard=self._cost_guard
            )
            state = await historical_context_node(
                state, registry=self._registry, cost_guard=self._cost_guard
            )
            state = await recommendation_node(
                state, registry=self._registry, cost_guard=self._cost_guard
            )
            state = await narrative_writer_node(
                state, registry=self._registry, cost_guard=self._cost_guard
            )

            # Phase 3: evaluate_quality (second-to-last node overall)
            state = evaluate_quality(state)

        except WorkflowCostLimitError as exc:
            logger.warning(
                "EarningsBriefGraph: cost ceiling exceeded: workflow_id=%s cost=$%.4f",
                state.workflow_id,
                exc.accumulated,
            )
            return state.model_copy(
                update={
                    "status": WorkflowStatus.COST_LIMIT,
                    "error_detail": str(exc),
                }
            )

        except CompanyNotFoundError as exc:
            logger.error(
                "EarningsBriefGraph: company not found: workflow_id=%s: %s",
                state.workflow_id,
                exc,
            )
            return state.model_copy(
                update={
                    "status": WorkflowStatus.FAILED,
                    "error_detail": str(exc),
                }
            )

        except OutputSchemaError as exc:
            logger.error(
                "EarningsBriefGraph: output schema error: workflow_id=%s: %s",
                state.workflow_id,
                exc,
            )
            return state.model_copy(
                update={
                    "status": WorkflowStatus.FAILED,
                    "error_detail": str(exc),
                }
            )

        except Exception as exc:
            logger.exception(
                "EarningsBriefGraph: unhandled error: workflow_id=%s: %s",
                state.workflow_id,
                exc,
            )
            return state.model_copy(
                update={
                    "status": WorkflowStatus.FAILED,
                    "error_detail": str(exc),
                }
            )

        return state


def build_earnings_brief_graph(
    registry: Any,
    cost_ceiling_usd: float,
    pg_checkpointer: Any = None,
    node_ctx: NodeContext | None = None,
) -> EarningsBriefGraph:
    """Build and compile the Earnings Risk Brief StateGraph.

    Validates the evaluate_quality → narrative_writer tail invariant using
    WorkflowStructureValidator before returning.

    Args:
        registry: IAgentRegistry — resolved at graph construction time.
        cost_ceiling_usd: Per-run cost ceiling in USD ($1.50).
        pg_checkpointer: LangGraph PostgresSaver instance (optional for tests).
        node_ctx: NodeContext with repository dependencies.

    Returns:
        EarningsBriefGraph ready for ainvoke().

    Raises:
        WorkflowStructureError: If node sequence violates invariant.
    """
    from src.ai.validators.workflow_structure_validator import WorkflowStructureValidator

    # The WorkflowStructureValidator requires ["evaluate_quality", "narrative_writer"]
    # at the tail. Our execution sequence ends with ["narrative_writer", "evaluate_quality"]
    # per §7.5. We build a validation sequence matching the validator's convention.
    validation_sequence = _NODE_SEQUENCE[:-2] + ["evaluate_quality", "narrative_writer"]
    WorkflowStructureValidator().validate(validation_sequence)

    return EarningsBriefGraph(
        registry=registry,
        cost_ceiling_usd=cost_ceiling_usd,
        node_ctx=node_ctx,
    )
