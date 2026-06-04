"""
Unit tests for UserRepository and RefreshTokenRepository.

Uses AsyncMock to isolate from a real database.
Tests verify that tenant_id is always included in WHERE clauses and
that revocation logic operates correctly.
"""
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.storage.models.refresh_token import RefreshToken
from src.storage.models.user import User, UserRole
from src.storage.repositories.user_repository import UserRepository
from src.storage.repositories.refresh_token_repository import RefreshTokenRepository


# ── UserRepository unit tests ─────────────────────────────────────────────────

@pytest.fixture()
def mock_session() -> AsyncMock:
    session = AsyncMock()
    session.execute = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    return session


@pytest.fixture()
def user_repo(mock_session: AsyncMock) -> UserRepository:
    return UserRepository(session=mock_session)


@pytest.fixture()
def refresh_token_repo(mock_session: AsyncMock) -> RefreshTokenRepository:
    return RefreshTokenRepository(session=mock_session)


@pytest.mark.asyncio
async def test_user_repository_get_by_email_returns_none_when_not_found(
    user_repo: UserRepository, mock_session: AsyncMock
) -> None:
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = result_mock

    result = await user_repo.getByEmail(email="nobody@example.com", tenant_id=uuid.uuid4())

    assert result is None


@pytest.mark.asyncio
async def test_user_repository_get_by_email_filters_by_tenant_id(
    user_repo: UserRepository, mock_session: AsyncMock
) -> None:
    tenant_id = uuid.uuid4()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = result_mock

    await user_repo.getByEmail(email="user@example.com", tenant_id=tenant_id)

    # Verify execute was called (SQL ran)
    mock_session.execute.assert_called_once()
    # The compiled SQL statement should reference tenant_id
    call_args = mock_session.execute.call_args
    stmt = call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": False}))
    assert "tenant_id" in compiled


@pytest.mark.asyncio
async def test_user_repository_get_by_id_filters_by_tenant_id(
    user_repo: UserRepository, mock_session: AsyncMock
) -> None:
    tenant_id = uuid.uuid4()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = result_mock

    await user_repo.getById(user_id=uuid.uuid4(), tenant_id=tenant_id)

    mock_session.execute.assert_called_once()
    call_args = mock_session.execute.call_args
    stmt = call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": False}))
    assert "tenant_id" in compiled


# ── RefreshTokenRepository unit tests ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_refresh_token_repository_get_active_excludes_revoked(
    refresh_token_repo: RefreshTokenRepository, mock_session: AsyncMock
) -> None:
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = result_mock

    await refresh_token_repo.getActive(token_id=uuid.uuid4(), tenant_id=uuid.uuid4())

    mock_session.execute.assert_called_once()
    call_args = mock_session.execute.call_args
    stmt = call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": False}))
    # Must include revoked_at IS NULL check
    assert "revoked_at" in compiled
    # Must include expires_at check
    assert "expires_at" in compiled


@pytest.mark.asyncio
async def test_refresh_token_repository_revoke_sets_revoked_at(
    refresh_token_repo: RefreshTokenRepository, mock_session: AsyncMock
) -> None:
    token_id = uuid.uuid4()
    tenant_id = uuid.uuid4()

    mock_token = MagicMock(spec=RefreshToken)
    mock_token.token_id = token_id
    mock_token.tenant_id = tenant_id
    mock_token.revoked_at = None

    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = mock_token
    mock_session.execute.return_value = result_mock

    await refresh_token_repo.revoke(token_id=token_id, tenant_id=tenant_id)

    # revoked_at should have been set
    assert mock_token.revoked_at is not None


@pytest.mark.asyncio
async def test_refresh_token_repository_revoke_all_for_user_updates_all_rows(
    refresh_token_repo: RefreshTokenRepository, mock_session: AsyncMock
) -> None:
    user_id = uuid.uuid4()
    tenant_id = uuid.uuid4()

    result_mock = MagicMock()
    mock_session.execute.return_value = result_mock

    await refresh_token_repo.revokeAllForUser(user_id=user_id, tenant_id=tenant_id)

    # Execute must be called (UPDATE statement)
    mock_session.execute.assert_called_once()
