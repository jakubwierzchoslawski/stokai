"""
Integration tests for the AuthRouter endpoints.

Uses FastAPI TestClient with mocked AuthService to avoid real DB/JWT ops.
Tests verify HTTP status codes, response bodies, cookie behaviour, and error envelopes.
"""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.auth.exceptions import AuthenticationError
from src.api.auth.router import auth_router
from src.config.settings import Settings


def _build_test_app() -> FastAPI:
    """Build a minimal FastAPI app with just the auth router for testing."""
    app = FastAPI()
    app.include_router(auth_router, prefix="/api/v1")
    return app


@pytest.fixture()
def mock_auth_service() -> AsyncMock:
    svc = AsyncMock()
    svc.login = AsyncMock()
    svc.refresh = AsyncMock()
    svc.logout = AsyncMock()
    return svc


@pytest.fixture()
def client(mock_auth_service: AsyncMock) -> TestClient:
    app = _build_test_app()

    # Override the AuthService dependency
    from src.api.auth.router import get_auth_service
    app.dependency_overrides[get_auth_service] = lambda: mock_auth_service

    return TestClient(app)


# ── Login tests ───────────────────────────────────────────────────────────────

@pytest.mark.integration
def test_login_valid_credentials_returns_200_with_access_token(
    client: TestClient, mock_auth_service: AsyncMock
) -> None:
    token_id = uuid.uuid4()
    mock_auth_service.login.return_value = ("access.token.here", token_id, "raw-refresh-token")

    response = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "correctpassword"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["access_token"] == "access.token.here"
    assert body["data"]["token_type"] == "bearer"
    assert body["data"]["expires_in"] > 0
    assert body["error"] is None

    # HttpOnly cookie must be set
    set_cookie = response.headers.get("set-cookie", "")
    assert "refresh_token" in set_cookie
    assert "HttpOnly" in set_cookie


@pytest.mark.integration
def test_login_invalid_password_returns_401_generic_message(
    client: TestClient, mock_auth_service: AsyncMock
) -> None:
    mock_auth_service.login.side_effect = AuthenticationError("Invalid credentials")

    response = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "wrongpassword"},
    )

    assert response.status_code == 401
    body = response.json()
    assert body["data"] is None
    assert body["error"]["code"] == "UNAUTHORIZED"
    # Must not reveal which field was wrong
    assert "wrong password" not in body["error"]["message"].lower()
    assert "user not found" not in body["error"]["message"].lower()


@pytest.mark.integration
def test_login_unknown_email_returns_401_same_message(
    client: TestClient, mock_auth_service: AsyncMock
) -> None:
    mock_auth_service.login.side_effect = AuthenticationError("Invalid credentials")

    response = client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": "anypassword"},
    )

    assert response.status_code == 401
    body = response.json()
    assert body["error"]["code"] == "UNAUTHORIZED"
    # Same message as wrong-password — no oracle
    assert "user not found" not in body["error"]["message"].lower()


@pytest.mark.integration
def test_login_missing_fields_returns_422(client: TestClient) -> None:
    response = client.post("/api/v1/auth/login", json={"email": "only@example.com"})
    assert response.status_code == 422


# ── Refresh tests ─────────────────────────────────────────────────────────────

@pytest.mark.integration
def test_refresh_valid_cookie_returns_200_new_access_token(
    client: TestClient, mock_auth_service: AsyncMock
) -> None:
    token_id = str(uuid.uuid4())
    mock_auth_service.refresh.return_value = "new.access.token"

    response = client.post(
        "/api/v1/auth/refresh",
        cookies={"refresh_token": f"{token_id}:raw-token-value"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["access_token"] == "new.access.token"


@pytest.mark.integration
def test_refresh_missing_cookie_returns_401(client: TestClient) -> None:
    response = client.post("/api/v1/auth/refresh")
    assert response.status_code == 401


@pytest.mark.integration
def test_refresh_revoked_token_returns_401(
    client: TestClient, mock_auth_service: AsyncMock
) -> None:
    mock_auth_service.refresh.side_effect = AuthenticationError("Invalid refresh token")
    token_id = str(uuid.uuid4())

    response = client.post(
        "/api/v1/auth/refresh",
        cookies={"refresh_token": f"{token_id}:raw-token-value"},
    )

    assert response.status_code == 401


# ── Logout tests ──────────────────────────────────────────────────────────────

@pytest.mark.integration
def test_logout_returns_204_and_clears_cookie(
    client: TestClient, mock_auth_service: AsyncMock
) -> None:
    token_id = str(uuid.uuid4())
    mock_auth_service.logout.return_value = None

    response = client.post(
        "/api/v1/auth/logout",
        cookies={"refresh_token": f"{token_id}:raw-token-value"},
    )

    assert response.status_code == 204
    # Cookie should be cleared
    set_cookie = response.headers.get("set-cookie", "")
    assert "refresh_token" in set_cookie
    assert "Max-Age=0" in set_cookie or "max-age=0" in set_cookie.lower()
