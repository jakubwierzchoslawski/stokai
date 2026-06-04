"""
src.ai.workflows.morning_brief.nodes.evaluate_quality_node — AgentNode wrapper.

Tier 1 LLM-as-judge gate (§9). Always the second-to-last node.

Invokes the evaluate_quality agent (Opus 4.7) using quality_judge.md prompt.
Computes workflow_confidence = min(state.confidence_scores.values()).
Sets confidence_route driving the conditional edge: auto-send / HIL / block.

PLAN-F-006 TASK-007
"""
from __future__ import annotations

import logging
from typing import Any

from src.ai.workflows.morning_brief_state import ConfidenceRoute, MorningBriefState

logger = logging.getLogger(__name__)

_ROLE_ID = "evaluate_quality"
_AUTO_SEND_THRESHOLD = 0.70
_HIL_THRESHOLD = 0.40


def _get_langfuse() -> Any:  # pragma: no cover
    """Return Langfuse client; lazy import to avoid hard dependency in tests."""
    try:
        from langfuse import Langfuse
        return Langfuse()
    except Exception:
        return None


async def _invoke_llm_stub(
    role_id: str,
    state: MorningBriefState,
    definition: Any,
) -> dict:
    """Default LLM stub — overridden in tests via _invoke_llm parameter."""
    return {
        "output": {"quality_score": 0.80, "rationale": "stub"},
        "confidence": 0.80,
        "cost_usd": 0.0,
        "input_tokens": 0,
        "output_tokens": 0,
    }


async def evaluate_quality_node(
    state: MorningBriefState,
    *,
    registry: Any,
    cost_ceiling_usd: float = 2.0,
    _invoke_llm: Any = None,
) -> MorningBriefState:
    """LLM-as-judge gate: second-to-last node in the workflow.

    Computes workflow_confidence = min(confidence_scores.values()).
    Routes to: AUTO_SEND (>= 0.70), HIL (0.40-0.69), BLOCK (< 0.40).
    Writes a Langfuse score linked to the producing trace.

    Args:
        state: Current MorningBriefState.
        registry: IAgentRegistry providing resolve() method.
        cost_ceiling_usd: Per-run cost ceiling (default $2.00).
        _invoke_llm: Optional override for LLM invocation (test injection).

    Returns:
        Updated state with confidence_route, requires_hil, and confidence_scores.
    """
    definition = registry.resolve(_ROLE_ID)
    invoke = _invoke_llm or _invoke_llm_stub

    result = await invoke(_ROLE_ID, state, definition)

    judge_confidence = result.get("confidence", 0.0)
    cost = result.get("cost_usd", 0.0)
    input_tokens = result.get("input_tokens", 0)
    output_tokens = result.get("output_tokens", 0)

    # Add judge's own score to confidence_scores before computing minimum
    new_scores = {**state.confidence_scores, _ROLE_ID: judge_confidence}

    # workflow_confidence = minimum across ALL agent scores (including judge)
    workflow_confidence = min(new_scores.values()) if new_scores else 0.0

    # Determine routing
    if workflow_confidence >= _AUTO_SEND_THRESHOLD:
        confidence_route = ConfidenceRoute.AUTO_SEND
        requires_hil = False
        hil_reason = None
    elif workflow_confidence >= _HIL_THRESHOLD:
        confidence_route = ConfidenceRoute.HIL
        requires_hil = True
        hil_reason = f"Confidence {workflow_confidence:.3f} in HIL range [0.40, 0.70)"
    else:
        confidence_route = ConfidenceRoute.BLOCK
        requires_hil = True
        hil_reason = f"Confidence {workflow_confidence:.3f} below block threshold 0.40"

    # Write Langfuse score linked to the producing trace
    langfuse = _get_langfuse()
    if langfuse is not None and state.langfuse_trace_id:
        try:
            langfuse.score(
                trace_id=state.langfuse_trace_id,
                name="workflow_confidence",
                value=workflow_confidence,
                comment=f"evaluate_quality judge score: {judge_confidence:.3f}",
            )
        except Exception as exc:
            logger.warning(
                "evaluate_quality_node: failed to write Langfuse score — %s", exc
            )

    new_tokens = {
        **state.tokens_consumed,
        f"{_ROLE_ID}_input": state.tokens_consumed.get(f"{_ROLE_ID}_input", 0) + input_tokens,
        f"{_ROLE_ID}_output": state.tokens_consumed.get(f"{_ROLE_ID}_output", 0) + output_tokens,
    }

    updated = state.model_copy(
        update={
            "confidence_scores": new_scores,
            "confidence_route": confidence_route,
            "requires_hil": requires_hil,
            "hil_reason": hil_reason,
            "cost_usd": state.cost_usd + cost,
            "tokens_consumed": new_tokens,
        }
    )

    logger.info(
        "evaluate_quality_node: workflow_confidence=%.3f, route=%s, judge_score=%.3f",
        workflow_confidence,
        confidence_route.value,
        judge_confidence,
    )

    return updated
