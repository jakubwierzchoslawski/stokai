"""
Integration tests for RefreshTokenRepository against a real (SQLite) database.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.storage.models.user import UserRole
from src.storage.repositories.refresh_token_repository import RefreshTokenRepository
from src.storage.repositories.user_repository import UserRepository


async def _create_test_user(db_session: AsyncSession, tenant_id: uuid.UUID) -> uuid.UUID:
    """Helper: create a user and return its user_id."""
    user_repo = UserRepository(session=db_session)
    user = await user_repo.create(
        tenant_id=tenant_id,
        email=f"user-{uuid.uuid4()}@example.com",
        password_hash="$2b$12$fakehash",
        role=UserRole.end_user,
    )
    return user.user_id


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_refresh_token_and_get_active(
    db_session: AsyncSession, tenant_id: uuid.UUID
) -> None:
    user_id = await _create_test_user(db_session, tenant_id)
    repo = RefreshTokenRepository(session=db_session)
    expires_at = datetime.now(tz=timezone.utc) + timedelta(days=7)

    token = await repo.create(
        user_id=user_id,
        tenant_id=tenant_id,
        token_hash="$2b$12$fakehashvalue",
        expires_at=expires_at,
    )
    assert token.token_id is not None

    found = await repo.getActive(token_id=token.token_id, tenant_id=tenant_id)
    assert found is not None
    assert found.token_id == token.token_id


@pytest.mark.integration
@pytest.mark.asyncio
async def test_revoke_token_makes_get_active_return_none(
    db_session: AsyncSession, tenant_id: uuid.UUID
) -> None:
    user_id = await _create_test_user(db_session, tenant_id)
    repo = RefreshTokenRepository(session=db_session)
    expires_at = datetime.now(tz=timezone.utc) + timedelta(days=7)

    token = await repo.create(
        user_id=user_id,
        tenant_id=tenant_id,
        token_hash="$2b$12$fakehashvalue",
        expires_at=expires_at,
    )

    await repo.revoke(token_id=token.token_id, tenant_id=tenant_id)

    found = await repo.getActive(token_id=token.token_id, tenant_id=tenant_id)
    assert found is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_revoke_all_for_user_revokes_all_tokens(
    db_session: AsyncSession, tenant_id: uuid.UUID
) -> None:
    user_id = await _create_test_user(db_session, tenant_id)
    repo = RefreshTokenRepository(session=db_session)
    expires_at = datetime.now(tz=timezone.utc) + timedelta(days=7)

    token1 = await repo.create(
        user_id=user_id,
        tenant_id=tenant_id,
        token_hash="$2b$12$fakehash1",
        expires_at=expires_at,
    )
    token2 = await repo.create(
        user_id=user_id,
        tenant_id=tenant_id,
        token_hash="$2b$12$fakehash2",
        expires_at=expires_at,
    )

    await repo.revokeAllForUser(user_id=user_id, tenant_id=tenant_id)

    assert await repo.getActive(token_id=token1.token_id, tenant_id=tenant_id) is None
    assert await repo.getActive(token_id=token2.token_id, tenant_id=tenant_id) is None
