"""
ai.workflows.on_demand.nodes.anomaly_detector_node — AgentNode.

Detects anomalies from exposure and historical context data.
Writes result to state.anomaly_output.
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

_ROLE_ID = "anomaly-detector"
_CEILING_USD = 1.50


async def _invoke_llm(
    state: WorkflowState,
    definition: Any,
) -> dict:
    """Invoke LLM for anomaly detection. Patchable in tests."""
    return {
        "output": {"anomalies": [], "severity": "low"},
        "confidence": 0.8,
        "cost_usd": 0.0,
        "input_tokens": 0,
        "output_tokens": 0,
    }


async def anomaly_detector_node(
    state: WorkflowState,
    *,
    registry: Any,
    cost_ceiling_usd: float = _CEILING_USD,
) -> WorkflowState:
    """Detect anomalies in exposure patterns.

    Steps:
      1. Resolve AgentDefinition.
      2. Invoke LLM.
      3. Validate output not None.
      4. Accumulate cost + tokens.
      5. Record confidence.
      6. Write to state.anomaly_output.
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
            "anomaly_output": output,
        }
    )

    guard = CostCeilingGuard(ceiling_usd=cost_ceiling_usd)
    guard.check(updated)

    return updated
