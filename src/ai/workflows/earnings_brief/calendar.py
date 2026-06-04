"""
ai.workflows.earnings_brief.calendar — US trading calendar utilities.

Provides:
  next_trading_day(from_date) -> date
    Returns the next trading day after from_date, skipping weekends and
    major US market holidays.

PLAN-F-009 TASK-003
"""
from __future__ import annotations

from datetime import date, timedelta


# US federal / NYSE market holidays (approximate fixed-date list)
# Holiday dates shift when the holiday falls on a weekend, but for MVP we
# use a simple year-agnostic rule set. A production implementation would
# use a proper calendar library (e.g., pandas_market_calendars or exchange_calendars).
_FIXED_HOLIDAYS_MM_DD = {
    (1, 1),   # New Year's Day
    (7, 4),   # Independence Day
    (12, 25), # Christmas Day
}

# Variable US market holidays (approximate – expanded as needed)
# These are hard-coded for current year ranges for MVP simplicity.
_VARIABLE_HOLIDAYS: set[date] = {
    # MLK Day (3rd Monday in January) — approximate
    date(2026, 1, 19),
    date(2027, 1, 18),
    # Presidents' Day (3rd Monday in February)
    date(2026, 2, 16),
    date(2027, 2, 15),
    # Good Friday (varies)
    date(2026, 4, 3),
    date(2027, 3, 26),
    # Memorial Day (last Monday in May)
    date(2026, 5, 25),
    date(2027, 5, 31),
    # Juneteenth
    date(2026, 6, 19),
    date(2027, 6, 18),
    # Labor Day (1st Monday in September)
    date(2026, 9, 7),
    date(2027, 9, 6),
    # Thanksgiving (4th Thursday in November)
    date(2026, 11, 26),
    date(2027, 11, 25),
}


def _is_us_market_holiday(d: date) -> bool:
    """Return True if d is a US stock market holiday."""
    if (d.month, d.day) in _FIXED_HOLIDAYS_MM_DD:
        return True
    if d in _VARIABLE_HOLIDAYS:
        return True
    # Day after Thanksgiving (Black Friday — market closes early but is open;
    # not treated as a full holiday here for MVP)
    return False


def next_trading_day(from_date: date | None = None) -> date:
    """Return the next trading day after from_date (defaults to today).

    A trading day is a weekday (Mon–Fri) that is not a US market holiday.

    Args:
        from_date: The reference date. Defaults to today's date.

    Returns:
        The next trading day as a date object.
    """
    if from_date is None:
        from_date = date.today()

    candidate = from_date + timedelta(days=1)

    while True:
        # Skip weekends
        if candidate.weekday() >= 5:  # 5 = Saturday, 6 = Sunday
            candidate += timedelta(days=1)
            continue
        # Skip US market holidays
        if _is_us_market_holiday(candidate):
            candidate += timedelta(days=1)
            continue
        break

    return candidate
