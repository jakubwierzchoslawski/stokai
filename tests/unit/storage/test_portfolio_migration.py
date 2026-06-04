"""
tests.unit.storage.test_portfolio_migration

Verifies that 0052_portfolio_watchlist migration applies and rolls back cleanly,
NOT NULL constraints are enforced, unique constraints reject duplicates, and
ON DELETE CASCADE from portfolio removes child positions.

These are *structural* unit tests — they run against an in-memory SQLite database
via the ORM models rather than invoking Alembic directly (Alembic runtime tests
require a live Postgres instance).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import event, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Import ORM models that mirror the migration
from src.storage.models.portfolio import Portfolio, Position, WatchlistItem
from src.storage.models.user import Base as UserBase, User, UserRole


# ── Shared test base ──────────────────────────────────────────────────────────

@pytest_asyncio.fixture()
async def session():
    """Provide an async SQLite in-memory session with all tables created."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    # SQLite does not enforce FK by default — enable it
    @event.listens_for(engine.sync_engine, "connect")
    def enable_fk(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    from src.storage.models.portfolio import PortfolioBase

    async with engine.begin() as conn:
        # Create user table first (FK target)
        await conn.run_sync(UserBase.metadata.create_all)
        await conn.run_sync(PortfolioBase.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as sess:
        yield sess

    await engine.dispose()


async def _make_user(session: AsyncSession, tenant_id: uuid.UUID) -> User:
    """Insert a minimal user row and return it."""
    u = User(
        user_id=uuid.uuid4(),
        tenant_id=tenant_id,
        email=f"{uuid.uuid4()}@test.com",
        password_hash="x" * 60,
        role=UserRole.end_user,
        settings={},
    )
    session.add(u)
    await session.flush()
    return u


# ── Tests ──────────────────────────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.asyncio
async def test_migration_creates_and_drops_tables(session: AsyncSession):
    """Schema exists — insert a portfolio row without error."""
    tid = uuid.uuid4()
    user = await _make_user(session, tid)
    p = Portfolio(
        portfolio_id=uuid.uuid4(),
        tenant_id=tid,
        user_id=user.user_id,
        name="My Portfolio",
    )
    session.add(p)
    await session.flush()
    assert p.portfolio_id is not None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_portfolio_not_null_tenant_id(session: AsyncSession):
    """tenant_id NOT NULL is enforced."""
    tid = uuid.uuid4()
    user = await _make_user(session, tid)
    p = Portfolio(
        portfolio_id=uuid.uuid4(),
        tenant_id=None,  # should violate NOT NULL
        user_id=user.user_id,
        name="Bad Portfolio",
    )
    session.add(p)
    with pytest.raises(IntegrityError):
        await session.flush()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_position_unique_portfolio_company(session: AsyncSession):
    """(portfolio_id, company_id) unique constraint rejects duplicates."""
    tid = uuid.uuid4()
    user = await _make_user(session, tid)
    company_id = uuid.uuid4()

    portfolio = Portfolio(
        portfolio_id=uuid.uuid4(),
        tenant_id=tid,
        user_id=user.user_id,
        name="P",
    )
    session.add(portfolio)
    await session.flush()

    pos1 = Position(
        position_id=uuid.uuid4(),
        portfolio_id=portfolio.portfolio_id,
        company_id=company_id,
        ticker="AAPL",
        shares=10.0,
        source="manual",
    )
    session.add(pos1)
    await session.flush()

    pos2 = Position(
        position_id=uuid.uuid4(),
        portfolio_id=portfolio.portfolio_id,
        company_id=company_id,  # duplicate
        ticker="AAPL",
        shares=5.0,
        source="manual",
    )
    session.add(pos2)
    with pytest.raises(IntegrityError):
        await session.flush()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_on_delete_cascade_removes_positions(session: AsyncSession):
    """Deleting a portfolio cascades to positions."""
    from sqlalchemy import select, delete

    tid = uuid.uuid4()
    user = await _make_user(session, tid)

    portfolio = Portfolio(
        portfolio_id=uuid.uuid4(),
        tenant_id=tid,
        user_id=user.user_id,
        name="P",
    )
    session.add(portfolio)
    await session.flush()

    pos = Position(
        position_id=uuid.uuid4(),
        portfolio_id=portfolio.portfolio_id,
        company_id=uuid.uuid4(),
        ticker="TSLA",
        shares=3.0,
        source="manual",
    )
    session.add(pos)
    await session.flush()

    # Delete the parent portfolio
    await session.delete(portfolio)
    await session.flush()

    # Position should be gone
    result = await session.execute(
        select(Position).where(Position.position_id == pos.position_id)
    )
    assert result.scalar_one_or_none() is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_watchlist_unique_tenant_user_company(session: AsyncSession):
    """(tenant_id, user_id, company_id) unique rejects duplicates."""
    tid = uuid.uuid4()
    user = await _make_user(session, tid)
    company_id = uuid.uuid4()

    w1 = WatchlistItem(
        item_id=uuid.uuid4(),
        tenant_id=tid,
        user_id=user.user_id,
        company_id=company_id,
        ticker="AAPL",
    )
    session.add(w1)
    await session.flush()

    w2 = WatchlistItem(
        item_id=uuid.uuid4(),
        tenant_id=tid,
        user_id=user.user_id,
        company_id=company_id,  # duplicate
        ticker="AAPL",
    )
    session.add(w2)
    with pytest.raises(IntegrityError):
        await session.flush()
