"""
tests.unit.storage.test_portfolio_repositories

Unit tests for PortfolioRepository, PositionRepository, and WatchlistItemRepository
using an in-memory SQLite database.
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.storage.models.portfolio import Portfolio, Position, PortfolioBase, WatchlistItem
from src.storage.models.user import Base as UserBase, User, UserRole
from src.storage.portfolio_repository import PortfolioRepository
from src.storage.position_repository import PositionRepository
from src.storage.watchlist_item_repository import WatchlistItemRepository


# ── Shared fixture ─────────────────────────────────────────────────────────────


@pytest_asyncio.fixture()
async def session():
    """In-memory SQLite session with FK support enabled."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    @event.listens_for(engine.sync_engine, "connect")
    def enable_fk(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    async with engine.begin() as conn:
        await conn.run_sync(UserBase.metadata.create_all)
        await conn.run_sync(PortfolioBase.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as sess:
        yield sess

    await engine.dispose()


async def _insert_user(session: AsyncSession, tenant_id: uuid.UUID) -> User:
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


async def _insert_portfolio(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    name: str = "Test",
) -> Portfolio:
    repo = PortfolioRepository(session)
    return await repo.create(tenant_id, user_id, name)


# ── PortfolioRepository tests ──────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.asyncio
async def test_portfolio_repo_create(session: AsyncSession):
    """create() returns a Portfolio with correct tenant_id and user_id."""
    tid = uuid.uuid4()
    user = await _insert_user(session, tid)
    repo = PortfolioRepository(session)
    p = await repo.create(tenant_id=tid, user_id=user.user_id, name="My Portfolio")
    assert p.tenant_id == tid
    assert p.user_id == user.user_id
    assert p.name == "My Portfolio"
    assert p.portfolio_id is not None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_portfolio_repo_list_isolation(session: AsyncSession):
    """list_by_user: two tenants see only their own portfolios."""
    tid_a = uuid.uuid4()
    tid_b = uuid.uuid4()
    user_a = await _insert_user(session, tid_a)
    user_b = await _insert_user(session, tid_b)

    repo = PortfolioRepository(session)
    await repo.create(tid_a, user_a.user_id, "A portfolio")
    await repo.create(tid_b, user_b.user_id, "B portfolio")

    list_a = await repo.list_by_user(tid_a, user_a.user_id)
    list_b = await repo.list_by_user(tid_b, user_b.user_id)

    assert len(list_a) == 1
    assert list_a[0].tenant_id == tid_a

    assert len(list_b) == 1
    assert list_b[0].tenant_id == tid_b


@pytest.mark.unit
@pytest.mark.asyncio
async def test_portfolio_repo_get_returns_none_for_wrong_tenant(session: AsyncSession):
    """get() returns None when portfolio belongs to a different tenant."""
    tid_a = uuid.uuid4()
    tid_b = uuid.uuid4()
    user_a = await _insert_user(session, tid_a)

    repo = PortfolioRepository(session)
    p = await repo.create(tid_a, user_a.user_id, "P")

    result = await repo.get(tid_b, p.portfolio_id)
    assert result is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_portfolio_repo_delete(session: AsyncSession):
    """delete() removes the portfolio row."""
    tid = uuid.uuid4()
    user = await _insert_user(session, tid)
    repo = PortfolioRepository(session)
    p = await repo.create(tid, user.user_id, "Del")
    await repo.delete(tid, p.portfolio_id)
    assert await repo.get(tid, p.portfolio_id) is None


# ── PositionRepository tests ───────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.asyncio
async def test_position_repo_tenant_isolation(session: AsyncSession):
    """Tenant B cannot get Tenant A's positions via get()."""
    tid_a = uuid.uuid4()
    tid_b = uuid.uuid4()
    user_a = await _insert_user(session, tid_a)

    p = await _insert_portfolio(session, tid_a, user_a.user_id)

    pos_repo = PositionRepository(session)
    pos = await pos_repo.create(
        tenant_id=tid_a,
        portfolio_id=p.portfolio_id,
        company_id=uuid.uuid4(),
        ticker="AAPL",
        shares=10.0,
        source="manual",
    )

    # Tenant B should get None
    result = await pos_repo.get(tid_b, pos.position_id)
    assert result is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_position_repo_bulk_create(session: AsyncSession):
    """bulk_create: 3 rows → 3 Position objects returned."""
    tid = uuid.uuid4()
    user = await _insert_user(session, tid)
    p = await _insert_portfolio(session, tid, user.user_id)

    pos_repo = PositionRepository(session)
    rows = [
        {"company_id": uuid.uuid4(), "ticker": "AAPL", "shares": 10.0, "source": "csv"},
        {"company_id": uuid.uuid4(), "ticker": "MSFT", "shares": 5.0, "source": "csv"},
        {"company_id": uuid.uuid4(), "ticker": "TSLA", "shares": 3.0, "source": "csv"},
    ]
    positions = await pos_repo.bulk_create(tid, p.portfolio_id, rows)
    assert len(positions) == 3
    assert all(isinstance(pos, Position) for pos in positions)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_position_repo_list_by_portfolio(session: AsyncSession):
    """list_by_portfolio returns only positions for the given portfolio."""
    tid = uuid.uuid4()
    user = await _insert_user(session, tid)
    p1 = await _insert_portfolio(session, tid, user.user_id, "P1")
    p2 = await _insert_portfolio(session, tid, user.user_id, "P2")

    pos_repo = PositionRepository(session)
    await pos_repo.create(tid, p1.portfolio_id, uuid.uuid4(), "AAPL", 10.0, "manual")
    await pos_repo.create(tid, p2.portfolio_id, uuid.uuid4(), "MSFT", 5.0, "manual")

    positions_p1 = await pos_repo.list_by_portfolio(tid, p1.portfolio_id)
    assert len(positions_p1) == 1
    assert positions_p1[0].ticker == "AAPL"


# ── WatchlistItemRepository tests ─────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.asyncio
async def test_watchlist_repo_remove(session: AsyncSession):
    """add then remove → list_by_user returns empty list."""
    tid = uuid.uuid4()
    user = await _insert_user(session, tid)
    company_id = uuid.uuid4()

    repo = WatchlistItemRepository(session)
    await repo.add(tid, user.user_id, company_id, "AAPL")
    await repo.remove(tid, user.user_id, company_id)

    items = await repo.list_by_user(tid, user.user_id)
    assert items == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_watchlist_repo_exists(session: AsyncSession):
    """exists: True after add, False after remove."""
    tid = uuid.uuid4()
    user = await _insert_user(session, tid)
    company_id = uuid.uuid4()

    repo = WatchlistItemRepository(session)
    assert await repo.exists(tid, user.user_id, company_id) is False

    await repo.add(tid, user.user_id, company_id, "AAPL")
    assert await repo.exists(tid, user.user_id, company_id) is True

    await repo.remove(tid, user.user_id, company_id)
    assert await repo.exists(tid, user.user_id, company_id) is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_watchlist_repo_add_idempotent(session: AsyncSession):
    """add called twice for same entry does not create duplicates."""
    tid = uuid.uuid4()
    user = await _insert_user(session, tid)
    company_id = uuid.uuid4()

    repo = WatchlistItemRepository(session)
    item1 = await repo.add(tid, user.user_id, company_id, "AAPL")
    item2 = await repo.add(tid, user.user_id, company_id, "AAPL")

    assert item1.item_id == item2.item_id

    items = await repo.list_by_user(tid, user.user_id)
    assert len(items) == 1
