"""
Domain models for the Mode A Reactive Pipeline.

All models are Pydantic v2 BaseModel subclasses. PipelineContext is mutable
(model_config allow) so steps can update it in place without replacement copies.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator


class RawEvent(BaseModel):
    """Raw event received from any source adapter."""

    source_provider: str  # "gdelt" | "edgar" | "price_anomaly" | "twitter"
    occurred_at: datetime
    raw_payload: dict[str, Any]
    tenant_id: UUID | None = None


class ClassificationResult(BaseModel):
    """LLM-derived classification for a raw event."""

    category: list[str]
    intensity: int  # 1–5 inclusive
    sentiment: float  # –1.0 to +1.0 inclusive
    geo_regions: list[str]
    affected_sectors: list[str]
    cameo_code: str

    @field_validator("intensity")
    @classmethod
    def validate_intensity(cls, v: int) -> int:
        if not (1 <= v <= 5):
            raise ValueError(f"intensity must be an integer in [1, 5], got {v}")
        return v

    @field_validator("sentiment")
    @classmethod
    def validate_sentiment(cls, v: float) -> float:
        if not (-1.0 <= v <= 1.0):
            raise ValueError(f"sentiment must be a float in [-1.0, 1.0], got {v}")
        return v


class TickerExtractionResult(BaseModel):
    """LLM-derived ticker extraction result for a raw event."""

    tickers: list[str]

    @field_validator("tickers", mode="before")
    @classmethod
    def validate_tickers(cls, v: list) -> list:
        """Validate that each ticker is a non-empty uppercase string."""
        for item in v:
            if not isinstance(item, str) or not item:
                raise ValueError(f"Each ticker must be a non-empty string, got {item!r}")
            if item != item.upper():
                raise ValueError(
                    f"Each ticker must be uppercase, got {item!r}"
                )
        return v


class ExposureCandidate(BaseModel):
    """Single company exposure derived from the exposure-map step."""

    company_id: UUID
    exposure_type: str  # "direct" | "supply_chain" | "sector" | "currency"
    direction: str  # "positive" | "negative"
    magnitude: float  # 0.0–1.0


class PipelineResult(BaseModel):
    """Final output of a completed pipeline run."""

    event_id: UUID
    alert_dispatched: bool
    silent_logged: bool
    deep_dive_enqueued: bool
    total_cost_usd: float
    step_latencies_ms: dict[str, int]
    langfuse_trace_id: str


# ── Analogy Search Models (PLAN-F-004, Step 7) ────────────────────────────────

class AnalogSearchResult(BaseModel):
    """Single historical event returned by HNSW cosine similarity search."""

    event_id: UUID
    similarity_score: float
    event_title: str
    event_date: datetime
    intensity: int
    category: list[str]
    price_change_t1d: float | None
    sample_size: int
    low_sample: bool  # True when sample_size < 5


class AnalogSearchResultSet(BaseModel):
    """Full result set from find_historical_analogies (step 7)."""

    results: list[AnalogSearchResult]
    k_requested: int
    low_sample: bool  # True if any result has low_sample=True
    source_event_id: UUID


class PipelineContext(BaseModel):
    """Mutable context object threaded through all 12 pipeline steps."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    raw_event: RawEvent
    event_id: UUID | None = None
    classification: ClassificationResult | None = None
    tickers: list[str] = []
    exposures: list[ExposureCandidate] = []
    embedding: list[float] | None = None
    analogies: list[dict] = []
    analogy_result_set: AnalogSearchResultSet | None = None
    alert_text: str | None = None
    rule_match: Any | None = None
    cost_accumulator: Any = None
    langfuse_trace_id: str | None = None
    langfuse_span: Any | None = None
    # Flags set by dispatch step
    alert_dispatched: bool = False
    silent_logged: bool = False
    deep_dive_enqueued: bool = False
    # Per-step latency tracking
    step_latencies_ms: dict[str, int] = {}
