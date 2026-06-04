"""
ai.workflows.earnings_brief.nodes.evaluate_quality — DeterministicNode.

Quality gate: computes overall confidence and routes per D9.

PLAN-F-009 TASK-007
"""
from __future__ import annotations

import logging

from src.ai.workflows.earnings_brief.state import EarningsBriefState
from src.ai.workflows.errors import EvaluateQualityError
from src.ai.workflows.state import WorkflowStatus

logger = logging.getLogger(__name__)

_AUTO_SEND_THRESHOLD = 0.70
_HIL_THRESHOLD = 0.40


def evaluate_quality(state: EarningsBriefState) -> EarningsBriefState:
    """DeterministicNode: compute overall confidence and route per D9.

    Decision (Architecture D9):
      overall_confidence >= 0.70  → COMPLETED, requires_hil=False
      0.40 <= overall_confidence < 0.70 → HIL_PENDING, requires_hil=True
      overall_confidence < 0.40  → BLOCKED, requires_hil=False

    Uses the MINIMUM of all agent confidence scores (fail-safe).

    Args:
        state: Current EarningsBriefState.

    Returns:
        Updated state with overall_confidence, status, requires_hil, hil_reason.

    Raises:
        EvaluateQualityError: If confidence_scores is empty.
    """
    if not state.confidence_scores:
        raise EvaluateQualityError("No agent confidence scores recorded")

    overall = min(state.confidence_scores.values())

    if overall >= _AUTO_SEND_THRESHOLD:
        new_status = WorkflowStatus.COMPLETED
        requires_hil = False
        hil_reason = None
    elif overall >= _HIL_THRESHOLD:
        new_status = WorkflowStatus.HIL_PENDING
        requires_hil = True
        hil_reason = "Confidence below auto-send threshold"
    else:
        new_status = WorkflowStatus.BLOCKED
        requires_hil = False
        hil_reason = "Confidence too low to deliver"

    logger.debug(
        "evaluate_quality: overall_confidence=%.3f status=%s requires_hil=%s",
        overall,
        new_status,
        requires_hil,
    )

    return state.model_copy(
        update={
            "overall_confidence": overall,
            "status": new_status,
            "requires_hil": requires_hil,
            "hil_reason": hil_reason,
        }
    )
