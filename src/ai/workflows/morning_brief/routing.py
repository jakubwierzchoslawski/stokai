"""
src.ai.workflows.morning_brief.routing — confidence_router conditional edge.

LangGraph conditional edge function called after evaluate_quality_node.

Routing thresholds (§7.7 Confidence Model D9):
  >= 0.70  → "narrative_writer"  (auto-send)
  >= 0.40  → "hil_queue"         (human-in-the-loop)
  < 0.40   → "block_and_log"     (blocked; no email)

PLAN-F-006 TASK-008
"""
from __future__ import annotations

from src.ai.workflows.morning_brief_state import MorningBriefState

_AUTO_SEND_THRESHOLD = 0.70
_HIL_THRESHOLD = 0.40


def confidence_router(state: MorningBriefState) -> str:
    """LangGraph conditional edge router from evaluate_quality_node.

    Computes the minimum confidence score across all agent nodes and routes:
      >= 0.70  → "narrative_writer"  (auto-send path)
      >= 0.40  → "hil_queue"         (human-in-the-loop path)
      < 0.40   → "block_and_log"     (blocked — confidence too low)

    An empty confidence_scores dict is treated as overall confidence 0.0 and
    routes to block_and_log (fail-safe).

    Args:
        state: Current MorningBriefState from the evaluate_quality node.

    Returns:
        Node name string for LangGraph conditional edge routing.
    """
    overall = min(state.confidence_scores.values()) if state.confidence_scores else 0.0

    if overall >= _AUTO_SEND_THRESHOLD:
        return "narrative_writer"
    elif overall >= _HIL_THRESHOLD:
        return "hil_queue"
    else:
        return "block_and_log"
