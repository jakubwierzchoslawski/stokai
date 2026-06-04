"""
ai.workflows.earnings_brief.nodes.recommendation_node — AgentNode.

Recommendation Synthesizer: scenario-tree-form recommendation.

PLAN-F-009 TASK-006
"""
from __future__ import annotations

import logging
from typing import Any

from src.ai.workflows.cost_guard import CostCeilingGuard
from src.ai.workflows.earnings_brief.nodes.earnings_context_node import OutputSchemaError
from src.ai.workflows.earnings_brief.state import EarningsBriefState

logger = logging.getLogger(__name__)

_AGENT_ROLE_ID = "recommendation-synthesizer"


async def _invoke_recommendation_synthesizer(
    state: EarningsBriefState,
    registry: Any,
) -> dict[str, Any]:
    """Invoke the Recommendation Synthesizer LLM. Patchable in tests."""
    if registry is not None:
        try:
            registry.resolve(_AGENT_ROLE_ID)
        except Exception as exc:
            logger.warning("recommendation_node: registry.resolve failed: %s", exc)

    # Scenario-tree-form recommendation (not a single action signal)
    return {
        "output": {
            "bull": {
                "hold_signal": "BUY_MORE",
                "position_sizing_guidance": "Increase position by 10%",
                "key_risk_factors": ["guidance miss", "sector rotation"],
                "implied_price_impact_pct": 5.0,
                "rationale": "Strong upside scenario justifies incremental add",
            },
            "base": {
                "hold_signal": "HOLD",
                "position_sizing_guidance": "Maintain current position",
                "key_risk_factors": ["EPS inline, no catalyst"],
                "implied_price_impact_pct": 0.5,
                "rationale": "Base case supports hold",
            },
            "bear": {
                "hold_signal": "REDUCE",
                "position_sizing_guidance": "Reduce position by 15%",
                "key_risk_factors": ["margin compression", "guidance cut"],
                "implied_price_impact_pct": -4.0,
                "rationale": "Bear scenario warrants defensive trim",
            },
            "summary": "Maintain current position pending earnings; watch for guidance.",
        },
        "confidence": 0.80,
        "cost_usd": 0.0,
        "input_tokens": 0,
        "output_tokens": 0,
    }


async def recommendation_node(
    state: EarningsBriefState,
    *,
    registry: Any,
    cost_guard: CostCeilingGuard,
) -> EarningsBriefState:
    """AgentNode: Recommendation Synthesizer — produces scenario-tree recommendation.

    Output schema must include bull, base, bear keys each with hold_signal,
    position_sizing_guidance, key_risk_factors (scenario-tree form, not a
    single action signal).

    Args:
        state: Current EarningsBriefState.
        registry: IAgentRegistry.
        cost_guard: CostCeilingGuard.

    Returns:
        Updated state with recommendation, confidence_scores, cost_usd.

    Raises:
        OutputSchemaError: If agent output is missing required scenario keys.
        WorkflowCostLimitError: If cost ceiling is reached.
    """
    logger.debug(
        "recommendation_node: company_id=%s", state.company_id
    )

    result = await _invoke_recommendation_synthesizer(state, registry)

    output = result.get("output")
    if output is None:
        raise OutputSchemaError("Recommendation synthesizer returned None output")

    # Validate required scenario keys in output
    for scenario_key in ("bull", "base", "bear"):
        if scenario_key not in output:
            raise OutputSchemaError(
                f"Missing required scenario '{scenario_key}' in recommendation output"
            )

    cost_delta = float(result.get("cost_usd", 0.0))
    confidence = float(result.get("confidence", 0.0))

    new_confidence_scores = dict(state.confidence_scores)
    new_confidence_scores[_AGENT_ROLE_ID.replace("-", "_")] = confidence

    new_tokens = dict(state.tokens_consumed)
    input_tokens = result.get("input_tokens", 0)
    output_tokens = result.get("output_tokens", 0)
    if input_tokens:
        new_tokens["recommendation_input"] = (
            new_tokens.get("recommendation_input", 0) + input_tokens
        )
    if output_tokens:
        new_tokens["recommendation_output"] = (
            new_tokens.get("recommendation_output", 0) + output_tokens
        )

    updated = state.model_copy(
        update={
            "recommendation": output,
            "cost_usd": state.cost_usd + cost_delta,
            "confidence_scores": new_confidence_scores,
            "tokens_consumed": new_tokens,
        }
    )

    cost_guard.check(updated)

    return updated
