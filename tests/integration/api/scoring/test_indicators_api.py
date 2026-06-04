"""Integration tests for indicator REST API endpoints.

Uses FastAPI TestClient. Tests JWT auth, DSL validation, and indicator CRUD.
"""
from __future__ import annotations

import time
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from uuid import uuid4, UUID

pytestmark = pytest.mark.integration

TENANT_ID = str(uuid4())
ADMIN_TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")


def _make_jwt_token(role: str = "admin", tenant_id: UUID | None = None):
    """Create a minimal JWT token for testing."""
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
    """Create a minimal FastAPI app for testing."""
    from fastapi import FastAPI
    from src.api.v1.scoring.indicators import router

    app = FastAPI()
    app.include_router(router, prefix="/api/v1/indicators")
    return app


class TestValidateDsl:
    def test_valid_dsl_returns_200_valid_true(self):
        from fastapi.testclient import TestClient
        from unittest.mock import patch, AsyncMock

        app = _make_app()

        with patch("src.api.auth.get_settings") as mock_settings:
            mock_settings.return_value.JWT_SECRET_KEY = "test-secret"
            with TestClient(app) as client:
                token = _make_jwt_token()
                response = client.post(
                    "/api/v1/indicators/validate",
                    json={"formula_dsl": "revenue * 0.5"},
                    headers={"Authorization": f"Bearer {token}"},
                )
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["valid"] is True
        assert data["data"]["errors"] == []

    def test_invalid_dsl_returns_200_valid_false(self):
        from fastapi.testclient import TestClient

        app = _make_app()

        with patch("src.api.auth.get_settings") as mock_settings:
            mock_settings.return_value.JWT_SECRET_KEY = "test-secret"
            with TestClient(app) as client:
                token = _make_jwt_token()
                response = client.post(
                    "/api/v1/indicators/validate",
                    json={"formula_dsl": "revenue + * bad"},
                    headers={"Authorization": f"Bearer {token}"},
                )
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["valid"] is False
        assert len(data["data"]["errors"]) > 0

    def test_no_auth_returns_401(self):
        from fastapi.testclient import TestClient

        app = _make_app()

        with TestClient(app) as client:
            response = client.post(
                "/api/v1/indicators/validate",
                json={"formula_dsl": "revenue"},
            )
        assert response.status_code == 401


class TestCreateIndicator:
    def test_create_returns_201_with_indicator_id(self):
        from fastapi.testclient import TestClient

        app = _make_app()

        with patch("src.api.auth.get_settings") as mock_settings:
            mock_settings.return_value.JWT_SECRET_KEY = "test-secret"
            with TestClient(app) as client:
                token = _make_jwt_token(role="admin")
                response = client.post(
                    "/api/v1/indicators",
                    json={
                        "name": "Test Indicator",
                        "formula_dsl": "revenue * 0.5",
                        "normalization_mode": "percentile",
                        "direction": "higher_better",
                        "geo_weight": 0.0,
                    },
                    headers={"Authorization": f"Bearer {token}"},
                )
        assert response.status_code == 201
        data = response.json()
        assert "indicator_id" in data["data"]

    def test_end_user_cannot_create_returns_403(self):
        from fastapi.testclient import TestClient

        app = _make_app()

        with patch("src.api.auth.get_settings") as mock_settings:
            mock_settings.return_value.JWT_SECRET_KEY = "test-secret"
            with TestClient(app) as client:
                token = _make_jwt_token(role="end_user")
                response = client.post(
                    "/api/v1/indicators",
                    json={
                        "name": "Test",
                        "formula_dsl": "revenue",
                    },
                    headers={"Authorization": f"Bearer {token}"},
                )
        assert response.status_code == 403


class TestPreviewIndicator:
    def test_preview_returns_5_company_scores(self):
        from fastapi.testclient import TestClient

        app = _make_app()

        with patch("src.api.auth.get_settings") as mock_settings:
            mock_settings.return_value.JWT_SECRET_KEY = "test-secret"
            with TestClient(app) as client:
                token = _make_jwt_token()
                start = time.time()
                response = client.post(
                    "/api/v1/indicators/preview",
                    json={"formula_dsl": "revenue * 0.5"},
                    headers={"Authorization": f"Bearer {token}"},
                )
                elapsed = time.time() - start

        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]["previews"]) == 5
        # Must complete within 2 seconds
        assert elapsed < 2.0


class TestUpdateIndicator:
    def test_update_returns_200_with_version_2(self):
        from fastapi.testclient import TestClient

        app = _make_app()
        indicator_id = uuid4()

        with patch("src.api.auth.get_settings") as mock_settings:
            mock_settings.return_value.JWT_SECRET_KEY = "test-secret"
            with TestClient(app) as client:
                token = _make_jwt_token(role="admin")
                response = client.put(
                    f"/api/v1/indicators/{indicator_id}",
                    json={"formula_dsl": "revenue * 0.7 + net_income"},
                    headers={"Authorization": f"Bearer {token}"},
                )
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["version"] == 2
