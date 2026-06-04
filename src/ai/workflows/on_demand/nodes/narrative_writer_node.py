"""
ai.workflows.on_demand.nodes.narrative_writer_node — AgentNode.

Writes the final narrative report from recommendation and all analyses.
Writes result to state.report.

Must be the last AgentNode (before evaluate_quality DeterministicNode).
"""
from __future__ import annotations

import logging
from typing import Any

from src.ai.workflows.cost_guard import CostCeilingGuard
from src.ai.workflows.on_demand.nodes._agent_node_base import (
    _accumulate_cost,
    _validate_output,
)
from src.ai.workflows.state import WorkflowState

logger = logging.getLogger(__name__)

_ROLE_ID = "narrative-writer"
_CEILING_USD = 1.50


async def _invoke_llm(
    state: WorkflowState,
    definition: Any,
) -> dict:
    """Invoke LLM for narrative writing. Patchable in tests."""
    return {
        "output": {"sections": ["executive_summary", "risk_analysis"], "text": "stub"},
        "confidence": 0.8,
        "cost_usd": 0.0,
        "input_tokens": 0,
        "output_tokens": 0,
    }


async def narrative_writer_node(
    state: WorkflowState,
    *,
    registry: Any,
    cost_ceiling_usd: float = _CEILING_USD,
) -> WorkflowState:
    """Write the final analysis narrative/report.

    Steps:
      1. Resolve AgentDefinition.
      2. Invoke LLM.
      3. Validate output not None.
      4. Accumulate cost + tokens.
      5. Record confidence.
      6. Write to state.report.
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
            "report": output,
        }
    )

    guard = CostCeilingGuard(ceiling_usd=cost_ceiling_usd)
    guard.check(updated)

    return updated
