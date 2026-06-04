"""
src.ai.workflows.morning_brief.nodes.narrative_writer_node — AgentNode wrapper.

Always the last AgentNode in the workflow. Invokes the narrative_writer agent
(Opus 4.7) to produce HTML email body in state.report.

Only runs when confidence routing directed to narrative_writer (AUTO_SEND or
HIL-approved path). Does NOT run on BLOCK path.

PLAN-F-006 TASK-009
"""
from __future__ import annotations

import logging
from typing import Any

from src.ai.workflows.morning_brief_state import ConfidenceRoute, MorningBriefState

logger = logging.getLogger(__name__)

_ROLE_ID = "narrative_writer"


async def _invoke_llm_stub(
    role_id: str,
    state: MorningBriefState,
    definition: Any,
) -> dict:
    """Default LLM stub — overridden in tests via _invoke_llm parameter."""
    return {
        "output": {"report": "<html><body><p>Morning Brief</p></body></html>"},
        "confidence": 0.85,
        "cost_usd": 0.0,
        "input_tokens": 0,
        "output_tokens": 0,
    }


async def narrative_writer_node(
    state: MorningBriefState,
    *,
    registry: Any,
    cost_ceiling_usd: float = 2.0,
    _invoke_llm: Any = None,
) -> MorningBriefState:
    """Compose the final narrative HTML brief.

    Only invokes the agent when state.confidence_route is AUTO_SEND or HIL
    (i.e., not on BLOCK path). Uses "FT columnist voice, not AI assistant voice"
    persona (§7.2).

    Args:
        state: Current MorningBriefState.
        registry: IAgentRegistry providing resolve() method.
        cost_ceiling_usd: Per-run cost ceiling (default $2.00).
        _invoke_llm: Optional override for LLM invocation (test injection).

    Returns:
        Updated state with report (HTML string) populated, or unchanged on BLOCK.
    """
    # Guard: do not invoke on BLOCK path
    if state.confidence_route == ConfidenceRoute.BLOCK:
        logger.debug(
            "narrative_writer_node: skipping — confidence_route=BLOCK for workflow_id=%s",
            state.workflow_id,
        )
        return state

    definition = registry.resolve(_ROLE_ID)
    invoke = _invoke_llm or _invoke_llm_stub

    result = await invoke(_ROLE_ID, state, definition)

    output = result.get("output") or {}
    report = output.get("report") or output.get("html") or str(output)

    confidence = result.get("confidence", 0.0)
    cost = result.get("cost_usd", 0.0)
    input_tokens = result.get("input_tokens", 0)
    output_tokens = result.get("output_tokens", 0)

    new_scores = {**state.confidence_scores, _ROLE_ID: confidence}
    new_tokens = {
        **state.tokens_consumed,
        f"{_ROLE_ID}_input": state.tokens_consumed.get(f"{_ROLE_ID}_input", 0) + input_tokens,
        f"{_ROLE_ID}_output": state.tokens_consumed.get(f"{_ROLE_ID}_output", 0) + output_tokens,
    }

    updated = state.model_copy(
        update={
            "report": report,
            "cost_usd": state.cost_usd + cost,
            "confidence_scores": new_scores,
            "tokens_consumed": new_tokens,
        }
    )

    logger.debug(
        "narrative_writer_node: report generated, len=%d, confidence=%.3f",
        len(report),
        confidence,
    )

    return updated
