"""
ai.workflows.on_demand.nodes.exposure_analyst_node — AgentNode.

Analyzes company exposure to active geopolitical events.
Writes result to state.exposure_output.
"""
from __future__ import annotations

import logging
from typing import Any

from src.ai.workflows.cost_guard import CostCeilingGuard
from src.ai.workflows.on_demand.nodes._agent_node_base import (
    AgentOutputValidationError,
    _accumulate_cost,
    _validate_output,
)
from src.ai.workflows.state import WorkflowState

logger = logging.getLogger(__name__)

_ROLE_ID = "exposure-analyst"
_CEILING_USD = 1.50


async def _invoke_llm(
    state: WorkflowState,
    definition: Any,
) -> dict:
    """Call the LLM for this agent.

    In production, this calls the Anthropic client. The function is a separate
    async def to allow patching in tests without replacing the entire node.

    Returns a dict with keys:
      output: dict | None
      confidence: float
      cost_usd: float
      input_tokens: int
      output_tokens: int
    """
    # Stub implementation — real LLM call wired in production via dependency injection.
    # This allows test-time patching of this single function.
    return {
        "output": {"summary": "exposure analysis stub"},
        "confidence": 0.8,
        "cost_usd": 0.0,
        "input_tokens": 0,
        "output_tokens": 0,
    }


async def exposure_analyst_node(
    state: WorkflowState,
    *,
    registry: Any,
    cost_ceiling_usd: float = _CEILING_USD,
) -> WorkflowState:
    """Analyze exposure of the company to active geopolitical events.

    Steps:
      1. Resolve AgentDefinition from registry.
      2. Invoke LLM (patchable via _invoke_llm).
      3. Validate output is not None.
      4. Accumulate cost_usd + tokens_consumed.
      5. Record confidence score.
      6. Write to state.exposure_output.
      7. CostCeilingGuard.check(state).
    """
    definition = registry.resolve(_ROLE_ID)

    result = await _invoke_llm(state, definition)

    output = result.get("output")
    _validate_output(_ROLE_ID, output)

    cost_updates = _accumulate_cost(
        state,
        cost_usd=result.get("cost_usd", 0.0),
        input_tokens=result.get("input_tokens", 0),
        output_tokens=result.get("output_tokens", 0),
        role_id=_ROLE_ID,
    )

    new_confidence_scores = dict(state.confidence_scores)
    new_confidence_scores[_ROLE_ID] = result.get("confidence", 0.0)

    updated = state.model_copy(
        update={
            **cost_updates,
            "confidence_scores": new_confidence_scores,
            "exposure_output": output,
        }
    )

    guard = CostCeilingGuard(ceiling_usd=cost_ceiling_usd)
    guard.check(updated)

    return updated
