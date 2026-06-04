"""
pipeline_state.py — PipelineContext for the Mode A Reactive Pipeline (PLAN-F-003).

PipelineContext carries all data produced by pipeline steps 1–5.
It is passed by reference through each step so that steps can update it in place.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class GeoEventCreate(BaseModel):
    """Input value object for creating a new geo_event row.

    Attributes:
        headline: Short event headline.
        occurred_at: ISO-8601 timestamp when the event occurred.
        geo_regions: List of affected geographic regions.
        sectors_affected: List of affected GICS sectors.
        event_intensity: Event severity on a 1–5 scale.
        sentiment: "positive" | "negative" | "neutral".
        source: Source adapter identifier.
    """

    headline: str
    occurred_at: str
    geo_regions: list[str] = []
    sectors_affected: list[str] = []
    event_intensity: int = 3
    sentiment: str = "neutral"
    source: str = "unknown"


class GeoEvent(BaseModel):
    """Value object returned after inserting a geo_event row.

    Attributes:
        event_id: UUID assigned by the database.
        headline: Short event headline.
        occurred_at: ISO-8601 timestamp when the event occurred.
        tenant_id: Owning tenant UUID.
    """

    event_id: UUID
    headline: str
    occurred_at: str
    tenant_id: UUID | None = None


class PipelineContext(BaseModel):
    """Mutable context object threaded through pipeline steps 1–5.

    All fields have sensible defaults; steps populate them as they run.

    Attributes:
        tenant_id:         Owning tenant.
        geo_regions:       List of affected geo regions from classification.
        sectors_affected:  List of affected sector labels from classification.
        event_intensity:   Classified event intensity (1–5).
        sentiment:         Classified sentiment: "positive" | "negative" | "neutral".
        geo_event_create:  Input for the geo_event INSERT (populated by step 1).
        event_id:          UUID of the persisted geo_event row (set by step 5).
        exposures:         Exposure records computed by step 4.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    tenant_id: UUID | None = None
    geo_regions: list[str] = []
    sectors_affected: list[str] = []
    event_intensity: int = 3
    sentiment: str = "neutral"
    geo_event_create: GeoEventCreate | None = None
    event_id: UUID | None = None
    exposures: list[Any] = []  # list[ExposureRecord] — typed as Any to avoid circular imports
