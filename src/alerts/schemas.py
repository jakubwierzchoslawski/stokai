"""
Pydantic schemas for the Alerts Center API (PLAN-F-025).

These are the public contract types exchanged between the API layer and
the frontend.  Domain models (AlertRuleRow, AlertRow, etc.) live in
src/alerts/models.py and are not exposed directly to HTTP clients.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


# ── Alert list ────────────────────────────────────────────────────────────────


class AlertListItem(BaseModel):
    alert_id: UUID
    occurred_at: datetime
    event_title: str
    action_signal: str
    confidence: float
    channel: str
    status: str
    event_link: str  # /map?event={event_id}&lat={lat}&lon={lon}
    report_link: str | None = None


class AlertListResponse(BaseModel):
    items: list[AlertListItem]
    total: int
    page: int
    page_size: int
    has_next: bool


# ── Alert rules ───────────────────────────────────────────────────────────────


class AlertRuleResponse(BaseModel):
    rule_id: UUID
    user_id: UUID
    name: str
    enabled: bool
    event_category_filter: list[str]
    intensity_min: int
    ticker_list: list[str]
    quiet_hours_start: str | None
    quiet_hours_end: str | None
    per_ticker_interval_hours: int
    channels: list[str]


class CreateAlertRuleRequest(BaseModel):
    name: str
    event_category_filter: list[str] = []
    intensity_min: int
    ticker_list: list[str] = []
    quiet_hours_start: str | None = None
    quiet_hours_end: str | None = None
    per_ticker_interval_hours: int = 24
    channels: list[str]


class UpdateAlertRuleRequest(BaseModel):
    name: str | None = None
    enabled: bool | None = None
    event_category_filter: list[str] | None = None
    intensity_min: int | None = None
    ticker_list: list[str] | None = None
    quiet_hours_start: str | None = None
    quiet_hours_end: str | None = None
    per_ticker_interval_hours: int | None = None
    channels: list[str] | None = None


# ── Anti-fatigue settings ─────────────────────────────────────────────────────


class AntiFatigueSettingsResponse(BaseModel):
    daily_push_limit: int
    quiet_hours_start: str | None
    quiet_hours_end: str | None
    dedup_window_minutes: int


class UpdateAntiFatigueRequest(BaseModel):
    daily_push_limit: int | None = None
    quiet_hours_start: str | None = None
    quiet_hours_end: str | None = None
    dedup_window_minutes: int | None = None
