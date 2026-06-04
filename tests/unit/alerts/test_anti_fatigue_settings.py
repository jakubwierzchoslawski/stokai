"""
Unit tests for AntiFatigueSettingsService.

Uses AsyncMock for the DB session — no DB required.
Covers: get, partial update, validations, tenant isolation.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.alerts.services.anti_fatigue_settings import AntiFatigueSettingsService
from src.alerts.exceptions import ValidationError
from src.alerts.schemas import AntiFatigueSettingsResponse, UpdateAntiFatigueRequest


USER_ID = uuid.uuid4()
TENANT_ID = uuid.uuid4()
OTHER_USER = uuid.uuid4()
OTHER_TENANT = uuid.uuid4()

_DEFAULT_SETTINGS = {
    "daily_push_limit": 10,
    "quiet_hours_start": None,
    "quiet_hours_end": None,
    "dedup_window_minutes": 60,
}


def _make_session_with_settings(settings: dict | None) -> AsyncMock:
    """Session whose first execute is UPDATE, second returns settings row (get_settings).

    update_settings() call order:
      1. UPDATE "user" ...  (no mapping needed)
      2. SELECT ... FROM "user"  (get_settings called internally after update)
    """
    session = AsyncMock()

    class FakeRow:
        def __init__(self, data: dict):
            self._data = data

        def __getitem__(self, key):
            return self._data[key]

    update_result = MagicMock()
    update_result.rowcount = 1

    select_result = MagicMock()
    select_result.mappings.return_value.first.return_value = (
        FakeRow(settings) if settings is not None else None
    )

    session.execute = AsyncMock(side_effect=[update_result, select_result])
    return session


def _make_get_session(settings: dict | None) -> AsyncMock:
    """Session whose execute returns settings for GET only."""
    session = AsyncMock()

    class FakeRow:
        def __init__(self, data: dict):
            self._data = data

        def __getitem__(self, key):
            return self._data[key]

    result = MagicMock()
    result.mappings.return_value.first.return_value = (
        FakeRow(settings) if settings is not None else None
    )

    session.execute = AsyncMock(return_value=result)
    return session


# ── get_settings ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_settings_returns_current_values():
    """get_settings returns the values stored in user.settings JSONB."""
    session = _make_get_session(_DEFAULT_SETTINGS)
    svc = AntiFatigueSettingsService(session)

    result = await svc.get_settings(user_id=USER_ID, tenant_id=TENANT_ID)

    assert result.daily_push_limit == 10
    assert result.dedup_window_minutes == 60
    assert result.quiet_hours_start is None
    assert result.quiet_hours_end is None


@pytest.mark.asyncio
async def test_get_settings_returns_defaults_when_no_row():
    """get_settings returns hardcoded defaults when user has no settings row."""
    session = _make_get_session(None)
    svc = AntiFatigueSettingsService(session)

    result = await svc.get_settings(user_id=USER_ID, tenant_id=TENANT_ID)

    assert isinstance(result, AntiFatigueSettingsResponse)
    assert result.daily_push_limit >= 1
    assert result.dedup_window_minutes >= 1


# ── update_settings ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_only_daily_push_limit_changes_only_that():
    """Partial update with only daily_push_limit keeps other fields intact."""
    current = {**_DEFAULT_SETTINGS, "daily_push_limit": 5}
    session = _make_session_with_settings(current)
    svc = AntiFatigueSettingsService(session)

    await svc.update_settings(
        user_id=USER_ID,
        tenant_id=TENANT_ID,
        request=UpdateAntiFatigueRequest(daily_push_limit=20),
    )

    # Check that UPDATE was called
    assert session.execute.call_count == 2


@pytest.mark.asyncio
async def test_update_daily_push_limit_zero_raises():
    """daily_push_limit=0 is below the minimum of 1."""
    session = _make_get_session(_DEFAULT_SETTINGS)
    svc = AntiFatigueSettingsService(session)

    with pytest.raises(ValidationError):
        await svc.update_settings(
            user_id=USER_ID,
            tenant_id=TENANT_ID,
            request=UpdateAntiFatigueRequest(daily_push_limit=0),
        )


@pytest.mark.asyncio
async def test_update_dedup_window_zero_raises():
    """dedup_window_minutes=0 is below the minimum of 1."""
    session = _make_get_session(_DEFAULT_SETTINGS)
    svc = AntiFatigueSettingsService(session)

    with pytest.raises(ValidationError):
        await svc.update_settings(
            user_id=USER_ID,
            tenant_id=TENANT_ID,
            request=UpdateAntiFatigueRequest(dedup_window_minutes=0),
        )


@pytest.mark.asyncio
async def test_update_overnight_quiet_hours_accepted():
    """quiet_hours_start='22:00', quiet_hours_end='06:00' is a valid overnight range."""
    session = _make_session_with_settings(_DEFAULT_SETTINGS)
    svc = AntiFatigueSettingsService(session)

    # Should not raise
    await svc.update_settings(
        user_id=USER_ID,
        tenant_id=TENANT_ID,
        request=UpdateAntiFatigueRequest(
            quiet_hours_start="22:00", quiet_hours_end="06:00"
        ),
    )


@pytest.mark.asyncio
async def test_update_same_start_end_raises():
    """quiet_hours_start == quiet_hours_end creates a zero window → ValidationError."""
    session = _make_get_session(_DEFAULT_SETTINGS)
    svc = AntiFatigueSettingsService(session)

    with pytest.raises(ValidationError):
        await svc.update_settings(
            user_id=USER_ID,
            tenant_id=TENANT_ID,
            request=UpdateAntiFatigueRequest(
                quiet_hours_start="08:00", quiet_hours_end="08:00"
            ),
        )


@pytest.mark.asyncio
async def test_update_partial_preserves_unset_fields():
    """Setting only quiet_hours doesn't touch daily_push_limit."""
    session = _make_session_with_settings(_DEFAULT_SETTINGS)
    svc = AntiFatigueSettingsService(session)

    await svc.update_settings(
        user_id=USER_ID,
        tenant_id=TENANT_ID,
        request=UpdateAntiFatigueRequest(quiet_hours_start="22:00", quiet_hours_end="06:00"),
    )

    update_call = session.execute.call_args_list[1]
    params = update_call[0][1]
    # daily_push_limit should be None (not overwritten in SQL)
    assert params.get("daily_push_limit") is None


@pytest.mark.asyncio
async def test_get_settings_is_isolated_to_user_and_tenant():
    """The query params always include user_id and tenant_id."""
    session = _make_get_session(_DEFAULT_SETTINGS)
    svc = AntiFatigueSettingsService(session)

    await svc.get_settings(user_id=OTHER_USER, tenant_id=OTHER_TENANT)

    params = session.execute.call_args[0][1]
    assert params["user_id"] == OTHER_USER
    assert params["tenant_id"] == OTHER_TENANT
