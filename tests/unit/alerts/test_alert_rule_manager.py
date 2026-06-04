"""
Unit tests for AlertRuleManager service.

Uses AsyncMock for the CRUD repository.
Covers: validation, delegation, NotFoundError propagation.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.alerts.services.alert_rule_manager import AlertRuleManager
from src.alerts.exceptions import NotFoundError, ValidationError
from src.alerts.schemas import AlertRuleResponse, CreateAlertRuleRequest, UpdateAlertRuleRequest


USER_ID = uuid.uuid4()
TENANT_ID = uuid.uuid4()
RULE_ID = uuid.uuid4()


def _make_rule_response(rule_id=None) -> AlertRuleResponse:
    return AlertRuleResponse(
        rule_id=rule_id or RULE_ID,
        user_id=USER_ID,
        name="Test Rule",
        enabled=True,
        event_category_filter=["conflict"],
        intensity_min=2,
        ticker_list=["AAPL"],
        quiet_hours_start=None,
        quiet_hours_end=None,
        per_ticker_interval_hours=24,
        channels=["email"],
    )


def _make_create_request(intensity_min: int = 2, per_ticker_interval_hours: int = 24) -> CreateAlertRuleRequest:
    return CreateAlertRuleRequest(
        name="Test Rule",
        event_category_filter=["conflict"],
        intensity_min=intensity_min,
        ticker_list=["AAPL"],
        channels=["email"],
        per_ticker_interval_hours=per_ticker_interval_hours,
    )


def _make_repo(
    get_by_user_returns=None,
    get_by_id_returns=None,
    insert_returns=None,
):
    repo = MagicMock()
    repo.get_by_user = AsyncMock(return_value=get_by_user_returns or [])
    repo.get_by_id = AsyncMock(return_value=get_by_id_returns)
    repo.insert = AsyncMock(return_value=insert_returns or uuid.uuid4())
    repo.update = AsyncMock()
    repo.delete = AsyncMock()
    return repo


# ── Create ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_valid_payload_delegates_to_repo_insert():
    """Valid request → repo.insert is called once and returns UUID."""
    repo = _make_repo(insert_returns=RULE_ID)
    svc = AlertRuleManager(repo)

    req = _make_create_request(intensity_min=3)
    result = await svc.create_rule(
        user_id=USER_ID, tenant_id=TENANT_ID, request=req
    )

    repo.insert.assert_called_once()
    assert result == RULE_ID


@pytest.mark.asyncio
async def test_create_intensity_min_zero_raises_validation_error():
    """intensity_min=0 is below the valid range [1,5]."""
    repo = _make_repo()
    svc = AlertRuleManager(repo)

    req = _make_create_request(intensity_min=0)
    with pytest.raises(ValidationError):
        await svc.create_rule(user_id=USER_ID, tenant_id=TENANT_ID, request=req)

    repo.insert.assert_not_called()


@pytest.mark.asyncio
async def test_create_intensity_min_six_raises_validation_error():
    """intensity_min=6 is above the valid range [1,5]."""
    repo = _make_repo()
    svc = AlertRuleManager(repo)

    req = _make_create_request(intensity_min=6)
    with pytest.raises(ValidationError):
        await svc.create_rule(user_id=USER_ID, tenant_id=TENANT_ID, request=req)

    repo.insert.assert_not_called()


@pytest.mark.asyncio
async def test_create_per_ticker_interval_negative_raises_validation_error():
    """per_ticker_interval_hours=-1 is not valid (must be > 0)."""
    repo = _make_repo()
    svc = AlertRuleManager(repo)

    req = _make_create_request(per_ticker_interval_hours=-1)
    with pytest.raises(ValidationError):
        await svc.create_rule(user_id=USER_ID, tenant_id=TENANT_ID, request=req)

    repo.insert.assert_not_called()


# ── Update ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_when_rule_not_found_raises_not_found_error():
    """update: repo.get_by_id returns None → NotFoundError (no info leak)."""
    repo = _make_repo(get_by_id_returns=None)
    svc = AlertRuleManager(repo)

    with pytest.raises(NotFoundError):
        await svc.update_rule(
            rule_id=RULE_ID,
            user_id=USER_ID,
            tenant_id=TENANT_ID,
            request=UpdateAlertRuleRequest(enabled=False),
        )

    repo.update.assert_not_called()


@pytest.mark.asyncio
async def test_update_delegates_to_repo_update():
    """update: rule found → repo.update called with correct params."""
    repo = _make_repo(get_by_id_returns=_make_rule_response())
    svc = AlertRuleManager(repo)

    await svc.update_rule(
        rule_id=RULE_ID,
        user_id=USER_ID,
        tenant_id=TENANT_ID,
        request=UpdateAlertRuleRequest(enabled=False),
    )

    repo.update.assert_called_once()
    kwargs = repo.update.call_args[1]
    assert kwargs["enabled"] is False


# ── Delete ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_when_rule_not_found_raises_not_found_error():
    """delete: repo.get_by_id returns None → NotFoundError (no info leak)."""
    repo = _make_repo(get_by_id_returns=None)
    svc = AlertRuleManager(repo)

    with pytest.raises(NotFoundError):
        await svc.delete_rule(
            rule_id=RULE_ID, user_id=USER_ID, tenant_id=TENANT_ID
        )

    repo.delete.assert_not_called()


@pytest.mark.asyncio
async def test_delete_calls_repo_delete_once():
    """delete: rule found → repo.delete called exactly once."""
    repo = _make_repo(get_by_id_returns=_make_rule_response())
    svc = AlertRuleManager(repo)

    await svc.delete_rule(
        rule_id=RULE_ID, user_id=USER_ID, tenant_id=TENANT_ID
    )

    repo.delete.assert_called_once()
    kwargs = repo.delete.call_args[1]
    assert kwargs["rule_id"] == RULE_ID


# ── List ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_delegates_to_repo_get_by_user():
    """list_rules delegates to repo.get_by_user and returns its result."""
    rules = [_make_rule_response(rule_id=uuid.uuid4()) for _ in range(3)]
    repo = _make_repo(get_by_user_returns=rules)
    svc = AlertRuleManager(repo)

    result = await svc.list_rules(user_id=USER_ID, tenant_id=TENANT_ID)

    repo.get_by_user.assert_called_once_with(user_id=USER_ID, tenant_id=TENANT_ID)
    assert len(result) == 3
