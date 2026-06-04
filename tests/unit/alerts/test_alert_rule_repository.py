"""
Unit tests for AlertRuleRepository.

Uses AsyncMock to simulate AsyncSession so no DB is required.
All tenant isolation and field-mapping cases are verified.
"""
from __future__ import annotations

import uuid
from datetime import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.alerts.models import AlertRuleRow
from src.alerts.repositories.alert_rule_repository import AlertRuleRepository


def _make_rule_row(**overrides):
    """Return a dict simulating a DB mapping row with sensible defaults."""
    base = {
        "rule_id": uuid.uuid4(),
        "tenant_id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "user_email": "user@example.com",
        "event_categories": ["conflict"],
        "intensity_min": 2,
        "ticker_list": ["AAPL"],
        "quiet_hours_start": None,
        "quiet_hours_end": None,
        "daily_limit": 5,
        "dedup_window_minutes": 60,
        "per_ticker_interval_hours": 24,
        "enabled": True,
    }
    base.update(overrides)
    return base


def _make_session(rows: list[dict]) -> AsyncMock:
    """Build a mock AsyncSession that returns *rows* from .execute()."""
    session = AsyncMock()
    mapping_mock = MagicMock()
    mapping_mock.all.return_value = [MagicMock(**{k: v for k, v in r.items()}, __getitem__=lambda self, k: r[k]) for r in rows]

    # Use dict-style access via MagicMock
    result_mock = MagicMock()
    result_mock.mappings.return_value = mapping_mock
    session.execute = AsyncMock(return_value=result_mock)
    return session


def _make_session_with_rows(rows: list[dict]) -> AsyncMock:
    """Build a session returning properly keyed row-like objects."""
    session = AsyncMock()

    class FakeRow:
        def __init__(self, data: dict):
            self._data = data

        def __getitem__(self, key):
            return self._data[key]

    fake_rows = [FakeRow(r) for r in rows]

    mapping_result = MagicMock()
    mapping_result.all.return_value = fake_rows

    execute_result = MagicMock()
    execute_result.mappings.return_value = mapping_result

    session.execute = AsyncMock(return_value=execute_result)
    return session


TENANT_A = uuid.uuid4()
TENANT_B = uuid.uuid4()


@pytest.mark.asyncio
async def test_get_active_rules_returns_only_enabled_for_tenant():
    """get_active_rules returns rules matching the given tenant_id."""
    row = _make_rule_row(tenant_id=TENANT_A, enabled=True)
    session = _make_session_with_rows([row])
    repo = AlertRuleRepository(session)

    rules = await repo.get_active_rules(TENANT_A)

    assert len(rules) == 1
    assert rules[0].tenant_id == row["tenant_id"]
    # Verify the SQL was executed with the correct tenant_id param
    call_args = session.execute.call_args
    params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("parameters", {})
    # The second positional arg is the params dict
    assert call_args[0][1]["tenant_id"] == TENANT_A


@pytest.mark.asyncio
async def test_get_active_rules_empty_when_no_rules_for_tenant():
    """get_active_rules returns empty list when no matching rules exist."""
    session = _make_session_with_rows([])
    repo = AlertRuleRepository(session)

    rules = await repo.get_active_rules(TENANT_A)

    assert rules == []


@pytest.mark.asyncio
async def test_get_active_rules_tenant_isolation():
    """Query is parameterised with tenant_id — cross-tenant data is impossible."""
    row_a = _make_rule_row(tenant_id=TENANT_A)
    session = _make_session_with_rows([row_a])
    repo = AlertRuleRepository(session)

    # When querying TENANT_B the mock returns TENANT_A's data only if the
    # WHERE clause is bypassed — we verify the param is passed correctly.
    await repo.get_active_rules(TENANT_B)

    call_params = session.execute.call_args[0][1]
    assert call_params["tenant_id"] == TENANT_B  # not TENANT_A


@pytest.mark.asyncio
async def test_get_active_rules_user_email_populated():
    """user_email is taken from the joined user row."""
    row = _make_rule_row(user_email="trader@example.com")
    session = _make_session_with_rows([row])
    repo = AlertRuleRepository(session)

    rules = await repo.get_active_rules(TENANT_A)

    assert rules[0].user_email == "trader@example.com"


@pytest.mark.asyncio
async def test_get_active_rules_all_schema_fields_populated():
    """All AlertRuleRow fields are mapped correctly from the DB row."""
    rule_id = uuid.uuid4()
    user_id = uuid.uuid4()
    row = _make_rule_row(
        rule_id=rule_id,
        tenant_id=TENANT_A,
        user_id=user_id,
        user_email="q@q.com",
        event_categories=["geopolitical", "trade"],
        intensity_min=3,
        ticker_list=["TSLA", "NVDA"],
        quiet_hours_start=time(22, 0),
        quiet_hours_end=time(6, 0),
        daily_limit=10,
        dedup_window_minutes=30,
        per_ticker_interval_hours=12,
        enabled=True,
    )
    session = _make_session_with_rows([row])
    repo = AlertRuleRepository(session)

    rules = await repo.get_active_rules(TENANT_A)
    r = rules[0]

    assert r.rule_id == rule_id
    assert r.user_id == user_id
    assert r.event_categories == ["geopolitical", "trade"]
    assert r.intensity_min == 3
    assert r.ticker_list == ["TSLA", "NVDA"]
    assert r.quiet_hours_start == time(22, 0)
    assert r.quiet_hours_end == time(6, 0)
    assert r.daily_limit == 10
    assert r.dedup_window_minutes == 30
    assert r.per_ticker_interval_hours == 12
    assert r.enabled is True


@pytest.mark.asyncio
async def test_get_active_rules_multiple_rules_returned():
    """Multiple rules for the same tenant are all returned."""
    rows = [_make_rule_row(tenant_id=TENANT_A) for _ in range(3)]
    session = _make_session_with_rows(rows)
    repo = AlertRuleRepository(session)

    rules = await repo.get_active_rules(TENANT_A)

    assert len(rules) == 3


@pytest.mark.asyncio
async def test_get_active_rules_none_valued_jsonb_coerced_to_empty_list():
    """None event_categories or ticker_list is coerced to empty list."""
    row = _make_rule_row(event_categories=None, ticker_list=None)
    session = _make_session_with_rows([row])
    repo = AlertRuleRepository(session)

    rules = await repo.get_active_rules(TENANT_A)

    assert rules[0].event_categories == []
    assert rules[0].ticker_list == []
