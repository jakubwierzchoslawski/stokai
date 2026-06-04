"""
ai.workflows.watchlist_scan_state — WatchlistScanState and route_after_quality.

State model and routing logic for the Watchlist Scan workflow (PLAN-F-008).

Afternoon scan at 17:30 UTC covering watchlist + portfolio companies.
Detects anomalies, fetches analogies, generates recommendations, routes by
confidence, sends email by 18:00.

The route_after_quality function is used as a LangGraph conditional edge:
  >= 0.70  → "dispatch"        (auto-send path)
  >= 0.40  → "hil_enqueue"     (human-in-the-loop path)
  < 0.40   → "block_and_notify" (blocked — confidence too low)

PLAN-F-008 TASK-001
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class WatchlistScanState(BaseModel):
    """LangGraph state model for the Watchlist Scan workflow.

    Passed through all workflow nodes and used as the LangGraph state and the
    serialisation format for the workflow_run.final_state JSONB column.
    """

    workflow_id: UUID
    workflow_type: str = "watchlist_scan"
    tenant_id: UUID
    user_id: UUID
    started_at: datetime

    # Company scoping — filled by fetch_scoped_companies
    watchlist_companies: list[UUID] = Field(default_factory=list)
    portfolio_companies: list[UUID] = Field(default_factory=list)
    scoped_company_ids: list[UUID] = Field(default_factory=list)  # union/dedup

    # DeterministicNode outputs
    today_events: list[dict] = Field(default_factory=list)
    score_changes: list[dict] = Field(default_factory=list)
    analogies: dict = Field(default_factory=dict)

    # AgentNode outputs
    relevant_events: list[dict] = Field(default_factory=list)
    anomalies: list[dict] = Field(default_factory=list)
    high_anomaly_company_ids: list[UUID] = Field(default_factory=list)
    recommendations: list[dict] = Field(default_factory=list)
    report: dict | None = None

    # Confidence tracking
    confidence_scores: dict[str, float] = Field(default_factory=dict)
    overall_confidence: float = 0.0
    requires_hil: bool = False
    hil_reason: str | None = None

    # Cost tracking
    cost_usd: float = 0.0

    # Observability
    langfuse_trace_id: str | None = None

    # Routing / lifecycle
    brief_id: UUID | None = None
    dispatch_time: str = "18:00"


# ── Routing function ──────────────────────────────────────────────────────────


def route_after_quality(
    state: WatchlistScanState,
) -> Literal["dispatch", "hil_enqueue", "block_and_notify"]:
    """LangGraph conditional edge router from evaluate_quality.

    Routes based on state.overall_confidence:
      >= 0.70  → "dispatch"         (auto-send path)
      >= 0.40  → "hil_enqueue"      (human-in-the-loop path)
      < 0.40   → "block_and_notify" (blocked — confidence too low)

    Args:
        state: Current WatchlistScanState from the evaluate_quality node.

    Returns:
        Node name string for LangGraph conditional edge routing.
    """
    confidence = state.overall_confidence

    if confidence >= 0.70:
        return "dispatch"
    elif confidence >= 0.40:
        return "hil_enqueue"
    else:
        return "block_and_notify"
