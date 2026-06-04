"""
api.auth.token_service — JWT issuance/validation and refresh-token hashing.

Pure-Python class with no DB dependency. All operations are synchronous
(bcrypt is CPU-bound; callers in the service layer should run these via
asyncio.get_event_loop().run_in_executor to avoid blocking the event loop).

Never logs raw tokens, JWTs, or password hashes.
"""
import secrets
import time
import uuid
from typing import NamedTuple

from jose import ExpiredSignatureError, JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

from src.config.settings import Settings


class AccessTokenClaims(BaseModel):
    """Validated claims from a decoded access token."""

    sub: str          # user_id as string
    tenant_id: str
    role: str
    iat: int
    exp: int


class TokenExpiredError(Exception):
    """Raised when a JWT access token has expired."""


class InvalidTokenError(Exception):
    """Raised when a JWT token has an invalid signature or is malformed."""


class TokenService:
    """Handles JWT access token issuance/decoding and refresh token lifecycle.

    Dependencies injected at construction (DIP):
      - settings: application configuration (JWT secret, TTLs, bcrypt rounds)
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._crypt_context = CryptContext(
            schemes=["bcrypt"],
            deprecated="auto",
            bcrypt__rounds=settings.BCRYPT_ROUNDS,
        )

    # ── Access tokens ─────────────────────────────────────────────────────────

    def createAccessToken(self, user_id: uuid.UUID, tenant_id: uuid.UUID, role: str) -> str:
        """Issue a signed HS256 JWT access token with a short TTL.

        Returns the encoded JWT string. Never logged.
        """
        now = int(time.time())
        expire = now + self._settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60
        claims = {
            "sub": str(user_id),
            "tenant_id": str(tenant_id),
            "role": role,
            "iat": now,
            "exp": expire,
        }
        return jwt.encode(
            claims,
            self._settings.JWT_SECRET_KEY,
            algorithm=self._settings.JWT_ALGORITHM,
        )

    def decodeAccessToken(self, token: str) -> AccessTokenClaims:
        """Decode and validate an access token.

        Raises:
            TokenExpiredError: if the token's exp claim is in the past.
            InvalidTokenError: if signature is bad, token is malformed,
                               or required claims (sub, tenant_id, role) are absent.
        """
        try:
            payload = jwt.decode(
                token,
                self._settings.JWT_SECRET_KEY,
                algorithms=[self._settings.JWT_ALGORITHM],
            )
        except ExpiredSignatureError as exc:
            raise TokenExpiredError("Access token has expired") from exc
        except JWTError as exc:
            raise InvalidTokenError("Access token is invalid") from exc

        try:
            return AccessTokenClaims(**payload)
        except Exception as exc:
            # Pydantic ValidationError — required claims missing or of wrong type.
            raise InvalidTokenError(
                "Access token is missing required claims (sub, tenant_id, role)"
            ) from exc

    # ── Refresh tokens ────────────────────────────────────────────────────────

    def createRefreshToken(self) -> tuple[uuid.UUID, str]:
        """Generate a new refresh token.

        Returns:
            (token_id, raw_token) — token_id is a UUID stored in the DB;
            raw_token is a URL-safe random string delivered to the client.
            The raw_token must be hashed before persistence.
        """
        token_id = uuid.uuid4()
        raw_token = secrets.token_urlsafe(32)
        return token_id, raw_token

    def hashRefreshToken(self, raw_token: str) -> str:
        """Hash a raw refresh token with bcrypt.

        The hash is safe to store in the database.
        Never log the raw_token argument.
        """
        return self._crypt_context.hash(raw_token)

    def verifyRefreshToken(self, raw_token: str, stored_hash: str) -> bool:
        """Verify a raw refresh token against its stored bcrypt hash.

        Returns True if the token matches, False otherwise.
        Never raises on mismatch — timing-safe comparison via passlib.
        """
        return self._crypt_context.verify(raw_token, stored_hash)
