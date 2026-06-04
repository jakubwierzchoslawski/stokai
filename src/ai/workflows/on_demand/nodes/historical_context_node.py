"""
ai.workflows.on_demand.nodes.historical_context_node — AgentNode.

Retrieves and synthesizes historical analogues for the active events.
Uses asyncio.gather for parallel sub-tasks.
Writes result to state.historical_output.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from src.ai.workflows.cost_guard import CostCeilingGuard
from src.ai.workflows.on_demand.nodes._agent_node_base import (
    _accumulate_cost,
    _validate_output,
)
from src.ai.workflows.state import WorkflowState

logger = logging.getLogger(__name__)

_ROLE_ID = "historical-context"
_CEILING_USD = 1.50


async def _invoke_llm(
    state: WorkflowState,
    definition: Any,
    sub_task: str = "primary",
) -> dict:
    """Call the LLM for a historical context sub-task.

    Sub-tasks are gathered in parallel via asyncio.gather in the main node.
    Patchable in tests.
    """
    return {
        "output": {"analogies": [], "sub_task": sub_task},
        "confidence": 0.8,
        "cost_usd": 0.0,
        "input_tokens": 0,
        "output_tokens": 0,
    }


async def historical_context_node(
    state: WorkflowState,
    *,
    registry: Any,
    cost_ceiling_usd: float = _CEILING_USD,
) -> WorkflowState:
    """Retrieve historical analogies using parallel async sub-tasks.

    Steps:
      1. Resolve AgentDefinition.
      2. Launch parallel sub-tasks via asyncio.gather.
      3. Merge results, validate output not None.
      4. Accumulate cost + tokens.
      5. Record confidence score.
      6. Write to state.historical_output.
      7. CostCeilingGuard.check(state).
    """
    definition = registry.resolve(_ROLE_ID)

    # Parallel sub-tasks: primary analysis + supplementary context
    results = await asyncio.gather(
        _invoke_llm(state, definition, sub_task="primary"),
        _invoke_llm(state, definition, sub_task="supplementary"),
    )

    # Merge results: use primary confidence, combine outputs
    primary, supplementary = results
    output = {
        "primary": primary.get("output"),
        "supplementary": supplementary.get("output"),
    }

    _validate_output(_ROLE_ID, output)

    total_cost = sum(r.get("cost_usd", 0.0) for r in results)
    total_input_tokens = sum(r.get("input_tokens", 0) for r in results)
    total_output_tokens = sum(r.get("output_tokens", 0) for r in results)
    confidence = primary.get("confidence", 0.0)

    cost_updates = _accumulate_cost(
        state,
        cost_usd=total_cost,
        input_tokens=total_input_tokens,
        output_tokens=total_output_tokens,
        role_id=_ROLE_ID,
    )

    new_confidence_scores = dict(state.confidence_scores)
    new_confidence_scores[_ROLE_ID] = confidence

    updated = state.model_copy(
        update={
            **cost_updates,
            "confidence_scores": new_confidence_scores,
            "historical_output": output,
        }
    )

    guard = CostCeilingGuard(ceiling_usd=cost_ceiling_usd)
    guard.check(updated)

    return updated
