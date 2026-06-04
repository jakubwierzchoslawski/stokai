"""
api.auth.auth_service — Business logic for authentication flows.

Handles login (credential validation + token issuance), token refresh,
logout (token revocation), and password hashing.

All dependencies are injected via constructor (DIP).
Never logs email, password, tokens, or hashes.
"""
import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from functools import partial

from passlib.context import CryptContext

from src.api.auth.exceptions import AuthenticationError
from src.api.auth.token_service import TokenService
from src.config.settings import get_settings
from src.storage.models.user import User, UserRole
from src.storage.repositories.refresh_token_repository import RefreshTokenRepository
from src.storage.repositories.user_repository import UserRepository

# Module-level CryptContext shared between password hashing and dummy verify.
# Rounds are read at import time from settings — ensure get_settings() is
# available in the environment (required fields must be set).
_settings = get_settings()
_crypt_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=_settings.BCRYPT_ROUNDS,
)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Timing-safe bcrypt verify. Synchronous — use run_in_executor in async contexts."""
    return _crypt_context.verify(plain_password, hashed_password)


def dummy_verify() -> None:
    """Perform a throwaway bcrypt operation to prevent timing-based user enumeration.

    Called when a user lookup returns None so that the response time matches
    a failed-password path (both paths do bcrypt work).
    """
    _crypt_context.dummy_verify()


class AuthService:
    """Business logic for all authentication operations.

    Depends on (all injected):
      - user_repo: UserRepository
      - refresh_token_repo: RefreshTokenRepository
      - token_service: TokenService
    """

    def __init__(
        self,
        user_repo: UserRepository,
        refresh_token_repo: RefreshTokenRepository,
        token_service: TokenService,
    ) -> None:
        self._user_repo = user_repo
        self._refresh_token_repo = refresh_token_repo
        self._token_service = token_service

    # ── Public API ────────────────────────────────────────────────────────────

    async def login(
        self,
        email: str,
        password: str,
        tenant_id: uuid.UUID,
    ) -> tuple[str, uuid.UUID, str]:
        """Validate credentials and issue a new access + refresh token pair.

        Returns:
            (access_token, refresh_token_id, raw_refresh_token)

        Raises:
            AuthenticationError: on invalid email or password (same message both cases).

        Security notes:
          - On unknown email, dummy_verify() is called to prevent timing oracle.
          - Never logs the password, email, or any token value.
        """
        loop = asyncio.get_event_loop()

        user = await self._user_repo.getByEmail(email=email, tenant_id=tenant_id)

        if user is None:
            # Run dummy bcrypt work off the event loop to equalise timing
            await loop.run_in_executor(None, dummy_verify)
            raise AuthenticationError("Invalid credentials")

        # Run bcrypt verify off the event loop (CPU-bound)
        is_valid = await loop.run_in_executor(
            None,
            partial(verify_password, password, user.password_hash),
        )
        if not is_valid:
            raise AuthenticationError("Invalid credentials")

        # Issue tokens
        access_token = self._token_service.createAccessToken(
            user_id=user.user_id,
            tenant_id=user.tenant_id,
            role=user.role.value,
        )
        token_id, raw_refresh_token = self._token_service.createRefreshToken()
        token_hash = await loop.run_in_executor(
            None,
            partial(self._token_service.hashRefreshToken, raw_refresh_token),
        )

        expires_at = datetime.now(tz=timezone.utc) + timedelta(
            days=_settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS
        )
        await self._refresh_token_repo.create(
            user_id=user.user_id,
            tenant_id=tenant_id,
            token_hash=token_hash,
            expires_at=expires_at,
        )

        return access_token, token_id, raw_refresh_token

    async def refresh(
        self,
        token_id: uuid.UUID,
        raw_token: str,
        tenant_id: uuid.UUID,
        user: User,
    ) -> str:
        """Validate a refresh token and issue a new access token.

        Args:
            token_id: UUID of the refresh token row to look up.
            raw_token: the raw token value from the HttpOnly cookie.
            tenant_id: tenant scope for the lookup.
            user: the User object (loaded by the calling layer).

        Returns:
            New access token string.

        Raises:
            AuthenticationError: if the token is not active or hash mismatch.
        """
        active_token = await self._refresh_token_repo.getActive(
            token_id=token_id,
            tenant_id=tenant_id,
        )
        if active_token is None:
            raise AuthenticationError("Invalid or expired refresh token")

        loop = asyncio.get_event_loop()
        is_valid = await loop.run_in_executor(
            None,
            partial(self._token_service.verifyRefreshToken, raw_token, active_token.token_hash),
        )
        if not is_valid:
            raise AuthenticationError("Invalid refresh token")

        return self._token_service.createAccessToken(
            user_id=user.user_id,
            tenant_id=user.tenant_id,
            role=user.role.value,
        )

    async def logout(self, token_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
        """Revoke a single refresh token.

        Raises:
            No exception on unknown token (idempotent).
        """
        await self._refresh_token_repo.revoke(token_id=token_id, tenant_id=tenant_id)

    def hashPassword(self, password: str) -> str:
        """Hash a plaintext password with bcrypt.

        Synchronous — callers in async context should use run_in_executor.
        Never log the input or output of this function.
        """
        return _crypt_context.hash(password)
