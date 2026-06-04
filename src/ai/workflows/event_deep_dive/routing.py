"""
ai.workflows.event_deep_dive.routing — Conditional edge routing functions.

route_after_evaluate is the LangGraph conditional edge called after
evaluate_quality completes.  It reads confidence_scores["workflow"] and
returns the next node name.

Decision thresholds (Architecture §D9):
  confidence >= 0.70 → "auto_store"
  0.40 <= confidence < 0.70 → "hil_queue"
  confidence < 0.40 → "blocked"

PLAN-F-010 TASK-008.
"""
from __future__ import annotations

import logging
from typing import Literal

from src.ai.workflows.event_deep_dive.state import DeepDiveWorkflowState

logger = logging.getLogger(__name__)

_AUTO_STORE_THRESHOLD = 0.70
_HIL_LOWER_BOUND = 0.40


def route_after_evaluate(
    state: DeepDiveWorkflowState,
) -> Literal["auto_store", "hil_queue", "blocked"]:
    """LangGraph conditional edge after evaluate_quality.

    Reads state.confidence_scores["workflow"] (written by evaluate_quality)
    and returns the destination node name.

    Args:
        state: DeepDiveWorkflowState after evaluate_quality has run.

    Returns:
        "auto_store"  — confidence >= 0.70
        "hil_queue"   — 0.40 <= confidence < 0.70
        "blocked"     — confidence < 0.40
    """
    workflow_confidence = state.confidence_scores.get("workflow", 0.0)

    if workflow_confidence >= _AUTO_STORE_THRESHOLD:
        route = "auto_store"
    elif workflow_confidence >= _HIL_LOWER_BOUND:
        route = "hil_queue"
    else:
        route = "blocked"

    logger.info(
        "route_after_evaluate: workflow_confidence=%.3f → %s",
        workflow_confidence,
        route,
    )
    return route
