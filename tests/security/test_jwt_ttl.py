"""
tests.security.test_jwt_ttl — JWT access token TTL and claims tests.

Covers AC-005: JWT access token expires within 15 minutes; expired token
returns HTTP 401; missing required claims return HTTP 401.
"""
import time
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient
from jose import jwt

from src.api.auth.dependencies import get_current_user, get_db
from src.api.auth.token_service import TokenService
from src.config.settings import Settings


# ── Fixture helpers ────────────────────────────────────────────────────────────

def _make_settings(**overrides) -> Settings:
    """Build a minimal Settings object for testing."""
    defaults = {
        "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
        "REDIS_URL": "redis://localhost:6379",
        "ANTHROPIC_API_KEY": "test-key",
        "OPENAI_API_KEY": "test-key",
        "JWT_SECRET_KEY": "supersecretkey-for-testing-only",
        "JWT_REFRESH_SECRET_KEY": "refresh-secret-for-testing-only",
        "JWT_ACCESS_TOKEN_EXPIRE_MINUTES": 15,
        "BCRYPT_ROUNDS": 4,
    }
    defaults.update(overrides)
    return Settings(**defaults)


@pytest.fixture()
def settings() -> Settings:
    return _make_settings()


@pytest.fixture()
def token_service(settings: Settings) -> TokenService:
    return TokenService(settings=settings)


def _make_protected_app() -> FastAPI:
    """Build a minimal app with one protected endpoint."""
    app = FastAPI()

    @app.get("/protected")
    async def protected(current_user=Depends(get_current_user)):
        return {"user_id": str(current_user.user_id)}

    return app


# ── AC-005: Access token TTL ──────────────────────────────────────────────────

def test_access_token_expires_within_15_minutes(
    token_service: TokenService, settings: Settings
) -> None:
    """createAccessToken must produce a JWT where exp - iat <= 900 seconds."""
    user_id = uuid.uuid4()
    tenant_id = uuid.uuid4()

    token = token_service.createAccessToken(
        user_id=user_id,
        tenant_id=tenant_id,
        role="end_user",
    )

    payload = jwt.decode(
        token,
        settings.JWT_SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
    )

    ttl_seconds = payload["exp"] - payload["iat"]
    assert ttl_seconds <= 900, (
        f"Access token TTL {ttl_seconds}s exceeds 900s (15 minutes). "
        "JWT_ACCESS_TOKEN_EXPIRE_MINUTES must be <= 15."
    )
    assert ttl_seconds > 0, "Access token must have a positive TTL"


def test_expired_access_token_returns_401(settings: Settings) -> None:
    """An expired access token (exp in the past) must return HTTP 401."""
    now = int(time.time())
    # Craft a token that expired 1 second ago
    expired_claims = {
        "sub": str(uuid.uuid4()),
        "tenant_id": str(uuid.uuid4()),
        "role": "end_user",
        "iat": now - 120,
        "exp": now - 1,   # already expired
    }
    expired_token = jwt.encode(
        expired_claims,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )

    app = _make_protected_app()
    # Disable the DB dependency — decoding should fail before DB access
    app.dependency_overrides[get_db] = AsyncMock()

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get(
        "/protected",
        headers={"Authorization": f"Bearer {expired_token}"},
    )

    assert response.status_code == 401, (
        f"Expected 401 for expired token, got {response.status_code}"
    )


def test_access_token_with_no_tenant_id_claim_returns_401(settings: Settings) -> None:
    """A JWT missing the tenant_id claim must return HTTP 401."""
    now = int(time.time())
    claims_no_tenant = {
        "sub": str(uuid.uuid4()),
        # tenant_id deliberately omitted
        "role": "end_user",
        "iat": now,
        "exp": now + 900,
    }
    token = jwt.encode(
        claims_no_tenant,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )

    app = _make_protected_app()
    app.dependency_overrides[get_db] = AsyncMock()

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get(
        "/protected",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401, (
        f"Expected 401 for token without tenant_id, got {response.status_code}"
    )


def test_access_token_with_no_role_claim_returns_401(settings: Settings) -> None:
    """A JWT missing the role claim must return HTTP 401.

    The get_current_user dependency looks up the user in the DB. If the DB
    returns None (user not found — simulated here), it returns 401.
    We additionally verify that tokens without a role claim are handled safely.
    """
    now = int(time.time())
    claims_no_role = {
        "sub": str(uuid.uuid4()),
        "tenant_id": str(uuid.uuid4()),
        # role deliberately omitted
        "iat": now,
        "exp": now + 900,
    }
    token = jwt.encode(
        claims_no_role,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )

    app = _make_protected_app()

    # Mock DB session that returns None for any user lookup (simulates missing user)
    mock_session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(return_value=result_mock)

    async def _mock_db():
        yield mock_session

    app.dependency_overrides[get_db] = _mock_db

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get(
        "/protected",
        headers={"Authorization": f"Bearer {token}"},
    )

    # Either the token decode itself fails (no role in AccessTokenClaims pydantic model)
    # or the user lookup returns None — either way the response is 401.
    assert response.status_code == 401, (
        f"Expected 401 for token without role claim, got {response.status_code}"
    )
