"""
tests.unit.portfolio.test_onboarding_service

Unit tests for OnboardingService and onboarding endpoint.
"""
from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.api.auth_deps import get_current_user, CurrentUser
from src.api.routers.onboarding_router import _get_onboarding_service
from src.portfolio.onboarding_service import (
    OnboardingService,
    OnboardingState,
    IUserSettingsRepository,
    IHasHoldingChecker,
)


# ── Stubs ──────────────────────────────────────────────────────────────────────


class _StubSettingsRepo:
    def __init__(self, initial: dict[str, Any] | None = None) -> None:
        self._store: dict[str, Any] = initial or {}

    async def get_settings(self, tenant_id, user_id) -> dict[str, Any]:
        return dict(self._store)

    async def update_settings(self, tenant_id, user_id, patch) -> None:
        self._store.update(patch)


class _StubHoldingChecker:
    def __init__(self, has_holding: bool = False) -> None:
        self._has_holding = has_holding

    async def has_any_holding(self, tenant_id, user_id) -> bool:
        return self._has_holding


def _make_svc(
    settings: dict | None = None,
    has_holding: bool = False,
) -> tuple[OnboardingService, _StubSettingsRepo]:
    repo = _StubSettingsRepo(settings)
    checker = _StubHoldingChecker(has_holding)
    svc = OnboardingService(repo, checker)
    return svc, repo


# ── Tests ──────────────────────────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.asyncio
async def test_onboarding_required_when_empty_portfolio_not_skipped():
    """is_onboarding_required returns True when no holdings and not skipped."""
    svc, _ = _make_svc(has_holding=False)
    result = await svc.is_onboarding_required(uuid.uuid4(), uuid.uuid4())
    assert result is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_onboarding_not_required_after_skip():
    """is_onboarding_required returns False after mark_skipped."""
    tid = uuid.uuid4()
    uid = uuid.uuid4()
    svc, _ = _make_svc({"onboarding_skipped": True}, has_holding=False)
    result = await svc.is_onboarding_required(tid, uid)
    assert result is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_onboarding_not_required_after_holding():
    """is_onboarding_required returns False when user has at least one holding."""
    svc, _ = _make_svc(has_holding=True)
    result = await svc.is_onboarding_required(uuid.uuid4(), uuid.uuid4())
    assert result is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_select_scoring_profile_persists():
    """select_scoring_profile writes scoring_profile_id to settings."""
    tid = uuid.uuid4()
    uid = uuid.uuid4()
    profile_id = uuid.uuid4()

    svc, repo = _make_svc()
    await svc.select_scoring_profile(tid, uid, profile_id)

    settings = await repo.get_settings(tid, uid)
    assert settings.get("scoring_profile_id") == str(profile_id)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_mark_skipped_sets_flag():
    """mark_skipped sets onboarding_skipped=True in settings."""
    tid = uuid.uuid4()
    uid = uuid.uuid4()
    svc, repo = _make_svc()
    await svc.mark_skipped(tid, uid)

    settings = await repo.get_settings(tid, uid)
    assert settings.get("onboarding_skipped") is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_onboarding_state_includes_scoring_profile_id():
    """get_onboarding_state returns scoring_profile_id when set."""
    profile_id = uuid.uuid4()
    svc, _ = _make_svc({"scoring_profile_id": str(profile_id)}, has_holding=False)
    state = await svc.get_onboarding_state(uuid.uuid4(), uuid.uuid4())
    assert state.scoring_profile_id == profile_id


# ── Endpoint test ──────────────────────────────────────────────────────────────


TENANT_ID = uuid.uuid4()
USER_ID = uuid.uuid4()


def _fake_user() -> CurrentUser:
    return CurrentUser(
        user_id=USER_ID,
        tenant_id=TENANT_ID,
        role="end_user",
        email="test@test.com",
    )


@pytest.mark.integration
def test_onboarding_state_endpoint_returns_200():
    """GET /api/v1/onboarding/state returns 200 with OnboardingState."""
    mock_svc = AsyncMock()
    mock_svc.get_onboarding_state.return_value = OnboardingState(
        is_complete=False,
        skipped=False,
        has_holding=False,
        scoring_profile_id=None,
    )

    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[_get_onboarding_service] = lambda: mock_svc

    try:
        with TestClient(app) as client:
            resp = client.get("/api/v1/onboarding/state")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["is_complete"] is False
        assert data["skipped"] is False
    finally:
        app.dependency_overrides.clear()
