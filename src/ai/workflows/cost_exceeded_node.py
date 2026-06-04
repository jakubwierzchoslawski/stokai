"""
src.ai.workflows.cost_exceeded_node — Shared terminal node for workflow cost ceiling breaches.

DeterministicNode: no LLM calls, no side effects beyond state mutation and logging.

Used by all five Mode B workflow graphs as the handler for WorkflowBudgetExceededError.
When the per-workflow cost ceiling is reached mid-execution, the graph routes to this
node which:
  1. Sets state.cost_limited = True.
  2. Sets state.status = WorkflowStatus.COST_LIMIT ("cost_exceeded").
  3. Preserves whatever partial recommendations/report exist in state (not cleared).
  4. Logs a structured ERROR event with workflow_id, workflow_type, cost_usd, ceiling_usd.
  5. Does NOT dispatch any email to the end user.

Admin notification is via the structured ERROR log consumed by the log aggregation
pipeline (admin cost monitor, PLAN-F-030).

PLAN-N-004 TASK-007
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from src.ai.workflows.state import WorkflowState, WorkflowStatus

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


def cost_exceeded_node(state: WorkflowState) -> WorkflowState:
    """Terminal DeterministicNode — handles workflow cost ceiling breach.

    Sets cost_limited=True and status=COST_LIMIT on the state.  Preserves
    all partial results.  Logs a structured ERROR.  Does NOT dispatch email.

    Args:
        state: The current WorkflowState at the point of ceiling breach.
               state.cost_usd should reflect the accumulated cost at breach time.

    Returns:
        Updated WorkflowState with cost_limited=True and status=COST_LIMIT.
    """
    # Collect partial results metadata for structured log
    partial_recommendations_count = (
        len(state.active_events)
        + (1 if state.recommendation is not None else 0)
        + (1 if state.report is not None else 0)
        + (1 if state.exposure_output is not None else 0)
        + (1 if state.historical_output is not None else 0)
        + (1 if state.anomaly_output is not None else 0)
    )

    logger.error(
        "cost_exceeded_node: workflow terminated by cost ceiling "
        "workflow_id=%s workflow_type=%r cost_usd=%.4f "
        "partial_results_count=%d status=cost_exceeded",
        state.workflow_id,
        state.workflow_type.value if hasattr(state.workflow_type, "value") else str(state.workflow_type),
        state.cost_usd,
        partial_recommendations_count,
    )

    # Mutate state — set cost_limited and status
    updated = state.model_copy(
        update={
            "cost_limited": True,
            "status": WorkflowStatus.COST_LIMIT,
        }
    )

    return updated
