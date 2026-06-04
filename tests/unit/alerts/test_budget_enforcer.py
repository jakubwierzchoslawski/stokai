"""
Unit tests for BudgetEnforcer.

Pure synchronous tests — no async, no mocks needed.
"""
from __future__ import annotations

import pytest

from src.alerts.exceptions import BudgetHardStopError
from src.alerts.models import AlertStatus, BudgetState
from src.alerts.services.budget_enforcer import BudgetEnforcer


ENFORCER = BudgetEnforcer()


def _state(
    daily_budget_usd: float,
    spent_today_usd: float,
    hard_stop_pct: float = 100.0,
    alert_threshold_pct: float = 80.0,
) -> BudgetState:
    return BudgetState(
        daily_budget_usd=daily_budget_usd,
        spent_today_usd=spent_today_usd,
        alert_threshold_pct=alert_threshold_pct,
        hard_stop_pct=hard_stop_pct,
    )


# ── Happy path ───────────────────────────────────────────────────────────────

def test_within_budget_returns_none():
    """spent/budget*100 < hard_stop_pct → returns None (gate passes)."""
    state = _state(daily_budget_usd=10.0, spent_today_usd=5.0, hard_stop_pct=100.0)

    result = ENFORCER.check(state)

    assert result is None


# ── Hard stop triggered ───────────────────────────────────────────────────────

def test_hard_stop_at_100_pct_raises():
    """Spending exactly 100% of budget triggers BudgetHardStopError."""
    state = _state(daily_budget_usd=10.0, spent_today_usd=10.0, hard_stop_pct=100.0)

    with pytest.raises(BudgetHardStopError):
        ENFORCER.check(state)


def test_hard_stop_at_80_pct_triggers_at_80_spend():
    """hard_stop_pct=80 raises when spend reaches 80%."""
    state = _state(daily_budget_usd=10.0, spent_today_usd=8.0, hard_stop_pct=80.0)

    with pytest.raises(BudgetHardStopError):
        ENFORCER.check(state)


def test_hard_stop_at_80_pct_passes_below_threshold():
    """hard_stop_pct=80 allows dispatch below 80%."""
    state = _state(daily_budget_usd=10.0, spent_today_usd=7.9, hard_stop_pct=80.0)

    result = ENFORCER.check(state)

    assert result is None


def test_fully_spent_budget_raises():
    """Spending entire budget triggers BudgetHardStopError (not None)."""
    state = _state(daily_budget_usd=5.0, spent_today_usd=5.0, hard_stop_pct=100.0)

    with pytest.raises(BudgetHardStopError) as exc_info:
        ENFORCER.check(state)

    assert exc_info.value.spent_today_usd == 5.0
    assert exc_info.value.daily_budget_usd == 5.0


# ── Zero budget guard ─────────────────────────────────────────────────────────

def test_zero_daily_budget_raises_hard_stop_error():
    """daily_budget_usd == 0 raises BudgetHardStopError (divide-by-zero protection)."""
    state = _state(daily_budget_usd=0.0, spent_today_usd=0.0)

    with pytest.raises(BudgetHardStopError):
        ENFORCER.check(state)


def test_hard_stop_error_carries_spend_info():
    """BudgetHardStopError includes spent and budget amounts for log correlation."""
    state = _state(daily_budget_usd=10.0, spent_today_usd=10.0, hard_stop_pct=100.0)

    with pytest.raises(BudgetHardStopError) as exc_info:
        ENFORCER.check(state)

    err = exc_info.value
    assert err.spent_today_usd == 10.0
    assert err.daily_budget_usd == 10.0
