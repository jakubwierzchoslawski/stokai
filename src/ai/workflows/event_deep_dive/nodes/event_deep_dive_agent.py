"""
ai.workflows.event_deep_dive.nodes.event_deep_dive_agent — AgentNode.

Invokes the event-deep-dive-analyst agent to produce a structured analysis
of the event, market reaction, and exposure data.

PLAN-F-010 TASK-007.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from src.ai.workflows.event_deep_dive.cost_accumulator import CostAccumulator
from src.ai.workflows.event_deep_dive.state import DeepDiveWorkflowState

logger = logging.getLogger(__name__)

_ROLE_ID = "event-deep-dive-analyst"


async def _invoke_agent(
    role_id: str,
    definition: Any,
    input_payload: dict,
) -> dict:
    """Invoke an agent and return structured output.

    This function is the patchable boundary for tests.  Production wiring
    replaces this with a real LLM call via ExecutionLimiter.

    Returns:
        dict with keys: role_id, confidence, cost_usd, output (dict).
    """
    # Stub implementation — returns a minimal valid structure.
    # Real implementation is wired in the graph builder via partial application.
    return {
        "role_id": role_id,
        "confidence": 0.8,
        "cost_usd": 0.05,
        "output": {"analysis": f"stub output from {role_id}"},
    }


async def event_deep_dive_agent(
    state: DeepDiveWorkflowState,
    *,
    registry: Any,
    cost_accumulator: CostAccumulator,
    langfuse_client: Any = None,
) -> DeepDiveWorkflowState:
    """Invoke the event-deep-dive-analyst agent.

    Inputs: state.event_full, state.market_reaction, state.exposure_analyses.
    Outputs: state.exposure_output (overloaded field), state.confidence_scores[_ROLE_ID].

    Args:
        state: Current DeepDiveWorkflowState.
        registry: AgentRegistry to resolve the agent definition.
        cost_accumulator: Shared cost accumulator (raises on ceiling hit).
        langfuse_client: Optional Langfuse client for span creation.

    Raises:
        CostCeilingExceededError: If the agent's cost would exceed the ceiling.
    """
    definition = registry.resolve(_ROLE_ID)

    # Serialize inputs within token limit
    input_payload = {
        "event_full": (
            state.event_full.model_dump(mode="json")
            if state.event_full is not None
            else None
        ),
        "market_reaction": {
            k: v.model_dump(mode="json")
            for k, v in state.market_reaction.items()
        },
        "exposure_analyses": [
            a.model_dump(mode="json") for a in state.exposure_analyses
        ],
    }

    result = await _invoke_agent(_ROLE_ID, definition, input_payload)

    # Update cost and confidence
    cost_accumulator.add(result["cost_usd"])

    new_scores = {**state.confidence_scores, _ROLE_ID: result["confidence"]}
    new_state = state.model_copy(
        update={
            "exposure_output": result.get("output"),
            "confidence_scores": new_scores,
            "cost_usd": state.cost_usd + result["cost_usd"],
        }
    )

    logger.info(
        "event_deep_dive_agent: confidence=%.2f cost_usd=%.4f",
        result["confidence"],
        result["cost_usd"],
    )
    return new_state
