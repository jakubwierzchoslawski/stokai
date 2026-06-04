"""
Unit tests for ProgressiveDisclosure FastAPI router.

PLAN-F-020 TASK-004 (TDD)

Uses FastAPI TestClient with dependency_overrides. No real DB calls are made.
All service calls are mocked via AsyncMock.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.auth_deps import CurrentUser, get_current_user
from src.api.progressive_disclosure.router import _get_service, router
from src.api.progressive_disclosure.schemas import (
    AuditTrailResponse,
    DeepDiveResponse,
    PopupDataResponse,
    ReasoningStepSchema,
    SidePanelDataResponse,
    TickerDeltaSchema,
)
from src.api.progressive_disclosure.service import (
    DeepDiveNotReadyError,
    EventNotFoundError,
    ProgressiveDisclosureService,
)


# ── Test app setup ─────────────────────────────────────────────────────────────

test_app = FastAPI()
test_app.include_router(router, prefix="/api/v1")

EVENT_ID = uuid.uuid4()
TENANT_ID = uuid.uuid4()
USER_ID = uuid.uuid4()
NOW = datetime.now(tz=timezone.utc)


def _make_user() -> CurrentUser:
    return CurrentUser(
        user_id=USER_ID,
        tenant_id=TENANT_ID,
        role="end_user",
        email="test@example.com",
    )


def _make_popup_response() -> PopupDataResponse:
    return PopupDataResponse(
        event_id=EVENT_ID,
        category=["GEOPOLITICAL"],
        intensity=3,
        headline="Test event",
        time_ago="5 minutes ago",
        location="Middle East",
        exposed_holdings_count=2,
        tickers_with_delta=[TickerDeltaSchema(ticker="AAPL", score_delta=1.5)],
        action_signal="WATCH",
        confidence=0.75,
        sample_size=8,
        low_sample=False,
    )


def _make_side_panel_response(is_contrarian: bool = False) -> SidePanelDataResponse:
    return SidePanelDataResponse(
        event_id=EVENT_ID,
        category=["GEOPOLITICAL"],
        intensity=3,
        headline="Test event",
        time_ago="5 minutes ago",
        location="Middle East",
        exposed_holdings_count=2,
        tickers_with_delta=[TickerDeltaSchema(ticker="AAPL", score_delta=1.5)],
        action_signal="WATCH",
        confidence=0.75,
        sample_size=8,
        low_sample=False,
        summary="Summary text",
        sparklines=[],
        rationale="Rationale text",
        analogies=[],
        affected_companies=[],
        is_contrarian=is_contrarian,
        contrarian_callout="History says X" if is_contrarian else None,
        social_posts=None,
        audit_trail_url=f"/events/{EVENT_ID}/audit-trail",
    )


def _make_audit_trail_response() -> AuditTrailResponse:
    return AuditTrailResponse(
        event_id=EVENT_ID,
        prompt_version="abc123def456",
        langfuse_trace_url="https://langfuse/traces/xyz",
        analogies=[],
        reasoning_steps=[
            ReasoningStepSchema(
                agent_role="recommendation_synthesizer",
                step_index=0,
                content="Signal: WATCH",
                tool_calls=["analogy_lookup"],
            )
        ],
    )


def _make_deep_dive_response() -> DeepDiveResponse:
    return DeepDiveResponse(
        event_id=EVENT_ID,
        memo="Full analysis memo.",
        scenario_tree=None,
        analogies=[],
        affected_companies=[],
        generated_at=NOW,
    )


# ── GET /popup ─────────────────────────────────────────────────────────────────


def test_get_popup_returns_200_with_correct_shape() -> None:
    """GET /popup with valid JWT and existing event returns 200 with PopupDataResponse."""
    mock_service = MagicMock(spec=ProgressiveDisclosureService)
    mock_service.get_popup = AsyncMock(return_value=_make_popup_response())

    test_app.dependency_overrides[get_current_user] = lambda: _make_user()
    test_app.dependency_overrides[_get_service] = lambda: mock_service

    client = TestClient(test_app)
    resp = client.get(f"/api/v1/events/{EVENT_ID}/popup")

    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["event_id"] == str(EVENT_ID)
    assert body["data"]["action_signal"] == "WATCH"
    assert body["data"]["confidence"] == pytest.approx(0.75)
    assert body["error"] is None

    test_app.dependency_overrides.clear()


def test_get_popup_without_jwt_returns_401() -> None:
    """GET /popup without JWT returns 401."""
    # No dependency override — get_current_user raises 401 by default
    client = TestClient(test_app, raise_server_exceptions=False)
    resp = client.get(f"/api/v1/events/{EVENT_ID}/popup")
    assert resp.status_code == 401


def test_get_popup_for_foreign_tenant_returns_404() -> None:
    """GET /popup for an event belonging to a different tenant returns 404."""
    mock_service = MagicMock(spec=ProgressiveDisclosureService)
    mock_service.get_popup = AsyncMock(side_effect=EventNotFoundError(EVENT_ID))

    test_app.dependency_overrides[get_current_user] = lambda: _make_user()
    test_app.dependency_overrides[_get_service] = lambda: mock_service

    client = TestClient(test_app)
    resp = client.get(f"/api/v1/events/{EVENT_ID}/popup")

    assert resp.status_code == 404

    test_app.dependency_overrides.clear()


# ── GET /audit-trail ──────────────────────────────────────────────────────────


def test_get_audit_trail_returns_200_with_prompt_version_and_steps() -> None:
    """GET /audit-trail returns 200 with prompt_version SHA and non-empty reasoning_steps."""
    mock_service = MagicMock(spec=ProgressiveDisclosureService)
    mock_service.get_audit_trail = AsyncMock(return_value=_make_audit_trail_response())

    test_app.dependency_overrides[get_current_user] = lambda: _make_user()
    test_app.dependency_overrides[_get_service] = lambda: mock_service

    client = TestClient(test_app)
    resp = client.get(f"/api/v1/events/{EVENT_ID}/audit-trail")

    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["prompt_version"] == "abc123def456"
    assert len(body["data"]["reasoning_steps"]) == 1
    assert body["data"]["reasoning_steps"][0]["agent_role"] == "recommendation_synthesizer"

    test_app.dependency_overrides.clear()


# ── GET /deep-dive ────────────────────────────────────────────────────────────


def test_get_deep_dive_returns_202_when_pending() -> None:
    """GET /deep-dive when no workflow has completed returns 202 with {"status":"pending"}."""
    mock_service = MagicMock(spec=ProgressiveDisclosureService)
    mock_service.get_deep_dive = AsyncMock(side_effect=DeepDiveNotReadyError(EVENT_ID))

    test_app.dependency_overrides[get_current_user] = lambda: _make_user()
    test_app.dependency_overrides[_get_service] = lambda: mock_service

    client = TestClient(test_app)
    resp = client.get(f"/api/v1/events/{EVENT_ID}/deep-dive")

    assert resp.status_code == 202
    assert resp.json()["status"] == "pending"

    test_app.dependency_overrides.clear()


def test_get_deep_dive_returns_200_when_complete() -> None:
    """GET /deep-dive returns 200 with DeepDiveResponse when workflow has completed."""
    mock_service = MagicMock(spec=ProgressiveDisclosureService)
    mock_service.get_deep_dive = AsyncMock(return_value=_make_deep_dive_response())

    test_app.dependency_overrides[get_current_user] = lambda: _make_user()
    test_app.dependency_overrides[_get_service] = lambda: mock_service

    client = TestClient(test_app)
    resp = client.get(f"/api/v1/events/{EVENT_ID}/deep-dive")

    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["memo"] == "Full analysis memo."

    test_app.dependency_overrides.clear()


# ── GET /side-panel ───────────────────────────────────────────────────────────


def test_get_side_panel_contrarian_callout_non_null_when_is_contrarian() -> None:
    """GET /side-panel with is_contrarian=True returns contrarian_callout as non-null string."""
    mock_service = MagicMock(spec=ProgressiveDisclosureService)
    mock_service.get_side_panel = AsyncMock(return_value=_make_side_panel_response(is_contrarian=True))

    test_app.dependency_overrides[get_current_user] = lambda: _make_user()
    test_app.dependency_overrides[_get_service] = lambda: mock_service

    client = TestClient(test_app)
    resp = client.get(f"/api/v1/events/{EVENT_ID}/side-panel")

    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["is_contrarian"] is True
    assert body["data"]["contrarian_callout"] is not None
    assert len(body["data"]["contrarian_callout"]) > 0

    test_app.dependency_overrides.clear()
