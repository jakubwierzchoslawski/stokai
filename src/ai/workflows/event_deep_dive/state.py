"""
ai.workflows.event_deep_dive.state — DeepDiveWorkflowState and data transfer models.

PLAN-F-010 TASK-001.

DeepDiveWorkflowState extends WorkflowState with event_deep_dive–specific fields.
All supporting Pydantic models live here so they are import-accessible from a
single location.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from src.ai.workflows.state import WorkflowState


# ── Supporting DTOs ───────────────────────────────────────────────────────────


class PriceReaction(BaseModel):
    """Price reaction of a single company to the triggering event.

    Populated by the fetch_market_reaction_so_far deterministic node.
    Empty fields are valid when the market is closed.
    """

    company_id: UUID
    ticker: str
    price_before: float | None = None
    price_after: float | None = None
    change_pct: float | None = None
    volume_ratio: float | None = None  # ratio vs 30-day avg
    sampled_at: datetime | None = None


class ExposureAnalysis(BaseModel):
    """Structured output from a single exposure_analyst AgentNode invocation."""

    company_id: UUID
    exposure_type: str          # "direct" | "supply_chain" | "sector" | "currency"
    direction: str              # "positive" | "negative" | "neutral"
    magnitude: float            # 0.0–1.0
    reasoning: str
    confidence: float           # 0.0–1.0
    cost_usd: float


class MemoDraft(BaseModel):
    """Structured memo produced by the narrative_writer AgentNode."""

    headline: str
    executive_summary: str
    event_analysis: dict[str, Any]
    market_impact: dict[str, Any]
    per_company_recommendations: list[dict[str, Any]] = Field(default_factory=list)
    historical_analogies: list[dict[str, Any]] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    confidence: float


class BriefCreate(BaseModel):
    """DTO used to INSERT a Brief/report row via IBriefRepository.insert_memo."""

    brief_id: UUID = Field(default_factory=uuid4)
    type: str = "event_deep_dive"
    event_id: UUID
    tenant_id: UUID
    content: dict[str, Any]          # stored as JSONB
    confidence: float
    cost_usd: float
    cost_limited: bool = False


# ── GeoEvent domain object (light wrapper) ───────────────────────────────────


class GeoEvent(BaseModel):
    """Light domain model for a geo_event row fetched from the database."""

    event_id: UUID
    tenant_id: UUID | None = None
    title: str | None = None
    summary: str | None = None
    source_provider: str | None = None
    category: list[str] = Field(default_factory=list)
    intensity: int | None = None
    sentiment: float | None = None
    geo_regions: list[str] = Field(default_factory=list)
    affected_sectors: list[str] = Field(default_factory=list)
    cameo_code: str | None = None
    lat: float | None = None
    lon: float | None = None
    occurred_at: datetime | None = None

    # Exposures fetched via EventExposureRepository
    exposures: list[dict[str, Any]] = Field(default_factory=list)


# ── Graph node list constant ──────────────────────────────────────────────────

GRAPH_NODES: list[str] = [
    "fetch_event_full",
    "fetch_market_reaction_so_far",
    "run_exposure_analysts",
    "event_deep_dive_agent",
    "historical_context_agent",
    "recommendation_synthesizer",
    "narrative_writer",
    "evaluate_quality",
]


# ── Main workflow state ───────────────────────────────────────────────────────


class DeepDiveWorkflowState(WorkflowState):
    """LangGraph state for the Event Deep-Dive workflow.

    Extends the canonical WorkflowState with all event-deep-dive–specific
    fields.  The parent class provides: workflow_id, workflow_type, tenant_id,
    user_id, company_id, inputs, confidence_scores, cost_usd, status,
    langfuse_trace_id, etc.

    Invariants:
    - event_full is None until fetch_event_full completes.
    - memo_draft is None until narrative_writer completes (last AgentNode).
    - cost_limited is set by evaluate_quality from the CostAccumulator state.
    """

    # Domain-specific fields
    event_full: GeoEvent | None = None
    market_reaction: dict[str, PriceReaction] = Field(default_factory=dict)
    exposure_analyses: list[ExposureAnalysis] = Field(default_factory=list)
    memo_draft: MemoDraft | None = None
    cost_limited: bool = False

    # Typed override: market_reaction keys are UUIDs serialized as str in JSON
    # We keep keys as str here for JSON serialisation compatibility
    model_config = {"arbitrary_types_allowed": True}
