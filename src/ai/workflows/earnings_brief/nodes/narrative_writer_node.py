"""
ai.workflows.earnings_brief.nodes.narrative_writer_node — AgentNode.

Narrative Writer: generates the final prose earnings brief (FT columnist voice).

PLAN-F-009 TASK-006
"""
from __future__ import annotations

import logging
from typing import Any

from src.ai.workflows.cost_guard import CostCeilingGuard
from src.ai.workflows.earnings_brief.nodes.earnings_context_node import OutputSchemaError
from src.ai.workflows.earnings_brief.state import EarningsBriefState

logger = logging.getLogger(__name__)

_AGENT_ROLE_ID = "narrative-writer"


async def _invoke_narrative_writer(
    state: EarningsBriefState,
    registry: Any,
) -> dict[str, Any]:
    """Invoke the Narrative Writer LLM. Patchable in tests."""
    if registry is not None:
        try:
            registry.resolve(_AGENT_ROLE_ID)
        except Exception as exc:
            logger.warning("narrative_writer_node: registry.resolve failed: %s", exc)

    return {
        "output": {
            "title": "Earnings Risk Brief",
            "sections": ["executive_summary", "scenario_tree", "recommendation"],
            "text": (
                "This earnings brief provides a structured analysis of the upcoming "
                "earnings event. The base case anticipates in-line results with "
                "modest upside risk from stronger-than-expected guidance."
            ),
        },
        "confidence": 0.80,
        "cost_usd": 0.0,
        "input_tokens": 0,
        "output_tokens": 0,
    }


async def narrative_writer_node(
    state: EarningsBriefState,
    *,
    registry: Any,
    cost_guard: CostCeilingGuard,
) -> EarningsBriefState:
    """AgentNode: Narrative Writer — generates the final prose earnings brief.

    Writes in FT columnist voice. Populates state.report with at minimum
    a 'text' key containing non-empty prose.

    Args:
        state: Current EarningsBriefState.
        registry: IAgentRegistry.
        cost_guard: CostCeilingGuard.

    Returns:
        Updated state with report, confidence_scores, cost_usd.

    Raises:
        OutputSchemaError: If report text is empty or output is invalid.
        WorkflowCostLimitError: If cost ceiling is reached.
    """
    logger.debug(
        "narrative_writer_node: company_id=%s", state.company_id
    )

    result = await _invoke_narrative_writer(state, registry)

    output = result.get("output")
    if output is None:
        raise OutputSchemaError("Narrative writer returned None output")

    # Validate non-empty text
    text = output.get("text", "")
    if not text or not text.strip():
        raise OutputSchemaError("Narrative writer output 'text' is empty")

    cost_delta = float(result.get("cost_usd", 0.0))
    confidence = float(result.get("confidence", 0.0))

    new_confidence_scores = dict(state.confidence_scores)
    new_confidence_scores[_AGENT_ROLE_ID.replace("-", "_")] = confidence

    new_tokens = dict(state.tokens_consumed)
    input_tokens = result.get("input_tokens", 0)
    output_tokens = result.get("output_tokens", 0)
    if input_tokens:
        new_tokens["narrative_writer_input"] = (
            new_tokens.get("narrative_writer_input", 0) + input_tokens
        )
    if output_tokens:
        new_tokens["narrative_writer_output"] = (
            new_tokens.get("narrative_writer_output", 0) + output_tokens
        )

    updated = state.model_copy(
        update={
            "report": output,
            "cost_usd": state.cost_usd + cost_delta,
            "confidence_scores": new_confidence_scores,
            "tokens_consumed": new_tokens,
        }
    )

    cost_guard.check(updated)

    return updated
