"""
Unit tests for AlertRuleCrudRepository.

Uses AsyncMock for AsyncSession — no DB required.
Covers: get_by_user, get_by_id, insert, update (partial), delete.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, call

import pytest

from src.alerts.repositories.alert_rule_crud_repository import AlertRuleCrudRepository
from src.alerts.exceptions import NotFoundError


# ── Helpers ───────────────────────────────────────────────────────────────────

USER_A = uuid.uuid4()
USER_B = uuid.uuid4()
TENANT_ID = uuid.uuid4()

RULE_ID_1 = uuid.uuid4()
RULE_ID_2 = uuid.uuid4()
RULE_ID_3 = uuid.uuid4()


def _make_rule_dict(rule_id=None, user_id=None, **overrides) -> dict:
    base = {
        "rule_id": rule_id or uuid.uuid4(),
        "user_id": user_id or USER_A,
        "tenant_id": TENANT_ID,
        "name": "My Rule",
        "enabled": True,
        "event_category_filter": ["conflict"],
        "intensity_min": 2,
        "ticker_list": ["AAPL"],
        "quiet_hours_start": None,
        "quiet_hours_end": None,
        "per_ticker_interval_hours": 24,
        "channels": ["email"],
    }
    base.update(overrides)
    return base


def _make_session_mappings_all(rows: list[dict]) -> AsyncMock:
    """Session whose execute().mappings().all() returns FakeRow list."""
    session = AsyncMock()

    class FakeRow:
        def __init__(self, data: dict):
            self._data = data

        def __getitem__(self, key):
            return self._data[key]

    mapping_result = MagicMock()
    mapping_result.all.return_value = [FakeRow(r) for r in rows]

    execute_result = MagicMock()
    execute_result.mappings.return_value = mapping_result

    session.execute = AsyncMock(return_value=execute_result)
    return session


def _make_session_mappings_first(row: dict | None) -> AsyncMock:
    """Session whose execute().mappings().first() returns FakeRow or None."""
    session = AsyncMock()

    class FakeRow:
        def __init__(self, data: dict):
            self._data = data

        def __getitem__(self, key):
            return self._data[key]

    mapping_result = MagicMock()
    mapping_result.first.return_value = FakeRow(row) if row else None

    execute_result = MagicMock()
    execute_result.mappings.return_value = mapping_result

    session.execute = AsyncMock(return_value=execute_result)
    return session


def _make_session_scalar(value) -> AsyncMock:
    """Session whose execute().scalar() returns value."""
    session = AsyncMock()
    result = MagicMock()
    result.scalar.return_value = value
    session.execute = AsyncMock(return_value=result)
    return session


# ── get_by_user ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_by_user_returns_users_rules():
    """get_by_user returns only rules belonging to user_a."""
    rows = [
        _make_rule_dict(rule_id=RULE_ID_1, user_id=USER_A),
        _make_rule_dict(rule_id=RULE_ID_2, user_id=USER_A),
    ]
    session = _make_session_mappings_all(rows)
    repo = AlertRuleCrudRepository(session)

    result = await repo.get_by_user(user_id=USER_A, tenant_id=TENANT_ID)

    assert len(result) == 2
    assert all(r.user_id == USER_A for r in result)


@pytest.mark.asyncio
async def test_get_by_user_does_not_return_others():
    """get_by_user query is parameterised with user_id (tenant isolation check)."""
    session = _make_session_mappings_all([])
    repo = AlertRuleCrudRepository(session)

    await repo.get_by_user(user_id=USER_B, tenant_id=TENANT_ID)

    params = session.execute.call_args[0][1]
    assert params["user_id"] == USER_B
    assert params["tenant_id"] == TENANT_ID


# ── get_by_id ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_by_id_matches_all_three_ids():
    """get_by_id returns the rule when rule_id, user_id, tenant_id all match."""
    row = _make_rule_dict(rule_id=RULE_ID_1, user_id=USER_A)
    session = _make_session_mappings_first(row)
    repo = AlertRuleCrudRepository(session)

    result = await repo.get_by_id(
        rule_id=RULE_ID_1, user_id=USER_A, tenant_id=TENANT_ID
    )

    assert result is not None
    assert result.rule_id == RULE_ID_1


@pytest.mark.asyncio
async def test_get_by_id_returns_none_for_different_user():
    """get_by_id returns None when user_id doesn't match (no leakage)."""
    session = _make_session_mappings_first(None)
    repo = AlertRuleCrudRepository(session)

    result = await repo.get_by_id(
        rule_id=RULE_ID_1, user_id=USER_B, tenant_id=TENANT_ID
    )

    assert result is None


