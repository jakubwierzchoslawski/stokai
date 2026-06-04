"""
Unit tests for briefs_router and feedback_router (PLAN-F-026 TASK-004).

TDD — all tests written before implementation. JWT and service dependencies mocked.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.briefs.briefs_router import _get_brief_service, router as briefs_router
from src.api.briefs.feedback_router import (
    _get_feedback_service,
    _get_brief_service_for_feedback,
    router as feedback_router,
)
from src.api.auth_deps import CurrentUser, get_current_user
from src.briefs.schemas.brief_schemas import BriefListResult, BriefProjection, BriefType
from src.briefs.services.brief_service import BriefNotFoundError


# ── Fixtures ──────────────────────────────────────────────────────────────────

TENANT_ID = uuid.uuid4()
USER_ID = uuid.uuid4()
BRIEF_ID = uuid.uuid4()
FEEDBACK_ID = uuid.uuid4()


def _make_current_user() -> CurrentUser:
    return CurrentUser(
        user_id=USER_ID,
        tenant_id=TENANT_ID,
        role="end_user",
        email="test@example.com",
    )


def _make_projection(
    brief_id: uuid.UUID = None,
    confidence: float = 0.82,
    low_sample: bool = False,
) -> BriefProjection:
    return BriefProjection(
        brief_id=brief_id or BRIEF_ID,
        type=BriefType.morning_brief,
        headline="Market outlook",
        content_html="<p>Content here</p>",
        confidence=confidence,
        sample_size=10 if not low_sample else 3,
        low_sample=low_sample,
        delivery_status="COMPLETED",
        sent_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )


def _make_app_with_overrides(
    mock_service=None, mock_feedback_service=None, mock_brief_for_feedback=None
) -> tuple[FastAPI, TestClient]:
    app = FastAPI()
    app.include_router(briefs_router, prefix="/api/v1")
    app.include_router(feedback_router, prefix="/api/v1")

    app.dependency_overrides[get_current_user] = lambda: _make_current_user()

    if mock_service is not None:
        app.dependency_overrides[_get_brief_service] = lambda: mock_service

    if mock_feedback_service is not None:
        app.dependency_overrides[_get_feedback_service] = lambda: mock_feedback_service

    if mock_brief_for_feedback is not None:
        app.dependency_overrides[_get_brief_service_for_feedback] = lambda: mock_brief_for_feedback

    client = TestClient(app, raise_server_exceptions=False)
    return app, client


# ── GET /api/v1/briefs ────────────────────────────────────────────────────────


def test_list_briefs_returns_200_with_items():
    """GET /api/v1/briefs returns 200 with items list."""
    projections = [_make_projection() for _ in range(3)]
    mock_service = AsyncMock()
    mock_service.list_briefs = AsyncMock(
        return_value=BriefListResult(items=projections, next_cursor=None)
    )

    _, client = _make_app_with_overrides(mock_service=mock_service)
    resp = client.get("/api/v1/briefs")

    assert resp.status_code == 200
    body = resp.json()
    assert body["error"] is None
    assert len(body["data"]["items"]) == 3


def test_list_briefs_type_filter_passed_to_service():
    """?type=morning_brief is passed to service.list_briefs as BriefType enum."""
    mock_service = AsyncMock()
    mock_service.list_briefs = AsyncMock(
        return_value=BriefListResult(items=[], next_cursor=None)
    )

    _, client = _make_app_with_overrides(mock_service=mock_service)
    resp = client.get("/api/v1/briefs?type=morning_brief")

    assert resp.status_code == 200
    call_kwargs = mock_service.list_briefs.call_args[1]
    assert call_kwargs["brief_type"] == BriefType.morning_brief


# ── GET /api/v1/briefs/{id} ───────────────────────────────────────────────────


def test_get_brief_detail_returns_200_with_confidence():
    """GET /api/v1/briefs/{id} returns 200 with confidence field."""
    projection = _make_projection(brief_id=BRIEF_ID, confidence=0.82)
    mock_service = AsyncMock()
    mock_service.get_brief_detail = AsyncMock(return_value=projection)

    _, client = _make_app_with_overrides(mock_service=mock_service)
    resp = client.get(f"/api/v1/briefs/{BRIEF_ID}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["confidence"] == pytest.approx(0.82)
    assert body["error"] is None


def test_get_brief_detail_returns_404_on_not_found():
    """GET /api/v1/briefs/{id} returns 404 when service raises BriefNotFoundError."""
    mock_service = AsyncMock()
    mock_service.get_brief_detail = AsyncMock(
        side_effect=BriefNotFoundError("not found")
    )

    _, client = _make_app_with_overrides(mock_service=mock_service)
    resp = client.get(f"/api/v1/briefs/{BRIEF_ID}")

    assert resp.status_code == 404


# ── POST /api/v1/briefs/{id}/feedback ────────────────────────────────────────


def test_post_feedback_thumbs_down_returns_201():
    """POST thumbs_down feedback returns 201 with feedback_id."""
    mock_feedback_svc = AsyncMock()
    mock_feedback_svc.submit_feedback = AsyncMock(return_value=FEEDBACK_ID)

    mock_brief_svc = AsyncMock()
    mock_brief_svc.get_brief_detail = AsyncMock(return_value=_make_projection())

    _, client = _make_app_with_overrides(
        mock_feedback_service=mock_feedback_svc,
        mock_brief_for_feedback=mock_brief_svc,
    )

    resp = client.post(
        f"/api/v1/briefs/{BRIEF_ID}/feedback",
        json={"feedback_type": "thumbs_down"},
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["data"]["feedback_id"] == str(FEEDBACK_ID)


def test_post_feedback_edit_without_correction_returns_422():
    """POST edit feedback without correction returns 422."""
    mock_feedback_svc = AsyncMock()
    mock_brief_svc = AsyncMock()

    _, client = _make_app_with_overrides(
        mock_feedback_service=mock_feedback_svc,
        mock_brief_for_feedback=mock_brief_svc,
    )

    resp = client.post(
        f"/api/v1/briefs/{BRIEF_ID}/feedback",
        json={"feedback_type": "edit", "correction": None},
    )

    assert resp.status_code == 422


def test_post_feedback_requires_auth():
    """POST feedback without JWT returns 401."""
    app = FastAPI()
    app.include_router(feedback_router, prefix="/api/v1")
    # No auth override — uses real get_current_user which requires a token

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post(
        f"/api/v1/briefs/{BRIEF_ID}/feedback",
        json={"feedback_type": "thumbs_down"},
    )

    assert resp.status_code in (401, 403)
