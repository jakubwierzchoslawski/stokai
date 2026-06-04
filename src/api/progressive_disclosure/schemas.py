"""
schemas.py — Pydantic v2 response models for the Progressive Disclosure API.

PLAN-F-020 TASK-003

All field types match the TypeScript disclosure.types.ts interfaces.
Only fields that are explicitly optional in the data model are Optional.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


# ── Shared sub-models ─────────────────────────────────────────────────────────


class TickerDeltaSchema(BaseModel):
    ticker: str
    score_delta: float


class SparklineSchema(BaseModel):
    """Single close-price point for a T±7d sparkline."""

    ts: str   # ISO date
    close: float


class SparklineSeriesSchema(BaseModel):
    """Sparkline series for one ticker."""

    ticker: str
    ohlcv_7d: list[SparklineSchema]


class AnalogSummarySchema(BaseModel):
    event_id: str
    headline: str
    occurred_at: str
    similarity_score: float


class AffectedCompanySchema(BaseModel):
    company_id: UUID
    ticker: str
    name: str
    score: float
    delta: float


class SocialPostSchema(BaseModel):
    post_id: str
    source: str
    text: str
    timestamp: str


class ReasoningStepSchema(BaseModel):
    agent_role: str
    step_index: int
    content: str
    tool_calls: list[str] = Field(default_factory=list)


class ScenarioNodeSchema(BaseModel):
    label: str
    probability: float
    description: str
    children: list["ScenarioNodeSchema"] = Field(default_factory=list)


# Required for self-referencing model
ScenarioNodeSchema.model_rebuild()


# ── Level 1: Popup ────────────────────────────────────────────────────────────


class PopupDataResponse(BaseModel):
    event_id: UUID
    category: list[str]
    intensity: int
    headline: str
    time_ago: str
    location: str
    exposed_holdings_count: int
    tickers_with_delta: list[TickerDeltaSchema]
    action_signal: str
    confidence: float
    sample_size: int
    low_sample: bool


class PopupApiResponse(BaseModel):
    data: PopupDataResponse
    meta: dict[str, Any] = Field(default_factory=dict)
    error: None = None


# ── Level 2: Side Panel ───────────────────────────────────────────────────────


class SidePanelDataResponse(PopupDataResponse):
    summary: str
    sparklines: list[SparklineSeriesSchema] = Field(default_factory=list)
    rationale: str
    analogies: list[AnalogSummarySchema] = Field(default_factory=list)
    affected_companies: list[AffectedCompanySchema] = Field(default_factory=list)
    is_contrarian: bool
    contrarian_callout: str | None = None
    social_posts: list[SocialPostSchema] | None = None
    audit_trail_url: str


class SidePanelApiResponse(BaseModel):
    data: SidePanelDataResponse
    meta: dict[str, Any] = Field(default_factory=dict)
    error: None = None


# ── Audit Trail ───────────────────────────────────────────────────────────────


class AuditTrailResponse(BaseModel):
    event_id: UUID
    prompt_version: str
    langfuse_trace_url: str
    analogies: list[AnalogSummarySchema] = Field(default_factory=list)
    reasoning_steps: list[ReasoningStepSchema] = Field(default_factory=list)


class AuditTrailApiResponse(BaseModel):
    data: AuditTrailResponse
    meta: dict[str, Any] = Field(default_factory=dict)
    error: None = None


# ── Level 3: Deep Dive ────────────────────────────────────────────────────────


class DeepDiveResponse(BaseModel):
    event_id: UUID
    memo: str
    scenario_tree: ScenarioNodeSchema | None = None
    analogies: list[AnalogSummarySchema] = Field(default_factory=list)
    affected_companies: list[AffectedCompanySchema] = Field(default_factory=list)
    generated_at: datetime


class DeepDiveApiResponse(BaseModel):
    data: DeepDiveResponse
    meta: dict[str, Any] = Field(default_factory=dict)
    error: None = None


class DeepDivePendingResponse(BaseModel):
    """202 Accepted body when deep-dive workflow is not yet complete."""

    status: str = "pending"
