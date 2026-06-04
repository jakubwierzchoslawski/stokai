"""
ai.workflows.event_deep_dive.nodes.historical_context_agent — AgentNode.

Invokes the historical-context-analyst agent to find historical analogues.

PLAN-F-010 TASK-007.
"""
from __future__ import annotations

import logging
from typing import Any

from src.ai.workflows.event_deep_dive.cost_accumulator import CostAccumulator
from src.ai.workflows.event_deep_dive.state import DeepDiveWorkflowState

logger = logging.getLogger(__name__)

_ROLE_ID = "historical-context-analyst"


async def _invoke_agent(
    role_id: str,
    definition: Any,
    input_payload: dict,
) -> dict:
    """Patchable boundary for agent invocation in tests."""
    return {
        "role_id": role_id,
        "confidence": 0.8,
        "cost_usd": 0.05,
        "output": {"analogies": [], "historical_summary": "stub"},
    }


async def historical_context_agent(
    state: DeepDiveWorkflowState,
    *,
    registry: Any,
    cost_accumulator: CostAccumulator,
    langfuse_client: Any = None,
) -> DeepDiveWorkflowState:
    """Invoke the historical-context-analyst agent.

    Inputs: state.event_full, state.exposure_output (from event_deep_dive_agent).
    Outputs: state.historical_output, state.confidence_scores[_ROLE_ID].

    Raises:
        CostCeilingExceededError: If cost would exceed ceiling.
    """
    definition = registry.resolve(_ROLE_ID)

    input_payload = {
        "event_full": (
            state.event_full.model_dump(mode="json")
            if state.event_full is not None
            else None
        ),
        "event_analysis": state.exposure_output,
    }

    result = await _invoke_agent(_ROLE_ID, definition, input_payload)

    cost_accumulator.add(result["cost_usd"])

    new_scores = {**state.confidence_scores, _ROLE_ID: result["confidence"]}
    new_state = state.model_copy(
        update={
            "historical_output": result.get("output"),
            "confidence_scores": new_scores,
            "cost_usd": state.cost_usd + result["cost_usd"],
        }
    )

    logger.info(
        "historical_context_agent: confidence=%.2f cost_usd=%.4f",
        result["confidence"],
        result["cost_usd"],
    )
    return new_state
