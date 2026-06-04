"""
src.ai.workflows.morning_brief.nodes.historical_context_node — AgentNode wrapper.

Invokes the historical_context_agent (Opus 4.7) in parallel for each event in
state.relevant_events using asyncio.gather. Overall confidence = minimum across
all parallel invocations.

Creates one Langfuse child span per parallel invocation (REQ-N-008).

PLAN-F-006 TASK-005
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from src.ai.workflows.morning_brief_state import MorningBriefState

logger = logging.getLogger(__name__)

_ROLE_ID = "historical_context_agent"
_COST_WARNING_THRESHOLD = 0.80


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
        "output": {"analogies": []},
        "confidence": 0.80,
        "cost_usd": 0.0,
        "input_tokens": 0,
        "output_tokens": 0,
    }


async def _invoke_for_event(
    event: dict,
    state: MorningBriefState,
    definition: Any,
    invoke: Any,
    langfuse: Any,
) -> tuple[str, list, float, float]:
    """Invoke historical_context_agent for a single event.

    Returns (event_id, analogies, confidence, cost_usd).
    """
    event_id = str(event.get("event_id", "unknown"))

    # Create Langfuse child span for this invocation
    if langfuse is not None and state.langfuse_trace_id:
        langfuse.span(
            name=f"historical_context/{event_id}",
            trace_id=state.langfuse_trace_id,
        )

    result = await invoke(_ROLE_ID, state, definition)
    output = result.get("output") or {}
    analogies = output.get("analogies", [])
    if not isinstance(analogies, list):
        analogies = []

    return (
        event_id,
        analogies,
        result.get("confidence", 0.0),
        result.get("cost_usd", 0.0),
    )


async def historical_context_node(
    state: MorningBriefState,
    *,
    registry: Any,
    cost_ceiling_usd: float = 2.0,
    _invoke_llm: Any = None,
) -> MorningBriefState:
    """Find historical analogies for each relevant event in parallel.

    Uses asyncio.gather to invoke historical_context_agent in parallel.
    Overall confidence = minimum across all invocations (fail-safe).

    If total accumulated cost > cost_ceiling_usd * 0.80 after this node,
    logs WARNING (budget approaching; caller should reduce remaining budgets).

    Args:
        state: Current MorningBriefState (relevant_events must be populated).
        registry: IAgentRegistry providing resolve() method.
        cost_ceiling_usd: Per-run cost ceiling (default $2.00).
        _invoke_llm: Optional override for LLM invocation (test injection).

    Returns:
        Updated state with analogies dict, cost_usd, and confidence_scores.
    """
    if not state.relevant_events:
        logger.debug("historical_context_node: no relevant events; skipping")
        return state

    definition = registry.resolve(_ROLE_ID)
    invoke = _invoke_llm or _invoke_llm_stub
    langfuse = _get_langfuse()

    tasks = [
        _invoke_for_event(event, state, definition, invoke, langfuse)
        for event in state.relevant_events
    ]

    results = await asyncio.gather(*tasks)

    analogies: dict = {}
    confidences: list[float] = []
    total_cost = 0.0
    total_input_tokens = 0
    total_output_tokens = 0

    for event_id, event_analogies, confidence, cost in results:
        analogies[event_id] = event_analogies
        confidences.append(confidence)
        total_cost += cost

    overall_confidence = min(confidences) if confidences else 0.0

    new_scores = {**state.confidence_scores, _ROLE_ID: overall_confidence}
    new_tokens = {
        **state.tokens_consumed,
    }

    accumulated_cost = state.cost_usd + total_cost
    if cost_ceiling_usd > 0 and accumulated_cost / cost_ceiling_usd >= _COST_WARNING_THRESHOLD:
        logger.warning(
            "historical_context_node: accumulated cost $%.4f is %.0f%% of ceiling $%.2f "
            "for workflow_id=%s — consider reducing remaining agent token budgets",
            accumulated_cost,
            (accumulated_cost / cost_ceiling_usd) * 100,
            cost_ceiling_usd,
            state.workflow_id,
        )

    updated = state.model_copy(
        update={
            "analogies": analogies,
            "cost_usd": accumulated_cost,
            "confidence_scores": new_scores,
            "tokens_consumed": new_tokens,
        }
    )

    logger.debug(
        "historical_context_node: %d analogies sets, min_confidence=%.3f, total_cost=$%.4f",
        len(analogies),
        overall_confidence,
        total_cost,
    )

    return updated
