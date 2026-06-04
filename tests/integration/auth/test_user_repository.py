"""
Integration tests for UserRepository against a real (SQLite) database.
"""
import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from src.storage.models.user import UserRole
from src.storage.repositories.user_repository import UserRepository


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_and_retrieve_user_by_email(
    db_session: AsyncSession, tenant_id: uuid.UUID
) -> None:
    repo = UserRepository(session=db_session)
    user = await repo.create(
        tenant_id=tenant_id,
        email="admin@example.com",
        password_hash="$2b$12$fakehashfortest",
        role=UserRole.admin,
    )
    assert user.user_id is not None

    found = await repo.getByEmail(email="admin@example.com", tenant_id=tenant_id)
    assert found is not None
    assert found.email == "admin@example.com"
    assert found.role == UserRole.admin


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_user_by_email_wrong_tenant_returns_none(
    db_session: AsyncSession, tenant_id: uuid.UUID, other_tenant_id: uuid.UUID
) -> None:
    repo = UserRepository(session=db_session)
    await repo.create(
        tenant_id=tenant_id,
        email="operator@example.com",
        password_hash="$2b$12$fakehashfortest",
        role=UserRole.operator,
    )

    # Query with the wrong tenant — must return None (no cross-tenant data)
    found = await repo.getByEmail(email="operator@example.com", tenant_id=other_tenant_id)
    assert found is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_user_by_id_filters_by_tenant(
    db_session: AsyncSession, tenant_id: uuid.UUID, other_tenant_id: uuid.UUID
) -> None:
    repo = UserRepository(session=db_session)
    user = await repo.create(
        tenant_id=tenant_id,
        email="user@example.com",
        password_hash="$2b$12$fakehashfortest",
        role=UserRole.end_user,
    )

    # Same user_id, wrong tenant -> None
    found = await repo.getById(user_id=user.user_id, tenant_id=other_tenant_id)
    assert found is None

    # Correct tenant -> found
    found_correct = await repo.getById(user_id=user.user_id, tenant_id=tenant_id)
    assert found_correct is not None
    assert found_correct.user_id == user.user_id
