"""
Integration tests for Alert Rules CRUD API (PLAN-F-025 TASK-006).

Uses FastAPI TestClient with dependency_overrides.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.api.auth_deps import CurrentUser, get_current_user
from src.alerts.api.alert_rules_router import _get_alert_rule_manager
from src.alerts.exceptions import NotFoundError, ValidationError
from src.alerts.schemas import AlertRuleResponse


# ── Fixtures ───────────────────────────────────────────────────────────────────

TENANT_ID = uuid.uuid4()
USER_ID = uuid.uuid4()
RULE_ID = uuid.uuid4()


def _fake_user() -> CurrentUser:
    return CurrentUser(
        user_id=USER_ID,
        tenant_id=TENANT_ID,
        role="end_user",
        email="test@test.com",
    )


def _make_rule_response(rule_id=None) -> AlertRuleResponse:
    return AlertRuleResponse(
        rule_id=rule_id or RULE_ID,
        user_id=USER_ID,
        name="My Rule",
        enabled=True,
        event_category_filter=["conflict"],
        intensity_min=2,
        ticker_list=["AAPL"],
        quiet_hours_start=None,
        quiet_hours_end=None,
        per_ticker_interval_hours=24,
        channels=["email"],
    )


def _make_manager_mock(
    list_rules_returns=None,
    create_rule_returns=None,
    create_rule_raises=None,
    update_rule_raises=None,
    delete_rule_raises=None,
):
    manager = MagicMock()
    manager.list_rules = AsyncMock(return_value=list_rules_returns or [])
    if create_rule_raises:
        manager.create_rule = AsyncMock(side_effect=create_rule_raises)
    else:
        manager.create_rule = AsyncMock(return_value=create_rule_returns or uuid.uuid4())
    if update_rule_raises:
        manager.update_rule = AsyncMock(side_effect=update_rule_raises)
    else:
        manager.update_rule = AsyncMock()
    if delete_rule_raises:
        manager.delete_rule = AsyncMock(side_effect=delete_rule_raises)
    else:
        manager.delete_rule = AsyncMock()
    return manager


def _valid_create_body():
    return {
        "name": "Test Rule",
        "intensity_min": 2,
        "channels": ["email"],
        "event_category_filter": ["conflict"],
        "ticker_list": ["AAPL"],
        "per_ticker_interval_hours": 24,
    }


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_get_rules_returns_200_with_rules():
    """GET /api/v1/alert-rules → 200 with list of rules."""
    rules = [_make_rule_response()]
    manager = _make_manager_mock(list_rules_returns=rules)
    app.dependency_overrides[get_current_user] = lambda: _fake_user()
    app.dependency_overrides[_get_alert_rule_manager] = lambda: manager

    with TestClient(app) as client:
        resp = client.get("/api/v1/alert-rules")

    app.dependency_overrides.clear()
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["data"]) == 1


def test_get_rules_unauthenticated_returns_401():
    """GET without token → 401."""
    app.dependency_overrides.clear()

    with TestClient(app) as client:
        resp = client.get("/api/v1/alert-rules")

    assert resp.status_code == 401


def test_post_valid_rule_returns_201_with_rule_id():
    """POST valid rule → 201 with rule_id."""
    new_rule_id = uuid.uuid4()
    manager = _make_manager_mock(create_rule_returns=new_rule_id)
    app.dependency_overrides[get_current_user] = lambda: _fake_user()
    app.dependency_overrides[_get_alert_rule_manager] = lambda: manager

    with TestClient(app) as client:
        resp = client.post("/api/v1/alert-rules", json=_valid_create_body())

    app.dependency_overrides.clear()
    assert resp.status_code == 201
    body = resp.json()
    assert "rule_id" in body["data"]


def test_post_intensity_min_6_returns_422():
    """POST with intensity_min=6 → 422 (validation error from manager)."""
    manager = _make_manager_mock(create_rule_raises=ValidationError("intensity_min must be between 1 and 5"))
    app.dependency_overrides[get_current_user] = lambda: _fake_user()
    app.dependency_overrides[_get_alert_rule_manager] = lambda: manager

    body = {**_valid_create_body(), "intensity_min": 6}
    with TestClient(app) as client:
        resp = client.post("/api/v1/alert-rules", json=body)

    app.dependency_overrides.clear()
    assert resp.status_code == 422


def test_patch_enabled_false_returns_200():
    """PATCH {enabled: false} → 200."""
    manager = _make_manager_mock()
    app.dependency_overrides[get_current_user] = lambda: _fake_user()
    app.dependency_overrides[_get_alert_rule_manager] = lambda: manager

    with TestClient(app) as client:
        resp = client.patch(f"/api/v1/alert-rules/{RULE_ID}", json={"enabled": False})

    app.dependency_overrides.clear()
    assert resp.status_code == 200


def test_patch_quiet_hours_updates_both():
    """PATCH with quiet_hours_start and quiet_hours_end → 200."""
    manager = _make_manager_mock()
    app.dependency_overrides[get_current_user] = lambda: _fake_user()
    app.dependency_overrides[_get_alert_rule_manager] = lambda: manager

    with TestClient(app) as client:
        resp = client.patch(
            f"/api/v1/alert-rules/{RULE_ID}",
            json={"quiet_hours_start": "22:00", "quiet_hours_end": "06:00"},
        )

    app.dependency_overrides.clear()
    assert resp.status_code == 200
    kwargs = manager.update_rule.call_args[1]
    assert kwargs["request"].quiet_hours_start == "22:00"
    assert kwargs["request"].quiet_hours_end == "06:00"


def test_patch_non_existent_returns_404():
    """PATCH rule that doesn't exist → 404."""
    manager = _make_manager_mock(
        update_rule_raises=NotFoundError("AlertRule", RULE_ID)
    )
    app.dependency_overrides[get_current_user] = lambda: _fake_user()
    app.dependency_overrides[_get_alert_rule_manager] = lambda: manager

    with TestClient(app) as client:
        resp = client.patch(f"/api/v1/alert-rules/{RULE_ID}", json={"enabled": True})

    app.dependency_overrides.clear()
    assert resp.status_code == 404


def test_delete_own_rule_returns_204():
    """DELETE existing rule → 204."""
    manager = _make_manager_mock()
    app.dependency_overrides[get_current_user] = lambda: _fake_user()
    app.dependency_overrides[_get_alert_rule_manager] = lambda: manager

    with TestClient(app) as client:
        resp = client.delete(f"/api/v1/alert-rules/{RULE_ID}")

    app.dependency_overrides.clear()
    assert resp.status_code == 204


def test_delete_non_existent_returns_404():
    """DELETE non-existent rule → 404."""
    manager = _make_manager_mock(
        delete_rule_raises=NotFoundError("AlertRule", RULE_ID)
    )
    app.dependency_overrides[get_current_user] = lambda: _fake_user()
    app.dependency_overrides[_get_alert_rule_manager] = lambda: manager

    with TestClient(app) as client:
        resp = client.delete(f"/api/v1/alert-rules/{RULE_ID}")

    app.dependency_overrides.clear()
    assert resp.status_code == 404


def test_post_missing_required_fields_returns_422():
    """POST without required fields → 422 (Pydantic validation)."""
    manager = _make_manager_mock()
    app.dependency_overrides[get_current_user] = lambda: _fake_user()
    app.dependency_overrides[_get_alert_rule_manager] = lambda: manager

    with TestClient(app) as client:
        resp = client.post("/api/v1/alert-rules", json={})  # missing name, intensity_min, channels

    app.dependency_overrides.clear()
    assert resp.status_code == 422
