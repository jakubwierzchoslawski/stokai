"""
Unit tests for AntiFatigueChecker.

All tests are pure in-memory — no DB, no async, no mocks needed.
Gates are verified individually and in correct evaluation order.
"""
from __future__ import annotations

import uuid
from datetime import datetime, time, timedelta, timezone

import pytest

from src.alerts.models import AlertRuleRow, AlertStatus, AntiFatigueState
from src.alerts.services.anti_fatigue_checker import AntiFatigueChecker


# ── Fixtures ─────────────────────────────────────────────────────────────────

def _make_rule(**overrides) -> AlertRuleRow:
    base = dict(
        rule_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        user_email="u@e.com",
        event_categories=[],
        intensity_min=1,
        ticker_list=[],
        quiet_hours_start=None,
        quiet_hours_end=None,
        daily_limit=5,
        dedup_window_minutes=60,
        per_ticker_interval_hours=24,
        enabled=True,
    )
    base.update(overrides)
    return AlertRuleRow(**base)


def _make_state(**overrides) -> AntiFatigueState:
    base = dict(
        dispatched_today=0,
        last_ticker_dispatch=None,
        recent_event_alert_ids=[],
    )
    base.update(overrides)
    return AntiFatigueState(**base)


NOW = datetime(2026, 6, 3, 14, 0, 0, tzinfo=timezone.utc)
CHECKER = AntiFatigueChecker()


# ── All gates pass ────────────────────────────────────────────────────────────

def test_all_gates_pass_returns_none():
    """When all conditions are within limits, returns None."""
    rule = _make_rule(daily_limit=5)
    state = _make_state(dispatched_today=0)

    result = CHECKER.check(rule, state, NOW, ["AAPL"])

    assert result is None


# ── Gate 1: Daily limit ───────────────────────────────────────────────────────

def test_daily_limit_equal_to_dispatched_today_suppresses():
    """dispatched_today >= daily_limit triggers SUPPRESSED_DAILY_LIMIT."""
    rule = _make_rule(daily_limit=5)
    state = _make_state(dispatched_today=5)

    result = CHECKER.check(rule, state, NOW, [])

    assert result == AlertStatus.SUPPRESSED_DAILY_LIMIT


def test_daily_limit_above_dispatched_passes():
    """dispatched_today < daily_limit: gate passes."""
    rule = _make_rule(daily_limit=5)
    state = _make_state(dispatched_today=4)

    result = CHECKER.check(rule, state, NOW, [])

    assert result is None


# ── Gate 2: Quiet hours ───────────────────────────────────────────────────────

def test_quiet_hours_same_day_range_suppresses():
    """Event at 23:00 falls within same-day quiet window 22:00–23:59."""
    rule = _make_rule(
        quiet_hours_start=time(22, 0),
        quiet_hours_end=time(23, 59),
    )
    event_time = datetime(2026, 6, 3, 23, 0, 0, tzinfo=timezone.utc)

    result = CHECKER.check(rule, _make_state(), event_time, [])

    assert result == AlertStatus.SUPPRESSED_QUIET_HOURS


def test_quiet_hours_overnight_range_suppresses_after_start():
    """Event at 23:00 falls within overnight quiet window 22:00–06:00."""
    rule = _make_rule(
        quiet_hours_start=time(22, 0),
        quiet_hours_end=time(6, 0),
    )
    event_time = datetime(2026, 6, 3, 23, 0, 0, tzinfo=timezone.utc)

    result = CHECKER.check(rule, _make_state(), event_time, [])

    assert result == AlertStatus.SUPPRESSED_QUIET_HOURS


def test_quiet_hours_overnight_range_suppresses_before_end():
    """Event at 05:00 falls within overnight quiet window 22:00–06:00."""
    rule = _make_rule(
        quiet_hours_start=time(22, 0),
        quiet_hours_end=time(6, 0),
    )
    event_time = datetime(2026, 6, 3, 5, 0, 0, tzinfo=timezone.utc)

    result = CHECKER.check(rule, _make_state(), event_time, [])

    assert result == AlertStatus.SUPPRESSED_QUIET_HOURS


def test_quiet_hours_event_outside_window_passes():
    """Event at 12:00 falls outside quiet window 22:00–06:00."""
    rule = _make_rule(
        quiet_hours_start=time(22, 0),
        quiet_hours_end=time(6, 0),
    )
    event_time = datetime(2026, 6, 3, 12, 0, 0, tzinfo=timezone.utc)

    result = CHECKER.check(rule, _make_state(), event_time, [])

    assert result is None


# ── Gate 3: Per-ticker interval ───────────────────────────────────────────────

def test_ticker_interval_within_threshold_suppresses():
    """Ticker last dispatched 2 hours ago with 24-hour interval is suppressed."""
    rule = _make_rule(per_ticker_interval_hours=24)
    last_dispatch = NOW - timedelta(hours=2)
    state = _make_state(last_ticker_dispatch=last_dispatch)

    result = CHECKER.check(rule, state, NOW, ["AAPL"])

    assert result == AlertStatus.SUPPRESSED_TICKER_INTERVAL


def test_ticker_interval_past_threshold_passes():
    """Ticker last dispatched 25 hours ago with 24-hour interval: gate passes."""
    rule = _make_rule(per_ticker_interval_hours=24)
    last_dispatch = NOW - timedelta(hours=25)
    state = _make_state(last_ticker_dispatch=last_dispatch)

    result = CHECKER.check(rule, state, NOW, ["AAPL"])

    assert result is None


# ── Gate 4: Deduplication ─────────────────────────────────────────────────────

def test_dedup_non_empty_alert_ids_suppresses():
    """recent_event_alert_ids non-empty triggers SUPPRESSED_DEDUP."""
    state = _make_state(recent_event_alert_ids=[uuid.uuid4()])

    result = CHECKER.check(_make_rule(), state, NOW, [])

    assert result == AlertStatus.SUPPRESSED_DEDUP


def test_dedup_empty_alert_ids_passes():
    """recent_event_alert_ids empty: gate passes."""
    state = _make_state(recent_event_alert_ids=[])

    result = CHECKER.check(_make_rule(), state, NOW, [])

    assert result is None


# ── Gate order verification ───────────────────────────────────────────────────

def test_daily_limit_evaluated_before_quiet_hours():
    """Daily limit gate fires before quiet hours gate when both triggered."""
    rule = _make_rule(
        daily_limit=5,
        quiet_hours_start=time(0, 0),
        quiet_hours_end=time(23, 59),
    )
    # Both gates would trigger — daily limit fires first
    state = _make_state(dispatched_today=5)

    result = CHECKER.check(rule, state, NOW, [])

    assert result == AlertStatus.SUPPRESSED_DAILY_LIMIT
