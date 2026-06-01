"""Step 10: ROUTING — confidence-threshold routing (C-003).

Architecture enforcement:
  C-003 — auto_send >= 0.7; hil_queue >= 0.4; blocked < 0.4.
  P-06 12-Factor — thresholds configurable via environment variables.

Single Responsibility: pure routing logic only — no I/O.
"""
from __future__ import annotations

import logging
import os

from src.event_pipeline.pipeline_state import AlertRoute, PipelineState

logger = logging.getLogger(__name__)

# Default thresholds from C-003; overridable via env vars for operator tuning.
_DEFAULT_AUTO_SEND_THRESHOLD = 0.7
_DEFAULT_HIL_THRESHOLD = 0.4


class RoutingStep:
    """Pipeline Step 10: ROUTING.

    Applies the C-003 confidence routing rule:
      confidence >= AUTO_SEND_THRESHOLD  → AUTO_SEND
      confidence >= HIL_THRESHOLD        → HIL_QUEUE
      else                               → BLOCKED

    This step is a pure function — no I/O; no injected collaborators.
    Thresholds are read from environment variables at construction time.
    """

    step_name: str = "s10_routing"

    def __init__(self) -> None:
        self._auto_send_threshold = float(
            os.environ.get("AUTO_SEND_THRESHOLD", _DEFAULT_AUTO_SEND_THRESHOLD)
        )
        self._hil_threshold = float(
            os.environ.get("HIL_THRESHOLD", _DEFAULT_HIL_THRESHOLD)
        )

    async def execute(self, state: PipelineState) -> PipelineState:
        """Determine the alert route from the confidence score."""
        confidence = state.confidence or 0.0

        if confidence >= self._auto_send_threshold:
            route = AlertRoute.AUTO_SEND
        elif confidence >= self._hil_threshold:
            route = AlertRoute.HIL_QUEUE
        else:
            route = AlertRoute.BLOCKED

        logger.info(
            "Step 10 (ROUTING): raw_event_id=%s confidence=%.3f route=%s",
            state.raw_event_id,
            confidence,
            route.value,
        )

        return state.model_copy(update={"route": route})
