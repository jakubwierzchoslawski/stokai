"""
portfolio.portfolio_service — PortfolioService domain service.

Orchestrates portfolio and position lifecycle. Enforces tenant isolation by
passing tenant_id to every repository call. Maps domain errors to typed exceptions
for the API layer to handle.
"""
from __future__ import annotations

import uuid

from src.storage.models.portfolio import Portfolio, Position
from src.portfolio.exceptions import NotFoundError
from src.portfolio.interfaces import ICompanyLookup, IPortfolioRepository, IPositionRepository


class PortfolioService:
    """Domain service for portfolio and position management.

    Dependencies are injected via the constructor (DIP). No repository
    instantiation happens inside this class.
    """

    def __init__(
        self,
        portfolio_repo: IPortfolioRepository,
        position_repo: IPositionRepository,
        company_lookup: ICompanyLookup,
    ) -> None:
        self._portfolio_repo = portfolio_repo
        self._position_repo = position_repo
        self._company_lookup = company_lookup

    # ── Portfolio CRUD ─────────────────────────────────────────────────────────

    async def create_portfolio(
        self,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        name: str,
    ) -> Portfolio:
        """Create a new portfolio for the given user."""
        return await self._portfolio_repo.create(tenant_id, user_id, name)

    async def list_portfolios(
        self,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> list[Portfolio]:
        """Return all portfolios for the user within the tenant."""
        return await self._portfolio_repo.list_by_user(tenant_id, user_id)

    async def get_portfolio(
        self,
        tenant_id: uuid.UUID,
        portfolio_id: uuid.UUID,
    ) -> Portfolio:
        """Return a portfolio, raising NotFoundError if not found or wrong tenant."""
        portfolio = await self._portfolio_repo.get(tenant_id, portfolio_id)
        if portfolio is None:
            raise NotFoundError("Portfolio", portfolio_id)
        return portfolio

    async def delete_portfolio(
        self,
        tenant_id: uuid.UUID,
        portfolio_id: uuid.UUID,
    ) -> None:
        """Delete a portfolio and all its positions (via FK cascade)."""
        await self.get_portfolio(tenant_id, portfolio_id)  # raises if not found
        await self._portfolio_repo.delete(tenant_id, portfolio_id)

    # ── Position CRUD ──────────────────────────────────────────────────────────

    async def add_position(
        self,
        tenant_id: uuid.UUID,
        portfolio_id: uuid.UUID,
        ticker: str,
        shares: float,
        source: str = "manual",
        cost_basis: float | None = None,
    ) -> Position:
        """Add a position to a portfolio, resolving ticker to company_id.

        Raises NotFoundError if the portfolio does not belong to the tenant
        or if the ticker cannot be resolved to a known company.
        """
        await self.get_portfolio(tenant_id, portfolio_id)  # ownership check

        company_id = await self._company_lookup.resolve_ticker(ticker)
        if company_id is None:
            raise NotFoundError("Company with ticker", ticker)

        return await self._position_repo.create(
            tenant_id=tenant_id,
            portfolio_id=portfolio_id,
            company_id=company_id,
            ticker=ticker,
            shares=shares,
            source=source,
            cost_basis=cost_basis,
        )

    async def delete_position(
        self,
        tenant_id: uuid.UUID,
        position_id: uuid.UUID,
    ) -> None:
        """Delete a position, raising NotFoundError if not found or wrong tenant."""
        position = await self._position_repo.get(tenant_id, position_id)
        if position is None:
            raise NotFoundError("Position", position_id)
        await self._position_repo.delete(tenant_id, position_id)

    async def has_any_holding(
        self,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> bool:
        """Return True if the user has at least one position across all portfolios."""
        portfolios = await self._portfolio_repo.list_by_user(tenant_id, user_id)
        for portfolio in portfolios:
            positions = await self._position_repo.list_by_portfolio(
                tenant_id, portfolio.portfolio_id
            )
            if positions:
                return True
        return False
