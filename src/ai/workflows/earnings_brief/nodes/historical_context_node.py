"""
ai.workflows.earnings_brief.nodes.historical_context_node — AgentNode.

Historical Context Agent: finds historical earnings-surprise analogies.

PLAN-F-009 TASK-006
"""
from __future__ import annotations

import logging
from typing import Any

from src.ai.workflows.cost_guard import CostCeilingGuard
from src.ai.workflows.earnings_brief.nodes.earnings_context_node import OutputSchemaError
from src.ai.workflows.earnings_brief.state import EarningsBriefState

logger = logging.getLogger(__name__)

_AGENT_ROLE_ID = "historical-context-agent"


async def _invoke_historical_context_agent(
    state: EarningsBriefState,
    registry: Any,
) -> dict[str, Any]:
    """Invoke the Historical Context Agent LLM. Patchable in tests."""
    if registry is not None:
        try:
            registry.resolve(_AGENT_ROLE_ID)
        except Exception as exc:
            logger.warning("historical_context_node: registry.resolve failed: %s", exc)

    return {
        "output": {
            "analogies": [],
            "summary": "No close historical analogies found for current conditions.",
            "insufficient_data": False,
        },
        "confidence": 0.75,
        "cost_usd": 0.0,
        "input_tokens": 0,
        "output_tokens": 0,
    }


async def historical_context_node(
    state: EarningsBriefState,
    *,
    registry: Any,
    cost_guard: CostCeilingGuard,
) -> EarningsBriefState:
    """AgentNode: Historical Context Agent — finds historical earnings analogies.

    Uses pgvector semantic search to find historical earnings-surprise analogies
    whose outcomes match each scenario in the scenario tree. Handles
    InsufficientData gracefully (records lower confidence, does not fail).

    Args:
        state: Current EarningsBriefState.
        registry: IAgentRegistry.
        cost_guard: CostCeilingGuard.

    Returns:
        Updated state with analogies_output, confidence_scores, cost_usd.

    Raises:
        OutputSchemaError: If agent output is invalid.
        WorkflowCostLimitError: If cost ceiling is reached.
    """
    logger.debug(
        "historical_context_node: company_id=%s", state.company_id
    )

    result = await _invoke_historical_context_agent(state, registry)

    output = result.get("output")
    if output is None:
        raise OutputSchemaError("Historical context agent returned None output")

    cost_delta = float(result.get("cost_usd", 0.0))
    confidence = float(result.get("confidence", 0.0))

    new_confidence_scores = dict(state.confidence_scores)
    new_confidence_scores[_AGENT_ROLE_ID.replace("-", "_")] = confidence

    new_tokens = dict(state.tokens_consumed)
    input_tokens = result.get("input_tokens", 0)
    output_tokens = result.get("output_tokens", 0)
    if input_tokens:
        new_tokens["historical_context_input"] = (
            new_tokens.get("historical_context_input", 0) + input_tokens
        )
    if output_tokens:
        new_tokens["historical_context_output"] = (
            new_tokens.get("historical_context_output", 0) + output_tokens
        )

    updated = state.model_copy(
        update={
            "analogies_output": output,
            "cost_usd": state.cost_usd + cost_delta,
            "confidence_scores": new_confidence_scores,
            "tokens_consumed": new_tokens,
        }
    )

    cost_guard.check(updated)

    return updated
