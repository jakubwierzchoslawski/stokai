"""Integration tests for GET /api/v1/events date-range filter.

PLAN-F-021 TASK-011
"""
from __future__ import annotations

import pytest
from unittest.mock import patch
from uuid import uuid4, UUID

pytestmark = pytest.mark.integration

ADMIN_TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")


def _make_jwt_token(role: str = "admin", tenant_id: UUID | None = None) -> str:
    import jwt
    from datetime import datetime, timedelta

    payload = {
        "sub": str(uuid4()),
        "tenant_id": str(tenant_id or ADMIN_TENANT_ID),
        "role": role,
        "exp": datetime.utcnow() + timedelta(hours=1),
    }
    return jwt.encode(payload, "test-secret", algorithm="HS256")


def _make_app():
    from fastapi import FastAPI
    from src.api.v1.events import router

    app = FastAPI()
    # router already has prefix="/events"; mount at /api/v1 to get /api/v1/events/...
    app.include_router(router, prefix="/api/v1")
    return app


class TestEventsRangeAuth:
    def test_unauthenticated_request_returns_401(self):
        from fastapi.testclient import TestClient

        app = _make_app()
        with TestClient(app) as client:
            response = client.get(
                "/api/v1/events",
                params={"from": "2025-01-01", "to": "2025-01-31"},
            )
        assert response.status_code == 401


class TestEventsRangeValidation:
    def _auth_client(self):
        from fastapi.testclient import TestClient

        app = _make_app()
        return TestClient(app), _make_jwt_token()

    def test_from_without_to_returns_422(self):
        from fastapi.testclient import TestClient

        app = _make_app()
        with patch("src.api.auth.get_settings") as mock_settings:
            mock_settings.return_value.JWT_SECRET_KEY = "test-secret"
            with TestClient(app) as client:
                token = _make_jwt_token()
                response = client.get(
                    "/api/v1/events",
                    params={"from": "2025-01-01"},
                    headers={"Authorization": f"Bearer {token}"},
                )
        assert response.status_code == 422

    def test_to_without_from_returns_422(self):
        from fastapi.testclient import TestClient

        app = _make_app()
        with patch("src.api.auth.get_settings") as mock_settings:
            mock_settings.return_value.JWT_SECRET_KEY = "test-secret"
            with TestClient(app) as client:
                token = _make_jwt_token()
                response = client.get(
                    "/api/v1/events",
                    params={"to": "2025-01-31"},
                    headers={"Authorization": f"Bearer {token}"},
                )
        assert response.status_code == 422

    def test_from_greater_than_to_returns_422(self):
        from fastapi.testclient import TestClient

        app = _make_app()
        with patch("src.api.auth.get_settings") as mock_settings:
            mock_settings.return_value.JWT_SECRET_KEY = "test-secret"
            with TestClient(app) as client:
                token = _make_jwt_token()
                response = client.get(
                    "/api/v1/events",
                    params={"from": "2025-01-31", "to": "2025-01-01"},
                    headers={"Authorization": f"Bearer {token}"},
                )
        assert response.status_code == 422
        body = response.json()
        assert "from_date" in str(body).lower() or "before" in str(body).lower()

    def test_valid_range_returns_200_with_data_envelope(self):
        from fastapi.testclient import TestClient

        app = _make_app()
        with patch("src.api.auth.get_settings") as mock_settings:
            mock_settings.return_value.JWT_SECRET_KEY = "test-secret"
            with TestClient(app) as client:
                token = _make_jwt_token()
                response = client.get(
                    "/api/v1/events",
                    params={"from": "2025-01-01", "to": "2025-01-31"},
                    headers={"Authorization": f"Bearer {token}"},
                )
        assert response.status_code == 200
        body = response.json()
        assert "data" in body
        assert body["error"] is None
        assert body["meta"]["from"] == "2025-01-01"
        assert body["meta"]["to"] == "2025-01-31"

    def test_no_range_params_returns_200_live_mode(self):
        """Without from/to the endpoint returns the live event list."""
        from fastapi.testclient import TestClient

        app = _make_app()
        with patch("src.api.auth.get_settings") as mock_settings:
            mock_settings.return_value.JWT_SECRET_KEY = "test-secret"
            with TestClient(app) as client:
                token = _make_jwt_token()
                response = client.get(
                    "/api/v1/events",
                    headers={"Authorization": f"Bearer {token}"},
                )
        assert response.status_code == 200
        body = response.json()
        assert "data" in body
        assert body["error"] is None
        # Live-mode meta does not contain 'from' or 'to'.
        assert "from" not in body.get("meta", {})

    def test_stub_returns_empty_list_for_range_request(self):
        """Repository stub always returns empty list."""
        from fastapi.testclient import TestClient

        app = _make_app()
        with patch("src.api.auth.get_settings") as mock_settings:
            mock_settings.return_value.JWT_SECRET_KEY = "test-secret"
            with TestClient(app) as client:
                token = _make_jwt_token()
                response = client.get(
                    "/api/v1/events",
                    params={"from": "2025-01-01", "to": "2025-01-31"},
                    headers={"Authorization": f"Bearer {token}"},
                )
        assert response.status_code == 200
        assert response.json()["data"] == []
