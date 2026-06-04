"""
src.ai.workflows.morning_brief.nodes.anomaly_detector_node — AgentNode wrapper.

Invokes the anomaly_detector agent (Sonnet 4.6) to identify unusual score
movements in state.score_changes. Accumulates cost and confidence.

PLAN-F-006 TASK-004
"""
from __future__ import annotations

import logging
from typing import Any

from src.ai.workflows.morning_brief_state import MorningBriefState
from src.ai.workflows.morning_brief.nodes.relevance_analyst_node import LimitExceededError

logger = logging.getLogger(__name__)

_ROLE_ID = "anomaly_detector"


async def _invoke_llm_stub(
    role_id: str,
    state: MorningBriefState,
    definition: Any,
) -> dict:
    """Default LLM stub — overridden in tests via _invoke_llm parameter."""
    return {
        "output": {"anomalies": []},
        "confidence": 0.80,
        "cost_usd": 0.0,
        "input_tokens": 0,
        "output_tokens": 0,
    }


async def anomaly_detector_node(
    state: MorningBriefState,
    *,
    registry: Any,
    cost_ceiling_usd: float = 2.0,
    _invoke_llm: Any = None,
) -> MorningBriefState:
    """Detect statistical anomalies in score changes and events.

    Invokes the anomaly_detector agent. On LimitExceededError, sets
    state.requires_hil=True and returns without raising.

    Args:
        state: Current MorningBriefState.
        registry: IAgentRegistry providing resolve() method.
        cost_ceiling_usd: Per-run cost ceiling (default $2.00).
        _invoke_llm: Optional override for LLM invocation (test injection).

    Returns:
        Updated state with anomalies, cost_usd, and confidence_scores.
    """
    definition = registry.resolve(_ROLE_ID)
    invoke = _invoke_llm or _invoke_llm_stub

    try:
        result = await invoke(_ROLE_ID, state, definition)
    except LimitExceededError as exc:
        logger.warning(
            "anomaly_detector_node: LimitExceededError — %s; routing to HIL",
            exc.reason,
        )
        return state.model_copy(
            update={
                "requires_hil": True,
                "hil_reason": f"budget_exceeded: {exc.reason}",
            }
        )

    output = result.get("output") or {}
    anomalies = output.get("anomalies", [])
    if not isinstance(anomalies, list):
        anomalies = []

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
            "anomalies": anomalies,
            "cost_usd": state.cost_usd + cost,
            "confidence_scores": new_scores,
            "tokens_consumed": new_tokens,
        }
    )

    logger.debug(
        "anomaly_detector_node: %d anomalies, confidence=%.3f, cost=$%.4f",
        len(anomalies),
        confidence,
        cost,
    )

    return updated
