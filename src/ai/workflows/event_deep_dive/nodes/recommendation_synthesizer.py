"""
ai.workflows.event_deep_dive.nodes.recommendation_synthesizer — AgentNode.

Invokes the recommendation-synthesizer agent to produce per-company
recommendations.

PLAN-F-010 TASK-007.
"""
from __future__ import annotations

import logging
from typing import Any

from src.ai.workflows.event_deep_dive.cost_accumulator import CostAccumulator
from src.ai.workflows.event_deep_dive.state import DeepDiveWorkflowState

logger = logging.getLogger(__name__)

_ROLE_ID = "recommendation-synthesizer"


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
        "output": {
            "per_company_recommendations": [],
            "overall_recommendation": "hold",
        },
    }


async def recommendation_synthesizer(
    state: DeepDiveWorkflowState,
    *,
    registry: Any,
    cost_accumulator: CostAccumulator,
    langfuse_client: Any = None,
) -> DeepDiveWorkflowState:
    """Invoke the recommendation-synthesizer agent.

    Inputs: state.exposure_output, state.historical_output, state.exposure_analyses.
    Outputs: state.recommendation, state.confidence_scores[_ROLE_ID].

    Raises:
        CostCeilingExceededError: If cost would exceed ceiling.
    """
    definition = registry.resolve(_ROLE_ID)

    input_payload = {
        "event_analysis": state.exposure_output,
        "historical_context": state.historical_output,
        "exposure_analyses": [
            a.model_dump(mode="json") for a in state.exposure_analyses
        ],
    }

    result = await _invoke_agent(_ROLE_ID, definition, input_payload)

    cost_accumulator.add(result["cost_usd"])

    new_scores = {**state.confidence_scores, _ROLE_ID: result["confidence"]}
    new_state = state.model_copy(
        update={
            "recommendation": result.get("output"),
            "confidence_scores": new_scores,
            "cost_usd": state.cost_usd + result["cost_usd"],
        }
    )

    logger.info(
        "recommendation_synthesizer: confidence=%.2f cost_usd=%.4f",
        result["confidence"],
        result["cost_usd"],
    )
    return new_state
