"""PipelineState and supporting Pydantic models for the Mode A pipeline.

These models carry context between each of the 13 pipeline steps.  Every step
receives a ``PipelineState`` instance and returns an updated copy — steps never
mutate shared state outside their returned model.

Architecture enforcement:
  P-01 Provider Abstraction — source field uses ``RawEventSource`` enum; no
    raw string comparisons elsewhere in the pipeline.
  P-09 Full AI Lineage — ``langfuse_trace_id``, ``failed_step``, and
    ``error_detail`` are first-class fields so the executor can persist them.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class RawEventSource(str, Enum):
    """Canonical source identifiers for raw ingested events."""

    X_FILTERED_STREAM = "X_FILTERED_STREAM"
    GDELT = "GDELT"
    SEC_EDGAR = "SEC_EDGAR"
    PRICE_ANOMALY = "PRICE_ANOMALY"


class EventCategory(str, Enum):
    """Six fixed event categories used by the classifier and router."""

    GEOPOLITICAL_CONFLICT = "GEOPOLITICAL_CONFLICT"
    ECONOMIC_POLICY = "ECONOMIC_POLICY"
    NATURAL_DISASTER = "NATURAL_DISASTER"
    CORPORATE_ACTION = "CORPORATE_ACTION"
    REGULATORY_CHANGE = "REGULATORY_CHANGE"
    PRICE_ANOMALY = "PRICE_ANOMALY"


class AlertRoute(str, Enum):
    """Alert routing decision produced by Step 10 (ROUTING).

    Boundaries (C-003):
      AUTO_SEND  — confidence >= 0.7
      HIL_QUEUE  — 0.4 <= confidence < 0.7  (0.4 is inclusive lower bound)
      BLOCKED    — confidence < 0.4
    """

    AUTO_SEND = "AUTO_SEND"
    HIL_QUEUE = "HIL_QUEUE"
    BLOCKED = "BLOCKED"


# ---------------------------------------------------------------------------
# Raw event payload (produced by ingestion adapters before pipeline entry)
# ---------------------------------------------------------------------------

class RawEventPayload(BaseModel):
    """Data produced by an ingestion adapter and enqueued with the Celery task."""

    source: RawEventSource
    raw_payload: dict[str, Any]
    detected_at: datetime
    tenant_id: uuid.UUID


# ---------------------------------------------------------------------------
# Pipeline state — carries context across all 13 steps
# ---------------------------------------------------------------------------

class PipelineState(BaseModel):
    """Mutable context object passed sequentially through all pipeline steps.

    Each step returns a new ``PipelineState`` with updated fields; the executor
    replaces its reference with the returned value.  Pydantic model_copy is used
    for partial updates to preserve immutability between steps.
    """

    raw_event_id: uuid.UUID
    tenant_id: uuid.UUID
    payload: RawEventPayload

    # Step 2: DEDUPLICATE
    fingerprint: str | None = None

    # Step 3: PARSE
    event_description: str | None = None
    geo_lat: float | None = None
    geo_lon: float | None = None
    tickers: list[str] = Field(default_factory=list)

    # Step 4: CLASSIFY
    category: EventCategory | None = None
    intensity: int | None = None  # 1–5

    # Step 5: EMBED
    embedding: list[float] | None = None

    # Step 6: PORTFOLIO SCAN
    exposure_map: dict[str, float] = Field(default_factory=dict)  # portfolio_id (str) -> 0.0

    # Step 8: ANALOGY SEARCH
    analogues: list[uuid.UUID] = Field(default_factory=list)

    # Step 9: CONFIDENCE CALC
    confidence: float | None = None

    # Step 10: ROUTING
    route: AlertRoute | None = None

    # Step 11: RECORD / Step 12: DISPATCH
    alert_text: str | None = None

    # Step 13: TRACE
    generated_at: datetime | None = None

    # Observability
    langfuse_trace_id: str | None = None

    # Executor book-keeping
    current_step: str = "s01_ingest"
    failed_step: str | None = None
    error_detail: str | None = None
