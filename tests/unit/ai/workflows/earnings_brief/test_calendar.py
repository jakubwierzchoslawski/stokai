"""
Unit tests for calendar.py — next_trading_day().

TDD — PLAN-F-009 TASK-003.
"""
from __future__ import annotations

from datetime import date

import pytest

from src.ai.workflows.earnings_brief.calendar import next_trading_day


class TestNextTradingDay:
    def test_skips_saturday(self):
        """Friday → returns Monday."""
        # 2026-01-02 is a Friday
        friday = date(2026, 1, 2)
        result = next_trading_day(from_date=friday)
        # Should be Monday 2026-01-05
        assert result == date(2026, 1, 5)

    def test_skips_sunday(self):
        """Saturday → returns Monday (skipping Saturday → Sunday → Monday)."""
        saturday = date(2026, 1, 3)
        result = next_trading_day(from_date=saturday)
        assert result == date(2026, 1, 5)

    def test_weekday_goes_to_next_day(self):
        """Wednesday → returns Thursday."""
        wednesday = date(2026, 1, 7)
        result = next_trading_day(from_date=wednesday)
        assert result == date(2026, 1, 8)

    def test_thursday_goes_to_friday(self):
        """Thursday → returns Friday."""
        thursday = date(2026, 1, 8)
        result = next_trading_day(from_date=thursday)
        assert result == date(2026, 1, 9)

    def test_result_is_never_saturday(self):
        """next_trading_day should never return a Saturday."""
        # Test across 30 days
        start = date(2026, 1, 1)
        for i in range(30):
            from datetime import timedelta
            d = start + timedelta(days=i)
            result = next_trading_day(from_date=d)
            assert result.weekday() < 5, f"Got weekend day for input {d}: {result}"

    def test_skips_new_years_day(self):
        """Day before New Year's (Dec 31 2025) → skips Jan 1 holiday."""
        dec31 = date(2025, 12, 31)
        result = next_trading_day(from_date=dec31)
        # Jan 1 2026 is Wednesday (holiday) → Jan 2 is Thursday
        assert result > date(2026, 1, 1)

    def test_default_from_today(self):
        """Calling with no argument uses today's date."""
        result = next_trading_day()
        assert isinstance(result, date)
        assert result > date.today()
