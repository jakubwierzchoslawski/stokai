"""
Integration tests for watchlist scan API endpoints.

TDD: written before implementation — PLAN-F-008 TASK-008.

Endpoints tested:
  GET /api/v1/briefs/watchlist — returns most recent watchlist_scan brief

Tests:
  - 200 response with brief data
  - 404 when no brief found
  - JWT required (401/403/422 without auth)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.v1.watchlist_scan_router import router as watchlist_scan_router


def _make_current_user(
    user_id: uuid.UUID | None = None,
    tenant_id: uuid.UUID | None = None,
) -> MagicMock:
    user = MagicMock()
    user.user_id = user_id or uuid.uuid4()
    user.tenant_id = tenant_id or uuid.uuid4()
    user.role = "analyst"
    return user


def _make_brief_dict(
    tenant_id: uuid.UUID | None = None,
) -> dict:
    return {
        "brief_id": uuid.uuid4(),
        "type": "watchlist_scan",
        "tenant_id": str(tenant_id or uuid.uuid4()),
        "content": {"headline": "Afternoon scan complete", "sections": ["overview"]},
        "confidence": 0.82,
        "cost_usd": 0.45,
        "cost_limited": False,
        "hil_reviewed": False,
        "hil_approved": None,
        "created_at": datetime.now(tz=timezone.utc),
    }


class TestGetWatchlistBriefEndpoint:
    def test_returns_200_with_brief_data(self):
        """GET /api/v1/briefs/watchlist returns 200 with brief data."""
        from src.api.auth_deps import get_current_user

        app = FastAPI()
        app.include_router(watchlist_scan_router)

        tenant_id = uuid.uuid4()
        mock_user = _make_current_user(tenant_id=tenant_id)
        brief_data = _make_brief_dict(tenant_id=tenant_id)

        app.dependency_overrides[get_current_user] = lambda: mock_user

        with patch(
            "src.api.v1.watchlist_scan_router._get_latest_watchlist_brief",
            new=AsyncMock(return_value=brief_data),
        ):
            client = TestClient(app, raise_server_exceptions=False)
            response = client.get("/briefs/watchlist")

        assert response.status_code == 200
        body = response.json()
        assert "data" in body
        assert body["data"]["type"] == "watchlist_scan"

    def test_returns_404_when_no_brief_found(self):
        """GET /api/v1/briefs/watchlist returns 404 when no brief exists."""
        from src.api.auth_deps import get_current_user

        app = FastAPI()
        app.include_router(watchlist_scan_router)

        mock_user = _make_current_user()
        app.dependency_overrides[get_current_user] = lambda: mock_user

        with patch(
            "src.api.v1.watchlist_scan_router._get_latest_watchlist_brief",
            new=AsyncMock(return_value=None),
        ):
            client = TestClient(app, raise_server_exceptions=False)
            response = client.get("/briefs/watchlist")

        assert response.status_code == 404

    def test_returns_401_without_authentication(self):
        """GET /api/v1/briefs/watchlist without JWT → 401/403/422."""
        app = FastAPI()
        app.include_router(watchlist_scan_router)

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/briefs/watchlist")

        assert response.status_code in (401, 403, 422)

    def test_response_includes_confidence_field(self):
        """Response body must include confidence field."""
        from src.api.auth_deps import get_current_user

        app = FastAPI()
        app.include_router(watchlist_scan_router)

        tenant_id = uuid.uuid4()
        mock_user = _make_current_user(tenant_id=tenant_id)
        brief_data = _make_brief_dict(tenant_id=tenant_id)

        app.dependency_overrides[get_current_user] = lambda: mock_user

        with patch(
            "src.api.v1.watchlist_scan_router._get_latest_watchlist_brief",
            new=AsyncMock(return_value=brief_data),
        ):
            client = TestClient(app, raise_server_exceptions=False)
            response = client.get("/briefs/watchlist")

        body = response.json()
        assert "confidence" in body["data"]
        assert body["data"]["confidence"] == 0.82

    def test_404_includes_error_code(self):
        """404 response must include WATCHLIST_BRIEF_NOT_FOUND code."""
        from src.api.auth_deps import get_current_user

        app = FastAPI()
        app.include_router(watchlist_scan_router)

        mock_user = _make_current_user()
        app.dependency_overrides[get_current_user] = lambda: mock_user

        with patch(
            "src.api.v1.watchlist_scan_router._get_latest_watchlist_brief",
            new=AsyncMock(return_value=None),
        ):
            client = TestClient(app, raise_server_exceptions=False)
            response = client.get("/briefs/watchlist")

        body = response.json()
        assert body.get("detail", {}).get("code") == "WATCHLIST_BRIEF_NOT_FOUND"

    def test_response_includes_brief_id_as_string(self):
        """Response brief_id must be a string (JSON-serializable UUID)."""
        from src.api.auth_deps import get_current_user

        app = FastAPI()
        app.include_router(watchlist_scan_router)

        tenant_id = uuid.uuid4()
        mock_user = _make_current_user(tenant_id=tenant_id)
        brief_data = _make_brief_dict(tenant_id=tenant_id)

        app.dependency_overrides[get_current_user] = lambda: mock_user

        with patch(
            "src.api.v1.watchlist_scan_router._get_latest_watchlist_brief",
            new=AsyncMock(return_value=brief_data),
        ):
            client = TestClient(app, raise_server_exceptions=False)
            response = client.get("/briefs/watchlist")

        body = response.json()
        assert isinstance(body["data"]["brief_id"], str)
