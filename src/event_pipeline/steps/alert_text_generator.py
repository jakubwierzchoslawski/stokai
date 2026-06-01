"""AlertTextGenerator — template-based alert copy generation.

Architecture enforcement:
  C-001 — no LLM call here; template rendering stays within $0.05/event budget.
  Compliance — mandatory disclaimer always appended.

Single Responsibility: alert text composition only; no I/O.
"""
from __future__ import annotations

import os

from src.event_pipeline.pipeline_state import PipelineState

_DISCLAIMER = os.environ.get(
    "ALERT_DISCLAIMER",
    (
        "For informational purposes only. "
        "Not investment advice. Past analogues do not guarantee future outcomes."
    ),
)

_ALERT_TEMPLATE = """\
[{category}] Intensity: {intensity}/5 — {description}

Confidence: {confidence:.0%} | Supporting analogues: {sample_size}

{disclaimer}"""


class AlertTextGenerator:
    """Composes concise alert copy from pipeline state via template rendering.

    No LLM call; stays within Mode A $0.05/event budget (C-001).
    """

    def generate(self, state: PipelineState) -> str:
        """Return formatted alert text string.

        Parameters
        ----------
        state:
            Current pipeline state; must have category, intensity, confidence,
            event_description, and analogues populated.
        """
        category = state.category.value if state.category else "EVENT"
        intensity = state.intensity or 0
        description = state.event_description or "Geopolitical event detected"
        confidence = state.confidence or 0.0
        sample_size = len(state.analogues)

        return _ALERT_TEMPLATE.format(
            category=category,
            intensity=intensity,
            description=description,
            confidence=confidence,
            sample_size=sample_size,
            disclaimer=_DISCLAIMER,
        )
