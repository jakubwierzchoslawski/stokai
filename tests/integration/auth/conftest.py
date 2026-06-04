"""
Shared fixtures for auth integration tests.

Uses SQLite in-memory via aiosqlite for fast, isolated test runs.
Each test gets its own transaction that is rolled back after the test.
"""
import uuid
from typing import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.storage.models.user import Base, User, UserRole
from src.storage.models.refresh_token import RefreshToken


TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture(scope="session")
async def engine():
    """Create a test engine and tables once per session."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        # SQLite does not support PostgreSQL-specific types like UUID natively,
        # but SQLAlchemy will map them to TEXT for SQLite.
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture()
async def db_session(engine) -> AsyncIterator[AsyncSession]:
    """Provide a fresh session with rollback isolation per test."""
    async_session_factory = async_sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
    )
    async with async_session_factory() as session:
        async with session.begin():
            yield session
            await session.rollback()


@pytest.fixture()
def tenant_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture()
def other_tenant_id() -> uuid.UUID:
    return uuid.uuid4()
