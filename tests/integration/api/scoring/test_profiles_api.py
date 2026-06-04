"""Integration tests for scoring profile REST API endpoints."""
from __future__ import annotations

import pytest
from unittest.mock import patch
from uuid import uuid4, UUID

pytestmark = pytest.mark.integration

ADMIN_TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")


def _make_jwt_token(role: str = "admin", tenant_id: UUID | None = None):
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
    from src.api.v1.scoring.scoring_profiles import router
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/scoring-profiles")
    return app


class TestListProfiles:
    def test_list_requires_auth(self):
        from fastapi.testclient import TestClient
        app = _make_app()
        with TestClient(app) as client:
            response = client.get("/api/v1/scoring-profiles")
        assert response.status_code == 401

    def test_list_returns_200_for_authenticated_user(self):
        from fastapi.testclient import TestClient
        app = _make_app()
        with patch("src.api.auth.get_settings") as mock_settings:
            mock_settings.return_value.JWT_SECRET_KEY = "test-secret"
            with TestClient(app) as client:
                token = _make_jwt_token()
                response = client.get(
                    "/api/v1/scoring-profiles",
                    headers={"Authorization": f"Bearer {token}"},
                )
        assert response.status_code == 200
        data = response.json()
        assert "profiles" in data["data"]


class TestCreateProfile:
    def test_create_profile_returns_201(self):
        from fastapi.testclient import TestClient
        app = _make_app()
        indicator_id = uuid4()
        with patch("src.api.auth.get_settings") as mock_settings:
            mock_settings.return_value.JWT_SECRET_KEY = "test-secret"
            with TestClient(app) as client:
                token = _make_jwt_token(role="admin")
                response = client.post(
                    "/api/v1/scoring-profiles",
                    json={
                        "name": "My Custom Profile",
                        "indicators": [
                            {"indicator_id": str(indicator_id), "weight": 1.0}
                        ],
                    },
                    headers={"Authorization": f"Bearer {token}"},
                )
        assert response.status_code == 201
        data = response.json()
        assert "profile_id" in data["data"]

    def test_end_user_cannot_create_profile(self):
        from fastapi.testclient import TestClient
        app = _make_app()
        with patch("src.api.auth.get_settings") as mock_settings:
            mock_settings.return_value.JWT_SECRET_KEY = "test-secret"
            with TestClient(app) as client:
                token = _make_jwt_token(role="end_user")
                response = client.post(
                    "/api/v1/scoring-profiles",
                    json={"name": "Profile", "indicators": []},
                    headers={"Authorization": f"Bearer {token}"},
                )
        assert response.status_code == 403
