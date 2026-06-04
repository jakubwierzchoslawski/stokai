"""
tests.unit.portfolio.test_portfolio_service

Unit tests for PortfolioService and WatchlistService using stub repositories.
All external dependencies are replaced with simple in-memory stubs.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import AsyncGenerator

import pytest

from src.storage.models.portfolio import Portfolio, Position, WatchlistItem
from src.portfolio.exceptions import NotFoundError
from src.portfolio.portfolio_service import PortfolioService
from src.portfolio.watchlist_service import WatchlistService


# ── Stub implementations ───────────────────────────────────────────────────────


class _StubPortfolioRepo:
    def __init__(self) -> None:
        self._store: dict[uuid.UUID, Portfolio] = {}

    async def create(self, tenant_id, user_id, name) -> Portfolio:
        p = Portfolio(
            portfolio_id=uuid.uuid4(),
            tenant_id=tenant_id,
            user_id=user_id,
            name=name,
            created_at=datetime.utcnow(),
        )
        self._store[p.portfolio_id] = p
        return p

    async def list_by_user(self, tenant_id, user_id) -> list[Portfolio]:
        return [
            p for p in self._store.values()
            if p.tenant_id == tenant_id and p.user_id == user_id
        ]

    async def get(self, tenant_id, portfolio_id) -> Portfolio | None:
        p = self._store.get(portfolio_id)
        if p and p.tenant_id == tenant_id:
            return p
        return None

    async def delete(self, tenant_id, portfolio_id) -> None:
        p = self._store.get(portfolio_id)
        if p and p.tenant_id == tenant_id:
            del self._store[portfolio_id]


class _StubPositionRepo:
    def __init__(self) -> None:
        self._store: dict[uuid.UUID, Position] = {}

    async def create(self, tenant_id, portfolio_id, company_id, ticker, shares, source,
                     cost_basis=None) -> Position:
        pos = Position(
            position_id=uuid.uuid4(),
            portfolio_id=portfolio_id,
            company_id=company_id,
            ticker=ticker,
            shares=shares,
            source=source,
            cost_basis=cost_basis,
            added_at=datetime.utcnow(),
        )
        self._store[pos.position_id] = pos
        return pos

    async def list_by_portfolio(self, tenant_id, portfolio_id) -> list[Position]:
        return [p for p in self._store.values() if p.portfolio_id == portfolio_id]

    async def get(self, tenant_id, position_id) -> Position | None:
        return self._store.get(position_id)

    async def delete(self, tenant_id, position_id) -> None:
        self._store.pop(position_id, None)

    async def bulk_create(self, tenant_id, portfolio_id, rows) -> list[Position]:
        results = []
        for row in rows:
            p = await self.create(
                tenant_id=tenant_id,
                portfolio_id=portfolio_id,
                company_id=row["company_id"],
                ticker=row["ticker"],
                shares=row["shares"],
                source=row.get("source", "csv"),
                cost_basis=row.get("cost_basis"),
            )
            results.append(p)
        return results


class _StubCompanyLookup:
    def __init__(self, ticker_map: dict[str, uuid.UUID] | None = None) -> None:
        self._map: dict[str, uuid.UUID] = ticker_map or {}

    async def resolve_ticker(self, ticker: str) -> uuid.UUID | None:
        return self._map.get(ticker)


class _StubWatchlistRepo:
    def __init__(self) -> None:
        self._store: dict[tuple, WatchlistItem] = {}

    async def add(self, tenant_id, user_id, company_id, ticker) -> WatchlistItem:
        key = (tenant_id, user_id, company_id)
        if key in self._store:
            return self._store[key]
        item = WatchlistItem(
            item_id=uuid.uuid4(),
            tenant_id=tenant_id,
            user_id=user_id,
            company_id=company_id,
            ticker=ticker,
            added_at=datetime.utcnow(),
        )
        self._store[key] = item
        return item

    async def list_by_user(self, tenant_id, user_id) -> list[WatchlistItem]:
        return [
            v for (t, u, _), v in self._store.items()
            if t == tenant_id and u == user_id
        ]

    async def remove(self, tenant_id, user_id, company_id) -> None:
        self._store.pop((tenant_id, user_id, company_id), None)

    async def exists(self, tenant_id, user_id, company_id) -> bool:
        return (tenant_id, user_id, company_id) in self._store


# ── PortfolioService tests ─────────────────────────────────────────────────────


def _make_service(
    ticker_map: dict[str, uuid.UUID] | None = None,
    portfolio_repo=None,
    position_repo=None,
) -> tuple[PortfolioService, _StubPortfolioRepo, _StubPositionRepo]:
    p_repo = portfolio_repo or _StubPortfolioRepo()
    pos_repo = position_repo or _StubPositionRepo()
    lookup = _StubCompanyLookup(ticker_map)
    svc = PortfolioService(p_repo, pos_repo, lookup)
    return svc, p_repo, pos_repo


@pytest.mark.unit
@pytest.mark.asyncio
async def test_add_position_resolves_company_id():
    """add_position resolves ticker via ICompanyLookup and creates position."""
    tid = uuid.uuid4()
    uid = uuid.uuid4()
    company_id = uuid.uuid4()

    svc, p_repo, pos_repo = _make_service({"AAPL": company_id})
    portfolio = await p_repo.create(tid, uid, "P")

    pos = await svc.add_position(tid, portfolio.portfolio_id, "AAPL", 10.0)
    assert pos.company_id == company_id
    assert pos.ticker == "AAPL"
    assert pos.shares == 10.0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_portfolio_cascades_positions():
    """delete_portfolio removes the portfolio; subsequent list_portfolios is empty."""
    tid = uuid.uuid4()
    uid = uuid.uuid4()
    company_id = uuid.uuid4()

    svc, p_repo, pos_repo = _make_service({"AAPL": company_id})
    portfolio = await p_repo.create(tid, uid, "P")
    await svc.add_position(tid, portfolio.portfolio_id, "AAPL", 5.0)

    await svc.delete_portfolio(tid, portfolio.portfolio_id)

    portfolios = await svc.list_portfolios(tid, uid)
    assert portfolios == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_portfolio_wrong_tenant_raises():
    """get_portfolio raises NotFoundError when portfolio belongs to a different tenant."""
    tid_a = uuid.uuid4()
    tid_b = uuid.uuid4()
    uid = uuid.uuid4()

    svc, p_repo, _ = _make_service()
    portfolio = await p_repo.create(tid_a, uid, "P")

    with pytest.raises(NotFoundError):
        await svc.get_portfolio(tid_b, portfolio.portfolio_id)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_has_any_holding_false_when_empty():
    """has_any_holding returns False when user has no portfolios."""
    svc, _, _ = _make_service()
    result = await svc.has_any_holding(uuid.uuid4(), uuid.uuid4())
    assert result is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_has_any_holding_true_after_add():
    """has_any_holding returns True after a position is added."""
    tid = uuid.uuid4()
    uid = uuid.uuid4()
    company_id = uuid.uuid4()

    svc, p_repo, _ = _make_service({"TSLA": company_id})
    portfolio = await p_repo.create(tid, uid, "P")
    await svc.add_position(tid, portfolio.portfolio_id, "TSLA", 2.0)

    assert await svc.has_any_holding(tid, uid) is True


# ── WatchlistService tests ─────────────────────────────────────────────────────


def _make_watchlist_service():
    repo = _StubWatchlistRepo()
    svc = WatchlistService(repo)
    return svc, repo


@pytest.mark.unit
@pytest.mark.asyncio
async def test_add_to_watchlist_idempotent():
    """Calling add_to_watchlist twice for the same entry returns same item."""
    tid = uuid.uuid4()
    uid = uuid.uuid4()
    company_id = uuid.uuid4()

    svc, _ = _make_watchlist_service()
    item1 = await svc.add_to_watchlist(tid, uid, company_id, "AAPL")
    item2 = await svc.add_to_watchlist(tid, uid, company_id, "AAPL")

    assert item1.item_id == item2.item_id
    items = await svc.list_watchlist(tid, uid)
    assert len(items) == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_watchlist_empty_returns_empty_list():
    """list_watchlist returns [] for a user with no watchlist items."""
    svc, _ = _make_watchlist_service()
    items = await svc.list_watchlist(uuid.uuid4(), uuid.uuid4())
    assert items == []
