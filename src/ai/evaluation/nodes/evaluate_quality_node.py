"""
evaluate_quality_node — LangGraph DeterministicNode that runs Tier-1 evaluation.

Topology position: second-to-last node, inserted before narrative_writer in every
Mode B workflow.

Behaviour:
- Calls Tier1JudgeService.evaluate_output() with state data.
- Sets state.confidence_scores["tier1_eval"] = result.overall_quality.
- Catches ALL Tier1JudgeService exceptions → logs warning, returns state unchanged.
- Langfuse score write is fire-and-forget (handled inside Tier1JudgeService).
"""
from __future__ import annotations

import logging
from typing import Any

from src.ai.workflows.state import WorkflowState

logger = logging.getLogger(__name__)


async def evaluate_quality_node(
    state: WorkflowState,
    tier1_judge: Any,
) -> WorkflowState:
    """
    LangGraph node that evaluates agent output quality via Tier-1 judge.

    Parameters
    ----------
    state:
        Current workflow state (WorkflowState).
    tier1_judge:
        ITier1Judge implementation (injected; never imported directly).

    Returns
    -------
    WorkflowState
        Updated state with confidence_scores["tier1_eval"] set.
        On error, returns state unchanged.
    """
    try:
        agent_output = state.recommendation or {}
        agent_input = state.inputs or {}

        # Collect tool outputs from exposure/historical/anomaly outputs
        tool_outputs: list[dict] = []
        for attr in ("exposure_output", "historical_output", "anomaly_output"):
            val = getattr(state, attr, None)
            if isinstance(val, dict):
                tool_outputs.append(val)

        result = await tier1_judge.evaluate_output(
            run_id=state.workflow_id,
            agent_role="recommendation-analyst",
            prompt_version=str(getattr(state, "langfuse_trace_id", "unknown") or "unknown"),
            agent_input=agent_input,
            agent_output=agent_output,
            tool_outputs=tool_outputs,
        )

        # Update state
        updated_scores = dict(state.confidence_scores)
        updated_scores["tier1_eval"] = result.overall_quality
        state = state.model_copy(
            update={"confidence_scores": updated_scores}
        )
        logger.debug(
            "evaluate_quality_node: run_id=%s overall_quality=%.3f",
            state.workflow_id,
            result.overall_quality,
        )

    except Exception as exc:
        logger.warning(
            "evaluate_quality_node: exception for run_id=%s (%s) — continuing",
            state.workflow_id,
            type(exc).__name__,
        )

    return state
