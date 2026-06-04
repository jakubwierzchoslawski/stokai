"""
Domain models for the alerts module.

All models are Pydantic v2 BaseModel subclasses. Enums and models here are
the single source of truth for alert state across the anti-fatigue chain,
dispatch path, and silent-log path.
"""
from __future__ import annotations

from datetime import datetime, time
from enum import Enum
from uuid import UUID

from pydantic import BaseModel


# ── Enumerations ─────────────────────────────────────────────────────────────

class ActionSignal(str, Enum):
    """AI-recommended portfolio action derived from event analysis."""

    HOLD = "HOLD"
    WATCH = "WATCH"
    BUY_OPP = "BUY_OPP"
    REDUCE_RISK = "REDUCE_RISK"
    HEDGE = "HEDGE"
    CONTRARIAN = "CONTRARIAN"


class AlertStatus(str, Enum):
    """Final disposition of an alert: dispatched or suppressed at a named gate."""

    DISPATCHED = "dispatched"
    SUPPRESSED_DAILY_LIMIT = "suppressed_daily_limit"
    SUPPRESSED_QUIET_HOURS = "suppressed_quiet_hours"
    SUPPRESSED_DEDUP = "suppressed_dedup"
    SUPPRESSED_BUDGET = "suppressed_budget"
    SUPPRESSED_TICKER_INTERVAL = "suppressed_ticker_interval"


# ── Core domain models ────────────────────────────────────────────────────────

class AlertRuleRow(BaseModel):
    """A single active alert rule, joined with the owning user's email."""

    rule_id: UUID
    tenant_id: UUID
    user_id: UUID
    user_email: str
    event_categories: list[str]
    intensity_min: int
    ticker_list: list[str]
    quiet_hours_start: time | None
    quiet_hours_end: time | None
    daily_limit: int
    dedup_window_minutes: int
    per_ticker_interval_hours: int
    enabled: bool


class AlertTextResult(BaseModel):
    """Structured output from the LLM alert-text generator (step 8)."""

    alert_text: str
    action_signal: ActionSignal
    confidence: float
    sample_size: int
    low_sample_disclaimer: bool


class AntiFatigueState(BaseModel):
    """Snapshot of a user's fatigue counters for the current evaluation window."""

    dispatched_today: int
    last_ticker_dispatch: datetime | None
    recent_event_alert_ids: list[UUID]


class BudgetState(BaseModel):
    """User's daily spend budget and current expenditure."""

    daily_budget_usd: float
    spent_today_usd: float
    alert_threshold_pct: float  # warn at this percentage (default 80)
    hard_stop_pct: float        # halt at this percentage (default 100)


class DispatchDecision(BaseModel):
    """Outcome of the anti-fatigue + budget gate chain for a single rule match."""

    should_dispatch: bool
    suppression_status: AlertStatus | None
    alert_row: AlertRow | None = None


class AlertRow(BaseModel):
    """Full record written to the `alert` table on dispatch or silent-log."""

    alert_id: UUID
    event_id: UUID
    user_id: UUID
    tenant_id: UUID
    rule_id: UUID | None
    alert_text: str | None
    action_signal: ActionSignal | None
    confidence: float | None
    sample_size: int | None
    dispatched_at: datetime | None
    channel: str  # "email" | "silent"
    cost_usd: float
    status: AlertStatus
