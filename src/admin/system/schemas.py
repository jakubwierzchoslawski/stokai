"""
admin.system.schemas — Pydantic request/response schemas for the system ops panel.

PLAN-F-030 TASK-008
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# ── Ingestion Jobs ─────────────────────────────────────────────────────────────

class IngestionJobResponse(BaseModel):
    job_id: uuid.UUID
    name: str
    schedule: str
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None
    status: str
    error_count: int
    last_error_trace: Optional[str] = None
    updated_at: datetime


class TriggerJobResponse(BaseModel):
    job_id: str
    task_id: str
    status: str


# ── Cost Monitor ───────────────────────────────────────────────────────────────

class CostBreakdownItem(BaseModel):
    label: str
    total_cost_usd: float


class DailyTotal(BaseModel):
    date: str
    total_cost_usd: float


class CostResponse(BaseModel):
    spend_usd: float
    threshold_usd: float
    pct_used: float
    warning_active: bool
    hard_stop_active: bool
    by_source: list[dict]
    by_model: list[dict]
    by_workflow: list[dict]
    daily_totals: list[dict]


class ThresholdUpdateRequest(BaseModel):
    threshold_usd: float = Field(..., gt=0, description="New budget threshold in USD")


class ThresholdUpdateResponse(BaseModel):
    threshold_usd: float


# ── Company Universe ───────────────────────────────────────────────────────────

class CompanyItem(BaseModel):
    company_id: uuid.UUID
    ticker: str
    name: str
    is_tracked: bool
    sector_gics: Optional[str] = None


class CompanyListResponse(BaseModel):
    items: list[dict]
    total: int
    page: int
    page_size: int


class TrackResponse(BaseModel):
    company_id: uuid.UUID
    is_tracked: bool


# ── Cache Inspection ───────────────────────────────────────────────────────────

class CacheStatsResponse(BaseModel):
    price_bars_count: int
    embeddings_count: int
    event_data_count: int
    total_redis_memory_bytes: int


class CacheRefreshRequest(BaseModel):
    data_type: str = Field(
        ...,
        description="One of: price_bars, embeddings, event_data",
    )
    company_id: Optional[uuid.UUID] = Field(
        None,
        description="Optional: scope price_bars refresh to a single company",
    )


class CacheRefreshResponse(BaseModel):
    data_type: str
    keys_deleted: int


# ── Feature Flags ──────────────────────────────────────────────────────────────

class FeatureFlagResponse(BaseModel):
    flag_id: str
    environment: str
    enabled: bool
    updated_at: Optional[datetime] = None
    updated_by: Optional[uuid.UUID] = None


class FeatureFlagUpdateRequest(BaseModel):
    enabled: bool
