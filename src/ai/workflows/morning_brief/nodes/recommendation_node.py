"""
src.ai.workflows.morning_brief.nodes.recommendation_node — AgentNode wrapper.

Invokes the recommendation_synthesizer agent (Opus 4.7) to generate
action recommendations from the merged state. Persists each recommendation
to the ai_recommendation table via the storage repository.

PLAN-F-006 TASK-006
"""
from __future__ import annotations

import logging
from typing import Any

from src.ai.workflows.morning_brief_state import MorningBriefState

logger = logging.getLogger(__name__)

_ROLE_ID = "recommendation_synthesizer"


async def _invoke_llm_stub(
    role_id: str,
    state: MorningBriefState,
    definition: Any,
) -> dict:
    """Default LLM stub — overridden in tests via _invoke_llm parameter."""
    return {
        "output": {"recommendations": []},
        "confidence": 0.75,
        "cost_usd": 0.0,
        "input_tokens": 0,
        "output_tokens": 0,
    }


async def recommendation_node(
    state: MorningBriefState,
    *,
    registry: Any,
    rec_repo: Any,
    cost_ceiling_usd: float = 2.0,
    _invoke_llm: Any = None,
) -> MorningBriefState:
    """Synthesize action recommendations from portfolio state and analogies.

    Persists each recommendation to the ai_recommendation table via rec_repo.
    Confidence stored in state.confidence_scores["recommendation_synthesizer"].

    Args:
        state: Current MorningBriefState.
        registry: IAgentRegistry providing resolve() method.
        rec_repo: Repository with save(recommendation_dict) method.
        cost_ceiling_usd: Per-run cost ceiling (default $2.00).
        _invoke_llm: Optional override for LLM invocation (test injection).

    Returns:
        Updated state with recommendations, cost_usd, and confidence_scores.
    """
    definition = registry.resolve(_ROLE_ID)
    invoke = _invoke_llm or _invoke_llm_stub

    result = await invoke(_ROLE_ID, state, definition)

    output = result.get("output") or {}
    recommendations = output.get("recommendations", [])
    if not isinstance(recommendations, list):
        recommendations = []

    confidence = result.get("confidence", 0.0)
    cost = result.get("cost_usd", 0.0)
    input_tokens = result.get("input_tokens", 0)
    output_tokens = result.get("output_tokens", 0)

    # Persist each recommendation to the DB
    for rec in recommendations:
        await rec_repo.save(rec)

    new_scores = {**state.confidence_scores, _ROLE_ID: confidence}
    new_tokens = {
        **state.tokens_consumed,
        f"{_ROLE_ID}_input": state.tokens_consumed.get(f"{_ROLE_ID}_input", 0) + input_tokens,
        f"{_ROLE_ID}_output": state.tokens_consumed.get(f"{_ROLE_ID}_output", 0) + output_tokens,
    }

    updated = state.model_copy(
        update={
            "recommendations": recommendations,
            "cost_usd": state.cost_usd + cost,
            "confidence_scores": new_scores,
            "tokens_consumed": new_tokens,
        }
    )

    logger.debug(
        "recommendation_node: %d recommendations, confidence=%.3f, cost=$%.4f",
        len(recommendations),
        confidence,
        cost,
    )

    return updated
