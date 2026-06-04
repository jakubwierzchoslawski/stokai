"""
Integration tests for GET /api/v1/alerts (PLAN-F-025 TASK-005).

Uses FastAPI TestClient with dependency_overrides to mock the repository.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.api.auth_deps import CurrentUser, get_current_user
from src.alerts.api.alerts_router import _get_alerts_repo
from src.alerts.schemas import AlertListItem


# ── Shared fixtures ────────────────────────────────────────────────────────────

TENANT_ID = uuid.uuid4()
USER_ID = uuid.uuid4()
OTHER_TENANT = uuid.uuid4()
OTHER_USER = uuid.uuid4()
EVENT_ID = uuid.uuid4()
ALERT_ID = uuid.uuid4()


def _fake_user(user_id=None, tenant_id=None) -> CurrentUser:
    return CurrentUser(
        user_id=user_id or USER_ID,
        tenant_id=tenant_id or TENANT_ID,
        role="end_user",
        email="test@test.com",
    )


def _make_alert_item(**overrides) -> AlertListItem:
    base = dict(
        alert_id=ALERT_ID,
        occurred_at=datetime(2026, 1, 10, 9, 0, tzinfo=timezone.utc),
        event_title="US Trade Policy Shift",
        action_signal="BUY_OPP",
        confidence=0.82,
        channel="email",
        status="dispatched",
        event_link=f"/map?event={EVENT_ID}&lat=38.9&lon=-77.0",
        report_link=None,
    )
    base.update(overrides)
    return AlertListItem(**base)


def _make_repo_mock(items=None, total=0):
    repo = MagicMock()
    repo.list_alerts = AsyncMock(return_value=(items or [], total))
    return repo


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_authenticated_user_gets_200():
    """Authenticated user → 200."""
    app.dependency_overrides[get_current_user] = lambda: _fake_user()
    app.dependency_overrides[_get_alerts_repo] = lambda: _make_repo_mock()

    with TestClient(app) as client:
        resp = client.get("/api/v1/alerts")

    app.dependency_overrides.clear()
    assert resp.status_code == 200


def test_unauthenticated_gets_401():
    """No Bearer token → 401."""
    app.dependency_overrides.clear()  # real auth

    with TestClient(app) as client:
        resp = client.get("/api/v1/alerts")

    assert resp.status_code == 401


def test_status_filter_passed_to_repo():
    """?status=dispatched is forwarded to the repo."""
    repo = _make_repo_mock()
    app.dependency_overrides[get_current_user] = lambda: _fake_user()
    app.dependency_overrides[_get_alerts_repo] = lambda: repo

    with TestClient(app) as client:
        client.get("/api/v1/alerts?status=dispatched")

    app.dependency_overrides.clear()
    call_kwargs = repo.list_alerts.call_args[1]
    assert call_kwargs["status"] == "dispatched"


def test_action_signal_filter_passed_to_repo():
    """?action_signal=BUY_OPP is forwarded to the repo."""
    repo = _make_repo_mock()
    app.dependency_overrides[get_current_user] = lambda: _fake_user()
    app.dependency_overrides[_get_alerts_repo] = lambda: repo

    with TestClient(app) as client:
        client.get("/api/v1/alerts?action_signal=BUY_OPP")

    app.dependency_overrides.clear()
    call_kwargs = repo.list_alerts.call_args[1]
    assert call_kwargs["action_signal"] == "BUY_OPP"


def test_date_range_filter_passed_to_repo():
    """?date_from and ?date_to are forwarded to the repo."""
    repo = _make_repo_mock()
    app.dependency_overrides[get_current_user] = lambda: _fake_user()
    app.dependency_overrides[_get_alerts_repo] = lambda: repo

    with TestClient(app) as client:
        client.get("/api/v1/alerts?date_from=2026-01-01T00:00:00Z&date_to=2026-01-31T23:59:59Z")

    app.dependency_overrides.clear()
    call_kwargs = repo.list_alerts.call_args[1]
    assert call_kwargs["date_from"] is not None
    assert call_kwargs["date_to"] is not None


def test_page_size_zero_returns_422():
    """page_size=0 → 422 Unprocessable Entity."""
    app.dependency_overrides[get_current_user] = lambda: _fake_user()
    app.dependency_overrides[_get_alerts_repo] = lambda: _make_repo_mock()

    with TestClient(app) as client:
        resp = client.get("/api/v1/alerts?page_size=0")

    app.dependency_overrides.clear()
    assert resp.status_code == 422


def test_page_size_101_returns_422():
    """page_size=101 → 422 (max is 100)."""
    app.dependency_overrides[get_current_user] = lambda: _fake_user()
    app.dependency_overrides[_get_alerts_repo] = lambda: _make_repo_mock()

    with TestClient(app) as client:
        resp = client.get("/api/v1/alerts?page_size=101")

    app.dependency_overrides.clear()
    assert resp.status_code == 422


def test_event_link_pattern_in_response():
    """Response items contain event_link with /map?event= pattern."""
    item = _make_alert_item(
        event_link=f"/map?event={EVENT_ID}&lat=38.9&lon=-77.0"
    )
    repo = _make_repo_mock(items=[item], total=1)
    app.dependency_overrides[get_current_user] = lambda: _fake_user()
    app.dependency_overrides[_get_alerts_repo] = lambda: repo

    with TestClient(app) as client:
        resp = client.get("/api/v1/alerts")

    app.dependency_overrides.clear()
    body = resp.json()
    assert "/map?event=" in body["items"][0]["event_link"]


def test_empty_response_returns_200_with_empty_list():
    """Empty result → 200 with items=[] total=0."""
    repo = _make_repo_mock(items=[], total=0)
    app.dependency_overrides[get_current_user] = lambda: _fake_user()
    app.dependency_overrides[_get_alerts_repo] = lambda: repo

    with TestClient(app) as client:
        resp = client.get("/api/v1/alerts")

    app.dependency_overrides.clear()
    body = resp.json()
    assert resp.status_code == 200
    assert body["items"] == []
    assert body["total"] == 0


def test_other_tenant_not_returned():
    """Repo is always called with the authenticated user's tenant_id."""
    repo = _make_repo_mock()
    app.dependency_overrides[get_current_user] = lambda: _fake_user(
        user_id=OTHER_USER, tenant_id=OTHER_TENANT
    )
    app.dependency_overrides[_get_alerts_repo] = lambda: repo

    with TestClient(app) as client:
        client.get("/api/v1/alerts")

    app.dependency_overrides.clear()
    call_kwargs = repo.list_alerts.call_args[1]
    assert call_kwargs["tenant_id"] == OTHER_TENANT
    assert call_kwargs["user_id"] == OTHER_USER
