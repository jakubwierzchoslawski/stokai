"""
Unit tests for AlertsReadRepository.

Uses AsyncMock to simulate AsyncSession — no DB required.
All ordering, filter, pagination, event_link format, and tenant-isolation
cases are verified.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.alerts.repositories.alerts_read_repository import AlertsReadRepository


# ── Fixtures ──────────────────────────────────────────────────────────────────

USER_ID = uuid.uuid4()
TENANT_ID = uuid.uuid4()
OTHER_USER = uuid.uuid4()
OTHER_TENANT = uuid.uuid4()

EVENT_ID = uuid.uuid4()
ALERT_ID = uuid.uuid4()


def _make_db_row(**overrides) -> dict:
    """Return a dict simulating a joined DB row with sensible defaults."""
    base = {
        "alert_id": ALERT_ID,
        "dispatched_at": datetime(2026, 1, 10, 9, 0, tzinfo=timezone.utc),
        "event_title": "US Trade Policy Shift",
        "action_signal": "BUY_OPP",
        "confidence": 0.82,
        "channel": "email",
        "status": "dispatched",
        "event_id": EVENT_ID,
        "lat": 38.9,
        "lon": -77.0,
    }
    base.update(overrides)
    return base


def _make_session_with_rows(rows: list[dict], scalar_value: int = 0) -> AsyncMock:
    """Build a mock AsyncSession returning rows for first execute and scalar for second."""
    session = AsyncMock()

    class FakeRow:
        def __init__(self, data: dict):
            self._data = data

        def __getitem__(self, key):
            return self._data[key]

    fake_rows = [FakeRow(r) for r in rows]

    rows_result = MagicMock()
    rows_result.mappings.return_value.all.return_value = fake_rows

    count_result = MagicMock()
    count_result.scalar.return_value = scalar_value

    # First call → items, second call → total count
    session.execute = AsyncMock(side_effect=[rows_result, count_result])
    return session


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ordered_by_dispatched_at_desc():
    """SQL ORDER BY dispatched_at DESC NULLS LAST must be in the query."""
    session = _make_session_with_rows([_make_db_row()])
    repo = AlertsReadRepository(session)

    await repo.list_alerts(user_id=USER_ID, tenant_id=TENANT_ID, page=1, page_size=20)

    sql_text = str(session.execute.call_args_list[0][0][0])
    assert "dispatched_at" in sql_text.lower()
    assert "desc" in sql_text.lower()


@pytest.mark.asyncio
async def test_status_filter_passed_to_query():
    """status filter is included in query parameters."""
    session = _make_session_with_rows([])
    repo = AlertsReadRepository(session)

    await repo.list_alerts(
        user_id=USER_ID, tenant_id=TENANT_ID, page=1, page_size=20, status="dispatched"
    )

    params = session.execute.call_args_list[0][0][1]
    assert params.get("status") == "dispatched"


@pytest.mark.asyncio
async def test_action_signal_filter_passed_to_query():
    """action_signal filter is included in query parameters."""
    session = _make_session_with_rows([])
    repo = AlertsReadRepository(session)

    await repo.list_alerts(
        user_id=USER_ID,
        tenant_id=TENANT_ID,
        page=1,
        page_size=20,
        action_signal="BUY_OPP",
    )

    params = session.execute.call_args_list[0][0][1]
    assert params.get("action_signal") == "BUY_OPP"


@pytest.mark.asyncio
async def test_date_range_filters_passed_to_query():
    """date_from and date_to are included in query parameters."""
    session = _make_session_with_rows([])
    repo = AlertsReadRepository(session)

    date_from = datetime(2026, 1, 1, tzinfo=timezone.utc)
    date_to = datetime(2026, 1, 31, tzinfo=timezone.utc)

    await repo.list_alerts(
        user_id=USER_ID,
        tenant_id=TENANT_ID,
        page=1,
        page_size=20,
        date_from=date_from,
        date_to=date_to,
    )

    params = session.execute.call_args_list[0][0][1]
    assert params.get("date_from") == date_from
    assert params.get("date_to") == date_to


@pytest.mark.asyncio
async def test_no_filters_returns_all():
    """No optional filters → all rows returned (count=1 here)."""
    session = _make_session_with_rows([_make_db_row()], scalar_value=1)
    repo = AlertsReadRepository(session)

    items, total = await repo.list_alerts(
        user_id=USER_ID, tenant_id=TENANT_ID, page=1, page_size=20
    )

    assert total == 1
    assert len(items) == 1


@pytest.mark.asyncio
async def test_pagination_offset_calculated():
    """page=2, page_size=10 → OFFSET 10 in query params."""
    session = _make_session_with_rows([])
    repo = AlertsReadRepository(session)

    await repo.list_alerts(user_id=USER_ID, tenant_id=TENANT_ID, page=2, page_size=10)

    params = session.execute.call_args_list[0][0][1]
    assert params.get("offset") == 10
    assert params.get("limit") == 10


@pytest.mark.asyncio
async def test_total_reflects_full_set():
    """total returned matches the count query scalar, not the page size."""
    session = _make_session_with_rows([_make_db_row()], scalar_value=42)
    repo = AlertsReadRepository(session)

    items, total = await repo.list_alerts(
        user_id=USER_ID, tenant_id=TENANT_ID, page=1, page_size=20
    )

    assert total == 42


@pytest.mark.asyncio
async def test_event_link_correctly_formed():
    """event_link = /map?event={event_id}&lat={lat}&lon={lon}."""
    event_id = uuid.uuid4()
    lat = 51.5
    lon = -0.1
    row = _make_db_row(event_id=event_id, lat=lat, lon=lon)
    session = _make_session_with_rows([row], scalar_value=1)
    repo = AlertsReadRepository(session)

    items, _ = await repo.list_alerts(
        user_id=USER_ID, tenant_id=TENANT_ID, page=1, page_size=20
    )

    expected_link = f"/map?event={event_id}&lat={lat}&lon={lon}"
    assert items[0].event_link == expected_link


@pytest.mark.asyncio
async def test_tenant_isolation_params_set():
    """user_id and tenant_id are always bound into the query."""
    session = _make_session_with_rows([])
    repo = AlertsReadRepository(session)

    await repo.list_alerts(user_id=OTHER_USER, tenant_id=OTHER_TENANT, page=1, page_size=20)

    params = session.execute.call_args_list[0][0][1]
    assert params["user_id"] == OTHER_USER
    assert params["tenant_id"] == OTHER_TENANT


@pytest.mark.asyncio
async def test_silent_channel_alert_appears():
    """Alerts with channel='silent' are returned (no channel filter in list)."""
    row = _make_db_row(channel="silent", status="suppressed_daily_limit")
    session = _make_session_with_rows([row], scalar_value=1)
    repo = AlertsReadRepository(session)

    items, total = await repo.list_alerts(
        user_id=USER_ID, tenant_id=TENANT_ID, page=1, page_size=20
    )

    assert total == 1
    assert items[0].channel == "silent"


@pytest.mark.asyncio
async def test_report_link_is_none():
    """report_link is always None in this implementation."""
    session = _make_session_with_rows([_make_db_row()], scalar_value=1)
    repo = AlertsReadRepository(session)

    items, _ = await repo.list_alerts(
        user_id=USER_ID, tenant_id=TENANT_ID, page=1, page_size=20
    )

    assert items[0].report_link is None
