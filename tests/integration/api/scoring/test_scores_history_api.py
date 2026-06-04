"""Integration tests for GET /api/v1/scores/history endpoint.

PLAN-F-021 TASK-010
"""
from __future__ import annotations

import pytest
from unittest.mock import patch
from uuid import uuid4, UUID

pytestmark = pytest.mark.integration

ADMIN_TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")


def _make_jwt_token(role: str = "admin", tenant_id: UUID | None = None) -> str:
    """Create a minimal JWT token signed with the test secret."""
    from jose import jwt
    from datetime import datetime, timedelta

    payload = {
        "sub": str(uuid4()),
        "tenant_id": str(tenant_id or ADMIN_TENANT_ID),
        "role": role,
        "email": "test@example.com",
        "exp": datetime.utcnow() + timedelta(hours=1),
    }
    return jwt.encode(payload, "test-secret", algorithm="HS256")


def _make_app():
    from fastapi import FastAPI
    from src.api.v1.scoring.scores import router

    app = FastAPI()
    # router already has prefix="/scores"; mount at /api/v1 to get /api/v1/scores/...
    app.include_router(router, prefix="/api/v1")
    return app


def _patched_client():
    """Return a TestClient with get_settings patched to use test-secret."""
    from fastapi.testclient import TestClient

    app = _make_app()
    patcher = patch("src.api.auth_deps.get_settings")
    mock_settings = patcher.start()
    mock_settings.return_value.JWT_SECRET_KEY = "test-secret"
    client = TestClient(app)
    return client, patcher


class TestScoresHistoryAuth:
    def test_unauthenticated_request_returns_401(self):
        from fastapi.testclient import TestClient

        app = _make_app()
        with patch("src.api.auth_deps.get_settings"):
            with TestClient(app) as client:
                company_id = str(uuid4())
                response = client.get(
                    "/api/v1/scores/history",
                    params={"company_ids": company_id, "at": "2025-06-01T12:00:00Z"},
                )
        assert response.status_code == 401


class TestScoresHistoryValidation:
    def test_missing_at_parameter_returns_422(self):
        from fastapi.testclient import TestClient

        app = _make_app()
        with patch("src.api.auth_deps.get_settings") as mock_settings:
            mock_settings.return_value.JWT_SECRET_KEY = "test-secret"
            with TestClient(app) as client:
                token = _make_jwt_token()
                company_id = str(uuid4())
                response = client.get(
                    "/api/v1/scores/history",
                    params={"company_ids": company_id},
                    headers={"Authorization": f"Bearer {token}"},
                )
        assert response.status_code == 422

    def test_missing_company_ids_parameter_returns_422(self):
        from fastapi.testclient import TestClient

        app = _make_app()
        with patch("src.api.auth_deps.get_settings") as mock_settings:
            mock_settings.return_value.JWT_SECRET_KEY = "test-secret"
            with TestClient(app) as client:
                token = _make_jwt_token()
                response = client.get(
                    "/api/v1/scores/history",
                    params={"at": "2025-06-01T12:00:00Z"},
                    headers={"Authorization": f"Bearer {token}"},
                )
        assert response.status_code == 422

    def test_201_company_ids_returns_422(self):
        """More than MAX_COMPANY_IDS (200) should return 422."""
        from fastapi.testclient import TestClient

        app = _make_app()
        with patch("src.api.auth_deps.get_settings") as mock_settings:
            mock_settings.return_value.JWT_SECRET_KEY = "test-secret"
            with TestClient(app) as client:
                token = _make_jwt_token()
                ids = ",".join(str(uuid4()) for _ in range(201))
                response = client.get(
                    "/api/v1/scores/history",
                    params={"company_ids": ids, "at": "2025-06-01T12:00:00Z"},
                    headers={"Authorization": f"Bearer {token}"},
                )
        assert response.status_code == 422
        body = response.json()
        assert "200" in str(body)

    def test_valid_request_returns_200_with_data_envelope(self):
        """Valid request returns 200 with standard success envelope."""
        from fastapi.testclient import TestClient

        app = _make_app()
        with patch("src.api.auth_deps.get_settings") as mock_settings:
            mock_settings.return_value.JWT_SECRET_KEY = "test-secret"
            with TestClient(app) as client:
                token = _make_jwt_token()
                company_id = str(uuid4())
                response = client.get(
                    "/api/v1/scores/history",
                    params={
                        "company_ids": company_id,
                        "at": "2025-06-01T12:00:00Z",
                    },
                    headers={"Authorization": f"Bearer {token}"},
                )
        assert response.status_code == 200
        body = response.json()
        assert "data" in body
        assert body["error"] is None

    def test_invalid_at_datetime_returns_422(self):
        """Non-ISO-8601 'at' parameter should return 422."""
        from fastapi.testclient import TestClient

        app = _make_app()
        with patch("src.api.auth_deps.get_settings") as mock_settings:
            mock_settings.return_value.JWT_SECRET_KEY = "test-secret"
            with TestClient(app) as client:
                token = _make_jwt_token()
                company_id = str(uuid4())
                response = client.get(
                    "/api/v1/scores/history",
                    params={
                        "company_ids": company_id,
                        "at": "not-a-date",
                    },
                    headers={"Authorization": f"Bearer {token}"},
                )
        assert response.status_code == 422

    def test_stub_returns_empty_list_for_valid_request(self):
        """Stub implementation always returns empty list — repository not wired yet."""
        from fastapi.testclient import TestClient

        app = _make_app()
        with patch("src.api.auth_deps.get_settings") as mock_settings:
            mock_settings.return_value.JWT_SECRET_KEY = "test-secret"
            with TestClient(app) as client:
                token = _make_jwt_token()
                ids = ",".join([str(uuid4()), str(uuid4())])
                response = client.get(
                    "/api/v1/scores/history",
                    params={"company_ids": ids, "at": "2025-06-01T12:00:00Z"},
                    headers={"Authorization": f"Bearer {token}"},
                )
        assert response.status_code == 200
        assert response.json()["data"] == []

    def test_future_at_returns_200(self):
        """at in the future should still return 200 (empty if no data)."""
        from fastapi.testclient import TestClient

        app = _make_app()
        with patch("src.api.auth_deps.get_settings") as mock_settings:
            mock_settings.return_value.JWT_SECRET_KEY = "test-secret"
            with TestClient(app) as client:
                token = _make_jwt_token()
                company_id = str(uuid4())
                response = client.get(
                    "/api/v1/scores/history",
                    params={
                        "company_ids": company_id,
                        "at": "2099-01-01T00:00:00Z",
                    },
                    headers={"Authorization": f"Bearer {token}"},
                )
        assert response.status_code == 200
