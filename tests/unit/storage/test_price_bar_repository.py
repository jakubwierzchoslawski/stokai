"""
Unit tests for PriceBarRepository.

All DB interactions are mocked via AsyncMock — no real database required.

PLAN-F-023 TASK-001
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.storage.repositories.price_bar_repository import PriceBar, PriceBarRepository

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TENANT_ID = uuid.uuid4()
COMPANY_ID = uuid.uuid4()
INTERVAL = "1d"
FROM_TS = datetime(2024, 1, 1, tzinfo=timezone.utc)
TO_TS = datetime(2024, 4, 1, tzinfo=timezone.utc)


def _make_row(ts_offset_days: int) -> MagicMock:
    """Return a mock DB row as a tuple-like object."""
    row = MagicMock()
    row.__getitem__ = lambda self, i: [
        str(COMPANY_ID),
        FROM_TS + timedelta(days=ts_offset_days),
        100.0 + ts_offset_days,
        110.0 + ts_offset_days,
        90.0 + ts_offset_days,
        105.0 + ts_offset_days,
        1_000_000.0,
        INTERVAL,
    ][i]
    return row


def _mock_session(rows: list) -> AsyncMock:
    """Build an AsyncMock session that returns the given rows from execute."""
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.fetchall.return_value = rows
    session.execute = AsyncMock(return_value=result_mock)
    return session


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestGetOhlcvHistory:
    """Tests for PriceBarRepository.get_ohlcv_history."""

    async def test_get_ohlcv_history_returns_bars_in_asc_ts_order(self) -> None:
        """DB rows returned by the query (already ordered ASC) map 1-to-1 to PriceBar."""
        rows = [_make_row(0), _make_row(1), _make_row(2)]
        session = _mock_session(rows)

        repo = PriceBarRepository(session)
        bars = await repo.get_ohlcv_history(
            company_id=COMPANY_ID,
            tenant_id=TENANT_ID,
            interval=INTERVAL,
            from_ts=FROM_TS,
            to_ts=TO_TS,
        )

        assert len(bars) == 3
        # Verify ascending order by checking timestamps increment
        assert bars[0].ts <= bars[1].ts <= bars[2].ts

    async def test_get_ohlcv_history_filters_by_tenant_id(self) -> None:
        """The SQL query must include tenant_id as a bind parameter."""
        rows = [_make_row(0)]
        session = _mock_session(rows)

        repo = PriceBarRepository(session)
        await repo.get_ohlcv_history(
            company_id=COMPANY_ID,
            tenant_id=TENANT_ID,
            interval=INTERVAL,
            from_ts=FROM_TS,
            to_ts=TO_TS,
        )

        # Confirm execute was called with tenant_id in the params
        call_args = session.execute.call_args
        params = call_args[0][1]  # second positional arg is the params dict
        assert str(TENANT_ID) == params["tenant_id"]

    async def test_get_ohlcv_history_filters_by_interval(self) -> None:
        """The SQL query must include interval as a bind parameter."""
        rows = []
        session = _mock_session(rows)

        repo = PriceBarRepository(session)
        await repo.get_ohlcv_history(
            company_id=COMPANY_ID,
            tenant_id=TENANT_ID,
            interval="1h",
            from_ts=FROM_TS,
            to_ts=TO_TS,
        )

        call_args = session.execute.call_args
        params = call_args[0][1]
        assert params["interval"] == "1h"

    async def test_get_ohlcv_history_respects_from_to_range(self) -> None:
        """from_ts and to_ts must appear in the bind parameters."""
        rows = []
        session = _mock_session(rows)

        repo = PriceBarRepository(session)
        custom_from = datetime(2024, 3, 1, tzinfo=timezone.utc)
        custom_to = datetime(2024, 3, 31, tzinfo=timezone.utc)
        await repo.get_ohlcv_history(
            company_id=COMPANY_ID,
            tenant_id=TENANT_ID,
            interval=INTERVAL,
            from_ts=custom_from,
            to_ts=custom_to,
        )

        call_args = session.execute.call_args
        params = call_args[0][1]
        assert params["from_ts"] == custom_from
        assert params["to_ts"] == custom_to

    async def test_get_ohlcv_history_caps_at_internal_limit(self) -> None:
        """Requesting 2000 rows must cap at 1000 in the SQL LIMIT parameter."""
        rows = []
        session = _mock_session(rows)

        repo = PriceBarRepository(session)
        await repo.get_ohlcv_history(
            company_id=COMPANY_ID,
            tenant_id=TENANT_ID,
            interval=INTERVAL,
            from_ts=FROM_TS,
            to_ts=TO_TS,
            limit=2000,
        )

        call_args = session.execute.call_args
        params = call_args[0][1]
        assert params["limit"] == 1000

    async def test_get_ohlcv_history_empty_result_returns_empty_list(self) -> None:
        """When the DB returns no rows, the method returns an empty list."""
        session = _mock_session([])

        repo = PriceBarRepository(session)
        bars = await repo.get_ohlcv_history(
            company_id=COMPANY_ID,
            tenant_id=TENANT_ID,
            interval=INTERVAL,
            from_ts=FROM_TS,
            to_ts=TO_TS,
        )

        assert bars == []
