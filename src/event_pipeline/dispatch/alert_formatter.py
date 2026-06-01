"""AlertFormatter — produces AlertPayload from PipelineState.

Architecture enforcement:
  Single Responsibility — formats alert data only; no I/O.
  AC-001 — confidence, sample_size, and disclaimer always attached per spec.

A disclaimer is mandatory per compliance requirements (ARCHITECTURE.md §14).
"""
from __future__ import annotations

from pydantic import BaseModel

from src.event_pipeline.pipeline_state import PipelineState

_DISCLAIMER = (
    "This is an automated alert for informational purposes only. "
    "It does not constitute investment advice or a recommendation to buy or sell securities. "
    "Past analogues do not guarantee future outcomes."
)


class AlertPayload(BaseModel):
    """Structured alert ready for dispatch."""

    raw_event_id: str
    tenant_id: str
    category: str | None
    intensity: int | None
    confidence: float | None
    sample_size: int
    alert_text: str
    disclaimer: str
    route: str | None


class AlertFormatter:
    """Composes an ``AlertPayload`` from the current ``PipelineState``.

    Single Responsibility: data transformation only; no I/O.
    """

    def format(self, state: PipelineState) -> AlertPayload:
        """Return an AlertPayload for the given state."""
        return AlertPayload(
            raw_event_id=str(state.raw_event_id),
            tenant_id=str(state.tenant_id),
            category=state.category.value if state.category else None,
            intensity=state.intensity,
            confidence=state.confidence,
            sample_size=len(state.analogues),
            alert_text=state.alert_text or "",
            disclaimer=_DISCLAIMER,
            route=state.route.value if state.route else None,
        )
