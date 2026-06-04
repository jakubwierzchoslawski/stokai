"""
Unit tests for TokenService.

TDD — written before implementation (red phase).
Tests cover: access token creation/decoding, refresh token generation,
bcrypt hash/verify, and error handling on expired/tampered tokens.
"""
import time
import uuid
from unittest.mock import MagicMock

import pytest
from jose import jwt

from src.api.auth.token_service import (
    AccessTokenClaims,
    InvalidTokenError,
    TokenExpiredError,
    TokenService,
)
from src.config.settings import Settings


@pytest.fixture()
def settings() -> Settings:
    """Minimal settings for token tests — no real env needed."""
    mock = MagicMock(spec=Settings)
    mock.JWT_SECRET_KEY = "test-secret-key-at-least-32-chars-long!!"
    mock.JWT_REFRESH_SECRET_KEY = "test-refresh-secret-key-32-chars!!"
    mock.JWT_ALGORITHM = "HS256"
    mock.JWT_ACCESS_TOKEN_EXPIRE_MINUTES = 15
    mock.JWT_REFRESH_TOKEN_EXPIRE_DAYS = 7
    mock.BCRYPT_ROUNDS = 4  # low rounds for test speed
    return mock


@pytest.fixture()
def service(settings: Settings) -> TokenService:
    return TokenService(settings=settings)


def test_create_access_token_returns_decodable_jwt(service: TokenService, settings: Settings) -> None:
    user_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    role = "admin"

    token = service.createAccessToken(user_id=user_id, tenant_id=tenant_id, role=role)

    payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    assert payload["sub"] == str(user_id)
    assert payload["tenant_id"] == str(tenant_id)
    assert payload["role"] == role
    assert "iat" in payload
    assert "exp" in payload


def test_access_token_expires_at_configured_ttl(service: TokenService, settings: Settings) -> None:
    user_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    now = int(time.time())

    token = service.createAccessToken(user_id=user_id, tenant_id=tenant_id, role="operator")

    payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    expected_exp = now + settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60
    assert abs(payload["exp"] - expected_exp) <= 2  # within 2 seconds


def test_decode_access_token_raises_on_expired(service: TokenService, settings: Settings) -> None:
    user_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    # Create token with exp in the past
    claims = {
        "sub": str(user_id),
        "tenant_id": str(tenant_id),
        "role": "end_user",
        "iat": int(time.time()) - 3600,
        "exp": int(time.time()) - 1800,
    }
    expired_token = jwt.encode(claims, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

    with pytest.raises(TokenExpiredError):
        service.decodeAccessToken(expired_token)


def test_decode_access_token_raises_on_tampered_signature(service: TokenService) -> None:
    user_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    token = service.createAccessToken(user_id=user_id, tenant_id=tenant_id, role="admin")

    # Tamper: flip last character
    tampered = token[:-1] + ("X" if token[-1] != "X" else "Y")

    with pytest.raises(InvalidTokenError):
        service.decodeAccessToken(tampered)


def test_create_refresh_token_returns_uuid_and_raw_string(service: TokenService) -> None:
    token_id, raw_token = service.createRefreshToken()

    assert isinstance(token_id, uuid.UUID)
    assert isinstance(raw_token, str)
    assert len(raw_token) > 0


def test_hash_and_verify_refresh_token_round_trip(service: TokenService) -> None:
    _, raw_token = service.createRefreshToken()
    token_hash = service.hashRefreshToken(raw_token)

    assert service.verifyRefreshToken(raw_token, token_hash) is True


def test_verify_refresh_token_fails_for_wrong_token(service: TokenService) -> None:
    _, raw_token = service.createRefreshToken()
    _, other_raw = service.createRefreshToken()
    token_hash = service.hashRefreshToken(raw_token)

    assert service.verifyRefreshToken(other_raw, token_hash) is False


def test_hash_refresh_token_uses_bcrypt_rounds(service: TokenService, settings: Settings) -> None:
    _, raw_token = service.createRefreshToken()
    token_hash = service.hashRefreshToken(raw_token)

    # bcrypt hash format: $2b$<rounds>$...
    assert token_hash.startswith("$2")
    parts = token_hash.split("$")
    # parts[0]='', parts[1]='2b', parts[2]=rounds, parts[3]=rest
    rounds_in_hash = int(parts[2])
    assert rounds_in_hash == settings.BCRYPT_ROUNDS
