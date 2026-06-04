"""
ai.workflows.watchlist_scan.state — WatchlistScanState Pydantic v2 model.

Extends WorkflowState with all watchlist-scan–specific fields per the
PLAN-F-008 interface contract.

PLAN-F-008 TASK-002
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import ConfigDict, Field

from src.ai.workflows.state import WorkflowState, WorkflowType


# ── Lightweight domain models (used instead of importing from storage) ──────────


class GeoEvent(dict):
    """Thin wrapper — GeoEvent is passed as a dict through the workflow."""


class RelevantEvent(dict):
    """Thin wrapper — RelevantEvent is a filtered GeoEvent with relevance metadata."""


class ScoreChange(dict):
    """Thin wrapper — ScoreChange carries company_id, prior_score, new_score, delta."""


class Anomaly(dict):
    """Thin wrapper — Anomaly carries company_id, magnitude, and description."""


class Analogy(dict):
    """Thin wrapper — Analogy carries historical analogue data keyed by company_id."""


class Recommendation(dict):
    """Thin wrapper — Recommendation carries action_signal, company_id, confidence, rationale."""


class Report(dict):
    """Thin wrapper — Report carries the final HTML narrative and metadata."""


# ── WatchlistScanState ─────────────────────────────────────────────────────────


class WatchlistScanState(WorkflowState):
    """LangGraph state model for the Watchlist Scan workflow (Mode B Workflow 3).

    Extends WorkflowState with watchlist-scan–specific fields.
    All collections default to empty; all optionals default to None or 0.0.

    Pydantic v2 model_config=ConfigDict(frozen=False) to allow LangGraph mutation.
    """

    model_config = ConfigDict(frozen=False)

    # Override workflow_type default
    workflow_type: WorkflowType = WorkflowType.WATCHLIST_SCAN

    # Company scoping — filled by fetch_watchlist node
    watchlist_companies: list[UUID] = Field(default_factory=list)
    portfolio_companies: list[UUID] = Field(default_factory=list)
    scoped_company_ids: list[UUID] = Field(default_factory=list)  # union / dedup

    # DeterministicNode outputs
    today_events: list[Any] = Field(default_factory=list)
    score_changes: list[Any] = Field(default_factory=list)

    # AgentNode outputs
    relevant_events: list[Any] = Field(default_factory=list)
    anomalies: list[Any] = Field(default_factory=list)
    high_anomaly_company_ids: list[UUID] = Field(default_factory=list)
    analogies: dict[str, Any] = Field(default_factory=dict)
    recommendations: list[Any] = Field(default_factory=list)

    # Report — None until narrative_writer runs
    report: Any | None = None

    # Confidence tracking (overall_confidence already on WorkflowState)
    overall_confidence: float = 0.0

    # Routing / lifecycle
    brief_id: UUID | None = None
