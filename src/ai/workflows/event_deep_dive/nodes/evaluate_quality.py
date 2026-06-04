"""
ai.workflows.event_deep_dive.nodes.evaluate_quality — DeterministicNode.

Computes workflow_confidence = min(confidence_scores.values()).
Writes confidence_scores["workflow"].
Sets requires_hil for the 0.4–0.69 range.
Sets cost_limited from state.cost_limited (populated by CostAccumulator).

PLAN-F-010 TASK-008.
"""
from __future__ import annotations

import logging

from src.ai.workflows.event_deep_dive.state import DeepDiveWorkflowState

logger = logging.getLogger(__name__)

# Confidence thresholds (Architecture §D9)
_AUTO_STORE_THRESHOLD = 0.70   # >= 0.70 → auto_store
_HIL_LOWER_BOUND = 0.40        # 0.40–0.69 → hil_queue; < 0.40 → blocked


def evaluate_quality(state: DeepDiveWorkflowState) -> DeepDiveWorkflowState:
    """Compute workflow confidence and set routing flags.

    Takes the minimum of all per-agent confidence_scores as the overall
    workflow confidence.  Writes confidence_scores["workflow"].  Sets
    requires_hil=True for the mid-confidence band (0.4–0.69).

    Args:
        state: DeepDiveWorkflowState after all AgentNodes have run.

    Returns:
        Updated state with confidence_scores["workflow"] set and
        requires_hil / cost_limited fields refreshed.
    """
    scores = {k: v for k, v in state.confidence_scores.items() if k != "workflow"}

    if scores:
        workflow_confidence = min(scores.values())
    else:
        workflow_confidence = 0.0

    requires_hil = _HIL_LOWER_BOUND <= workflow_confidence < _AUTO_STORE_THRESHOLD

    new_scores = {**state.confidence_scores, "workflow": workflow_confidence}

    logger.info(
        "evaluate_quality: workflow_confidence=%.3f requires_hil=%s cost_limited=%s",
        workflow_confidence,
        requires_hil,
        state.cost_limited,
    )

    return state.model_copy(
        update={
            "confidence_scores": new_scores,
            "requires_hil": requires_hil,
            "cost_limited": state.cost_limited,
        }
    )
