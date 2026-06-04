"""
ai.workflows.on_demand.nodes.evaluate_quality — DeterministicNode (terminal quality gate).

Decision D9:
  overall_confidence = min(confidence_scores.values())
  >= 0.7  → COMPLETED
  0.4–0.69 → HIL_PENDING, requires_hil=True
  < 0.4   → BLOCKED

Raises EvaluateQualityError if confidence_scores is empty.
"""
from __future__ import annotations

from src.ai.workflows.errors import EvaluateQualityError
from src.ai.workflows.state import WorkflowState, WorkflowStatus

_HIL_THRESHOLD = 0.7
_BLOCK_THRESHOLD = 0.4

_HIL_REASON = "Confidence below auto-send threshold"
_BLOCK_REASON = "Confidence too low to deliver"


def evaluate_quality(state: WorkflowState) -> WorkflowState:
    """Compute overall_confidence and route to COMPLETED / HIL_PENDING / BLOCKED.

    Args:
        state: Current workflow state with confidence_scores populated.

    Returns:
        New WorkflowState with overall_confidence and status set.

    Raises:
        EvaluateQualityError: If confidence_scores is empty.
    """
    if not state.confidence_scores:
        raise EvaluateQualityError("No agent confidence scores recorded")

    overall = min(state.confidence_scores.values())

    if overall >= _HIL_THRESHOLD:
        return state.model_copy(
            update={
                "overall_confidence": overall,
                "status": WorkflowStatus.COMPLETED,
                "requires_hil": False,
                "hil_reason": None,
            }
        )

    if overall >= _BLOCK_THRESHOLD:
        return state.model_copy(
            update={
                "overall_confidence": overall,
                "status": WorkflowStatus.HIL_PENDING,
                "requires_hil": True,
                "hil_reason": _HIL_REASON,
            }
        )

    return state.model_copy(
        update={
            "overall_confidence": overall,
            "status": WorkflowStatus.BLOCKED,
            "requires_hil": False,
            "hil_reason": _BLOCK_REASON,
        }
    )
