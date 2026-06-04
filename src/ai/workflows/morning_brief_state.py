"""
ai.workflows.morning_brief_state — MorningBriefState, ConfidenceRoute, and confidence_router.

State model and routing logic for the Morning Brief workflow (PLAN-F-006).

The confidence_router is used as a LangGraph conditional edge from evaluate_quality:
  >= 0.70  → narrative_writer  (auto-send)
  >= 0.40  → hil_queue         (human-in-the-loop)
  < 0.40   → block_and_log     (blocked, no send)

PLAN-F-006 TASK-001
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field


class ConfidenceRoute(str, Enum):
    """Routing decision for a morning brief based on overall confidence."""

    AUTO_SEND = "auto_send"
    HIL = "hil"
    BLOCK = "block"


class MorningBriefState(BaseModel):
    """LangGraph state model for the Morning Brief workflow.

    Passed through all workflow nodes and used as the LangGraph state and the
    serialisation format for the workflow_run.final_state JSONB column.
    """

    workflow_id: UUID
    workflow_type: str = "morning_brief"
    tenant_id: UUID
    user_id: UUID
    started_at: datetime

    # DeterministicNode outputs
    portfolio_state: dict | None = None
    events: list[dict] = Field(default_factory=list)
    relevant_events: list[dict] = Field(default_factory=list)
    score_changes: list[dict] = Field(default_factory=list)
    anomalies: list[dict] = Field(default_factory=list)
    analogies: dict = Field(default_factory=dict)

    # AgentNode outputs
    recommendations: list[dict] = Field(default_factory=list)
    report: str | None = None

    # Confidence tracking
    confidence_scores: dict[str, float] = Field(default_factory=dict)
    requires_hil: bool = False
    hil_reason: str | None = None

    # Cost tracking
    cost_usd: float = 0.0

    # Observability
    langfuse_trace_id: str | None = None

    # Routing / lifecycle
    confidence_route: ConfidenceRoute | None = None
    brief_id: UUID | None = None
    dispatch_time: str = "06:00"


# ── Routing function ──────────────────────────────────────────────────────────


def confidence_router(state: MorningBriefState) -> str:
    """LangGraph conditional edge router from evaluate_quality.

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

    if overall >= 0.70:
        return "narrative_writer"
    elif overall >= 0.40:
        return "hil_queue"
    else:
        return "block_and_log"