@pytest.mark.asyncio
async def test_get_by_id_returns_none_when_not_exists():
    """get_by_id returns None (not raises) when rule doesn't exist."""
    session = _make_session_mappings_first(None)
    repo = AlertRuleCrudRepository(session)

    result = await repo.get_by_id(
        rule_id=uuid.uuid4(), user_id=USER_A, tenant_id=TENANT_ID
    )

    assert result is None


# ── insert ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_insert_returns_new_uuid():
    """insert executes the SQL and returns a UUID."""
    session = AsyncMock()
    session.execute = AsyncMock()
    repo = AlertRuleCrudRepository(session)

    new_id = await repo.insert(
        user_id=USER_A,
        tenant_id=TENANT_ID,
        name="Test Rule",
        event_category_filter=["conflict"],
        intensity_min=2,
        ticker_list=["AAPL"],
        quiet_hours_start=None,
        quiet_hours_end=None,
        per_ticker_interval_hours=24,
        channels=["email"],
    )

    assert isinstance(new_id, uuid.UUID)
    assert session.execute.called


# ── update ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_partial_preserves_other_fields():
    """update with only enabled=False only sets enabled in the query params."""
    session = AsyncMock()
    session.execute = AsyncMock()
    repo = AlertRuleCrudRepository(session)

    await repo.update(
        rule_id=RULE_ID_1,
        user_id=USER_A,
        tenant_id=TENANT_ID,
        enabled=False,
    )

    params = session.execute.call_args[0][1]
    assert params["enabled"] is False
    # Other optional fields should not be set (or None means no change)
    assert "name" not in params or params.get("name") is None


@pytest.mark.asyncio
async def test_update_quiet_hours_atomically():
    """update with quiet_hours sets both start and end in one call."""
    session = AsyncMock()
    session.execute = AsyncMock()
    repo = AlertRuleCrudRepository(session)

    await repo.update(
        rule_id=RULE_ID_1,
        user_id=USER_A,
        tenant_id=TENANT_ID,
        quiet_hours_start="22:00",
        quiet_hours_end="06:00",
    )

    params = session.execute.call_args[0][1]
    assert params.get("quiet_hours_start") == "22:00"
    assert params.get("quiet_hours_end") == "06:00"


# ── delete ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_removes_row():
    """delete executes a DELETE statement with correct params."""
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.rowcount = 1
    session.execute = AsyncMock(return_value=result_mock)
    repo = AlertRuleCrudRepository(session)

    await repo.delete(rule_id=RULE_ID_1, user_id=USER_A, tenant_id=TENANT_ID)

    assert session.execute.called
    params = session.execute.call_args[0][1]
    assert params["rule_id"] == RULE_ID_1
    assert params["user_id"] == USER_A
    assert params["tenant_id"] == TENANT_ID


@pytest.mark.asyncio
async def test_delete_non_existent_raises_not_found_error():
    """delete raises NotFoundError when rowcount == 0."""
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.rowcount = 0
    session.execute = AsyncMock(return_value=result_mock)
    repo = AlertRuleCrudRepository(session)

    with pytest.raises(NotFoundError):
        await repo.delete(rule_id=uuid.uuid4(), user_id=USER_A, tenant_id=TENANT_ID)
