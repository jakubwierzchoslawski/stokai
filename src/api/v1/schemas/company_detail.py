"""
api.v1.schemas.company_detail — Pydantic response models for the Company Detail endpoint.

PLAN-F-023 TASK-002, TASK-003, TASK-004
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Sub-panels
# ---------------------------------------------------------------------------


class FundamentalsPanel(BaseModel):
    """Key financial fundamentals for a company."""

    pe_ratio: float | None
    eps: float | None
    revenue: float | None
    debt_to_equity: float | None
    source: str  # "fmp" | "edgar" | "cross_validated"
    as_of: datetime


class ScoreBreakdownItem(BaseModel):
    """Per-indicator score breakdown with formula summary and sparkline."""

    indicator_id: UUID
    indicator_name: str
    formula_summary: str  # first 120 chars of DSL formula; "..." appended if truncated
    weight: float
    raw_value: float | None
    score: float  # 0-100
    geo_adjusted: float | None
    sub_score_contribution: float  # weight * score / 100
    sparkline: list[float]  # last 30 daily score values, oldest-first


class ActiveEventSummary(BaseModel):
    """Summary of an active geo-event affecting the company."""

    event_id: UUID
    title: str
    occurred_at: datetime
    intensity: int
    category: list[str]
    exposure_magnitude: float


class AnalysisHistoryItem(BaseModel):
    """Single AI analysis record from the recommendation history."""

    rec_id: UUID
    generated_at: datetime
    workflow_type: str
    action_signal: str
    confidence: float
    rationale_summary: str  # first 200 chars


class TrackRecordItem(BaseModel):
    """Track record row with direction mapping and correctness flags."""

    rec_id: UUID
    generated_at: datetime
    action_signal: str
    direction: str  # "bullish" | "bearish" | "neutral"
    confidence: float
    actual_t1d: float | None
    actual_t1w: float | None
    correct_t1d: bool | None
    correct_t1w: bool | None


# ---------------------------------------------------------------------------
# Top-level response
# ---------------------------------------------------------------------------


class CompanyDetailResponse(BaseModel):
    """Aggregated company detail response combining all panels."""

    company_id: UUID
    ticker: str
    name: str
    sector: str
    market_cap: float | None
    fundamentals: FundamentalsPanel
    scores: list[ScoreBreakdownItem]
    active_events: list[ActiveEventSummary]
    analysis_history: list[AnalysisHistoryItem]
    track_record: list[TrackRecordItem]
    directional_accuracy_t1d: float | None  # proportion of correct_t1d where actual_t1d is not None
