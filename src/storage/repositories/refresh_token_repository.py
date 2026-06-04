"""
storage.repositories.refresh_token_repository — RefreshTokenRepository.

All queries include tenant_id in the WHERE clause via TenantScopedRepository
(REQ-N-006 / Principle 3). No business logic lives here — only SQL via
SQLAlchemy 2.0 async ORM.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from src.storage.models.refresh_token import RefreshToken
from src.storage.repositories.base import TenantScopedRepository


class RefreshTokenRepository(TenantScopedRepository):
    """Repository for refresh_token entity persistence.

    Inherits TenantScopedRepository to structurally enforce tenant_id on every
    query. Manages the lifecycle of server-side refresh tokens:
    create → (active) → revoke.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        user_id: uuid.UUID,
        tenant_id: uuid.UUID,
        token_hash: str,
        expires_at: datetime,
    ) -> RefreshToken:
        """Persist a new refresh token row.

        token_hash must be a bcrypt hash of the raw token — never the raw value.
        expires_at should be a timezone-aware datetime.
        """
        token = RefreshToken(
            user_id=user_id,
            tenant_id=tenant_id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        self._session.add(token)
        await self._session.flush()
        await self._session.refresh(token)
        return token

    async def getActive(self, token_id: uuid.UUID, tenant_id: uuid.UUID) -> RefreshToken | None:
        """Retrieve an active (non-revoked, non-expired) refresh token.

        Returns None if the token does not exist, has been revoked,
        has expired, or belongs to a different tenant.
        """
        now = datetime.now(tz=timezone.utc)
        stmt = (
            self._scoped_select(RefreshToken, tenant_id)
            .where(
                RefreshToken.token_id == token_id,
                RefreshToken.revoked_at.is_(None),
                RefreshToken.expires_at > now,
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def revoke(self, token_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
        """Mark a single refresh token as revoked.

        Fetches the token and sets revoked_at; no-op if token not found.
        tenant_id is enforced via _scoped_select to prevent cross-tenant revocation.
        """
        stmt = self._scoped_select(RefreshToken, tenant_id).where(
            RefreshToken.token_id == token_id,
        )
        result = await self._session.execute(stmt)
        token = result.scalar_one_or_none()
        if token is not None:
            token.revoked_at = datetime.now(tz=timezone.utc)

    async def revokeAllForUser(self, user_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
        """Revoke all non-revoked tokens for the specified user.

        Used during logout-all or security reset flows.
        tenant_id is enforced via _scoped_update in the WHERE clause.
        """
        now = datetime.now(tz=timezone.utc)
        stmt = (
            self._scoped_update(RefreshToken, tenant_id)
            .where(
                RefreshToken.user_id == user_id,
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )
        await self._session.execute(stmt)
