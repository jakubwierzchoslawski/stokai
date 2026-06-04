"""
Unit tests for AuthService.

All external dependencies (UserRepository, RefreshTokenRepository, TokenService)
are mocked — no real DB or JWT operations run.
"""
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.api.auth.auth_service import AuthService
from src.api.auth.exceptions import AuthenticationError
from src.api.auth.token_service import TokenService, AccessTokenClaims
from src.storage.models.user import User, UserRole
from src.storage.models.refresh_token import RefreshToken
from src.storage.repositories.user_repository import UserRepository
from src.storage.repositories.refresh_token_repository import RefreshTokenRepository


@pytest.fixture()
def user_repo() -> AsyncMock:
    repo = AsyncMock(spec=UserRepository)
    return repo


@pytest.fixture()
def refresh_token_repo() -> AsyncMock:
    repo = AsyncMock(spec=RefreshTokenRepository)
    return repo


@pytest.fixture()
def token_service() -> MagicMock:
    svc = MagicMock(spec=TokenService)
    return svc


@pytest.fixture()
def auth_service(
    user_repo: AsyncMock,
    refresh_token_repo: AsyncMock,
    token_service: MagicMock,
) -> AuthService:
    return AuthService(
        user_repo=user_repo,
        refresh_token_repo=refresh_token_repo,
        token_service=token_service,
    )


def _make_user(role: UserRole = UserRole.end_user) -> MagicMock:
    user = MagicMock(spec=User)
    user.user_id = uuid.uuid4()
    user.tenant_id = uuid.uuid4()
    user.email = "user@example.com"
    user.password_hash = "$2b$12$testhashedpassword"
    user.role = role
    return user


# ── login tests ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_login_valid_credentials_returns_access_and_refresh_tokens(
    auth_service: AuthService,
    user_repo: AsyncMock,
    refresh_token_repo: AsyncMock,
    token_service: MagicMock,
) -> None:
    user = _make_user()
    user_repo.getByEmail.return_value = user
    tenant_id = user.tenant_id

    token_service.verifyRefreshToken.return_value = True
    token_service.createAccessToken.return_value = "access.token.here"
    token_service.createRefreshToken.return_value = (uuid.uuid4(), "raw-refresh-token")
    token_service.hashRefreshToken.return_value = "$2b$12$refreshhash"

    refresh_token_row = MagicMock(spec=RefreshToken)
    refresh_token_repo.create.return_value = refresh_token_row

    with patch("src.api.auth.auth_service.verify_password", return_value=True):
        access_token, refresh_token_id, raw_refresh = await auth_service.login(
            email="user@example.com",
            password="correctpassword",
            tenant_id=tenant_id,
        )

    assert access_token == "access.token.here"
    assert isinstance(refresh_token_id, uuid.UUID)
    assert raw_refresh == "raw-refresh-token"
    refresh_token_repo.create.assert_called_once()


@pytest.mark.asyncio
async def test_login_wrong_password_raises_unauthorized(
    auth_service: AuthService,
    user_repo: AsyncMock,
) -> None:
    user = _make_user()
    user_repo.getByEmail.return_value = user

    with patch("src.api.auth.auth_service.verify_password", return_value=False):
        with pytest.raises(AuthenticationError):
            await auth_service.login(
                email="user@example.com",
                password="wrongpassword",
                tenant_id=user.tenant_id,
            )


@pytest.mark.asyncio
async def test_login_unknown_email_raises_unauthorized(
    auth_service: AuthService,
    user_repo: AsyncMock,
) -> None:
    user_repo.getByEmail.return_value = None

    with patch("src.api.auth.auth_service.dummy_verify") as mock_dummy:
        with pytest.raises(AuthenticationError):
            await auth_service.login(
                email="nobody@example.com",
                password="anypassword",
                tenant_id=uuid.uuid4(),
            )
        # dummy_verify must be called to prevent timing oracle
        mock_dummy.assert_called_once()


@pytest.mark.asyncio
async def test_login_uses_constant_time_comparison_for_unknown_email(
    auth_service: AuthService,
    user_repo: AsyncMock,
) -> None:
    """Even on unknown email, dummy_verify is called to prevent timing attack."""
    user_repo.getByEmail.return_value = None

    with patch("src.api.auth.auth_service.dummy_verify") as mock_dummy:
        with pytest.raises(AuthenticationError):
            await auth_service.login(
                email="ghost@example.com",
                password="anypassword",
                tenant_id=uuid.uuid4(),
            )
        mock_dummy.assert_called_once()


# ── refresh tests ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_refresh_valid_token_returns_new_access_token(
    auth_service: AuthService,
    refresh_token_repo: AsyncMock,
    token_service: MagicMock,
) -> None:
    token_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()

    active_token = MagicMock(spec=RefreshToken)
    active_token.token_hash = "$2b$12$storedrefreshhash"
    active_token.user_id = user_id

    refresh_token_repo.getActive.return_value = active_token
    token_service.verifyRefreshToken.return_value = True
    token_service.createAccessToken.return_value = "new.access.token"

    # Need a user for the new access token
    user = _make_user()
    user.user_id = user_id
    user.tenant_id = tenant_id

    with patch("src.api.auth.auth_service.UserRepository") as _:
        # The service gets user from the active token's user reference
        active_token.user_id = user_id

        result = await auth_service.refresh(
            token_id=token_id,
            raw_token="raw-token-value",
            tenant_id=tenant_id,
            user=user,
        )

    assert result == "new.access.token"


@pytest.mark.asyncio
async def test_refresh_revoked_token_raises_unauthorized(
    auth_service: AuthService,
    refresh_token_repo: AsyncMock,
) -> None:
    refresh_token_repo.getActive.return_value = None  # revoked or expired

    with pytest.raises(AuthenticationError):
        await auth_service.refresh(
            token_id=uuid.uuid4(),
            raw_token="any-raw",
            tenant_id=uuid.uuid4(),
            user=_make_user(),
        )


@pytest.mark.asyncio
async def test_refresh_expired_token_raises_unauthorized(
    auth_service: AuthService,
    refresh_token_repo: AsyncMock,
) -> None:
    # getActive already filters expired tokens — returns None
    refresh_token_repo.getActive.return_value = None

    with pytest.raises(AuthenticationError):
        await auth_service.refresh(
            token_id=uuid.uuid4(),
            raw_token="any-raw",
            tenant_id=uuid.uuid4(),
            user=_make_user(),
        )


# ── logout tests ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_logout_revokes_token(
    auth_service: AuthService,
    refresh_token_repo: AsyncMock,
) -> None:
    token_id = uuid.uuid4()
    tenant_id = uuid.uuid4()

    await auth_service.logout(token_id=token_id, tenant_id=tenant_id)

    refresh_token_repo.revoke.assert_called_once_with(token_id=token_id, tenant_id=tenant_id)


# ── password hashing tests ────────────────────────────────────────────────────

def test_password_hash_uses_bcrypt_rounds_gte_12(auth_service: AuthService) -> None:
    hashed = auth_service.hashPassword("mysecretpassword123")

    # bcrypt hash format: $2b$<rounds>$...
    assert hashed.startswith("$2")
    parts = hashed.split("$")
    rounds = int(parts[2])
    assert rounds >= 12
