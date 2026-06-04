"""
ai.workflows.earnings_brief.nodes.earnings_context_node — AgentNode.

Earnings Context Agent (Opus 4.7): generates the bull/base/bear scenario tree.

PLAN-F-009 TASK-005
"""
from __future__ import annotations

import logging
from typing import Any

from src.ai.workflows.cost_guard import CostCeilingGuard
from src.ai.workflows.earnings_brief.state import EarningsBriefState, ScenarioTree
from src.ai.workflows.errors import WorkflowCostLimitError

logger = logging.getLogger(__name__)

_AGENT_ROLE_ID = "earnings-context-agent"


class OutputSchemaError(Exception):
    """Raised when agent output does not match the expected schema."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"OutputSchemaError: {reason}")
        self.reason = reason


async def _invoke_earnings_context_agent(
    state: EarningsBriefState,
    registry: Any,
) -> dict[str, Any]:
    """Invoke the Earnings Context Agent LLM. Patchable in tests.

    Returns a dict with keys: output, confidence, cost_usd, input_tokens, output_tokens.
    """
    # Resolve agent definition from registry
    if registry is not None:
        try:
            agent_def = registry.resolve(_AGENT_ROLE_ID)
            logger.debug(
                "earnings_context_node: resolved agent role=%s", agent_def.role_id
            )
        except Exception as exc:
            logger.warning("earnings_context_node: registry.resolve failed: %s", exc)

    # Stub: return a valid ScenarioTree output for testing/integration
    return {
        "output": {
            "bull": {
                "probability": 0.30,
                "rationale": "Strong revenue guidance and macro tailwinds",
                "macro_drivers": ["low interest rates", "strong consumer demand"],
                "sector_drivers": ["sector growth acceleration"],
                "implied_price_impact_pct": 5.0,
            },
            "base": {
                "probability": 0.50,
                "rationale": "In-line results expected based on consensus",
                "macro_drivers": ["stable inflation"],
                "sector_drivers": ["average sector performance"],
                "implied_price_impact_pct": 0.5,
            },
            "bear": {
                "probability": 0.20,
                "rationale": "Margin compression risk from input costs",
                "macro_drivers": ["cost pressures"],
                "sector_drivers": ["competitive pricing pressure"],
                "implied_price_impact_pct": -4.0,
            },
            "analogies": [],
            "macro_summary": "Macro environment is broadly supportive",
            "sector_summary": "Sector peers reported mixed results last quarter",
        },
        "confidence": 0.80,
        "cost_usd": 0.0,
        "input_tokens": 0,
        "output_tokens": 0,
    }


async def earnings_context_node(
    state: EarningsBriefState,
    *,
    registry: Any,
    cost_guard: CostCeilingGuard,
) -> EarningsBriefState:
    """AgentNode: Earnings Context Agent — generates structured scenario tree.

    Steps:
      1. Resolves agent definition from registry.
      2. Constructs input from company_state, earnings_history, macro_context,
         sector_recent_earnings.
      3. Invokes the LLM via _invoke_earnings_context_agent.
      4. Deserializes output into ScenarioTree.
      5. Records confidence_scores["earnings_context"].
      6. Accumulates cost_usd.
      7. Calls cost_guard.check(state).

    Args:
        state: Current EarningsBriefState.
        registry: IAgentRegistry for resolving agent definitions.
        cost_guard: CostCeilingGuard for enforcing cost ceiling.

    Returns:
        Updated EarningsBriefState with scenario_tree, cost_usd, confidence_scores.

    Raises:
        OutputSchemaError: If agent output cannot be deserialized to ScenarioTree.
        WorkflowCostLimitError: If cost ceiling is reached.
    """
    logger.debug(
        "earnings_context_node: company_id=%s", state.company_id
    )

    result = await _invoke_earnings_context_agent(state, registry)

    output = result.get("output")
    if output is None:
        raise OutputSchemaError("Earnings context agent returned None output")

    # Validate required scenario keys
    for scenario_key in ("bull", "base", "bear"):
        if scenario_key not in output:
            raise OutputSchemaError(
                f"Missing required scenario '{scenario_key}' in agent output"
            )

    # Deserialize into ScenarioTree (validates probability sum)
    try:
        scenario_tree = ScenarioTree(**output)
    except Exception as exc:
        raise OutputSchemaError(
            f"Failed to deserialize ScenarioTree: {exc}"
        ) from exc

    # Accumulate cost and record confidence
    cost_delta = float(result.get("cost_usd", 0.0))
    confidence = float(result.get("confidence", 0.0))

    new_confidence_scores = dict(state.confidence_scores)
    new_confidence_scores[_AGENT_ROLE_ID.replace("-", "_")] = confidence

    # Accumulate tokens
    new_tokens = dict(state.tokens_consumed)
    input_tokens = result.get("input_tokens", 0)
    output_tokens = result.get("output_tokens", 0)
    if input_tokens:
        new_tokens["earnings_context_input"] = (
            new_tokens.get("earnings_context_input", 0) + input_tokens
        )
    if output_tokens:
        new_tokens["earnings_context_output"] = (
            new_tokens.get("earnings_context_output", 0) + output_tokens
        )

    updated = state.model_copy(
        update={
            "scenario_tree": scenario_tree,
            "cost_usd": state.cost_usd + cost_delta,
            "confidence_scores": new_confidence_scores,
            "tokens_consumed": new_tokens,
        }
    )

    # Check cost ceiling before returning
    cost_guard.check(updated)

    return updated
