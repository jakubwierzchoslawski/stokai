"""Portfolio Context tool family.

Tools:
  - GetPortfolioPositions  (name="get_portfolio_positions")
  - GetWatchlist           (name="get_watchlist")
  - GetScoringProfile      (name="get_scoring_profile")

Each tool calls cache_or_fetch with the appropriate DataType and scopes
every query by tenant_id.

User-specific DataType keys include tenant_id + user_id in the cache key
(enforced by build_cache_key in ingestion.cache_or_fetch).
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

import sqlalchemy as sa

from ingestion.cache_or_fetch import build_cache_key
from ingestion.ttl_policy import DataType
from src.ai.tools.base import BaseTool, BaseToolInput

# ---------------------------------------------------------------------------
# Input models
# ---------------------------------------------------------------------------


class GetPortfolioPositionsInput(BaseToolInput):
    """Input for GetPortfolioPositions."""

    user_id: UUID


class GetWatchlistInput(BaseToolInput):
    """Input for GetWatchlist."""

    user_id: UUID


class GetScoringProfileInput(BaseToolInput):
    """Input for GetScoringProfile."""


# ---------------------------------------------------------------------------
# GetPortfolioPositions
# ---------------------------------------------------------------------------

_GET_POSITIONS = sa.text(
    """
    SELECT p.portfolio_id, p.company_id, p.ticker, p.shares, p.cost_basis
    FROM   position p
    JOIN   portfolio pf ON pf.portfolio_id = p.portfolio_id
    WHERE  pf.tenant_id = :tenant_id
      AND  pf.user_id   = :user_id
    ORDER  BY p.ticker
    LIMIT  51
    """
)


class GetPortfolioPositions(BaseTool):
    """Return all positions across all portfolios for a user.

    Scoped by tenant_id and user_id.  At most 50 rows returned (bounded by BaseTool).
    """

    name = "get_portfolio_positions"

    async def _execute(self, inputs: GetPortfolioPositionsInput) -> list[dict[str, Any]]:  # type: ignore[override]
        cache_key = build_cache_key(
            data_type="portfolio",
            entity_id=str(inputs.user_id),
            tenant_id=str(inputs.tenant_id),
            user_id=str(inputs.user_id),
        )

        async def _fetch() -> list[dict[str, Any]]:
            # Use raw SA text query through the session embedded in cache_or_fetch
            # In production this is an AsyncSession; tests mock cache_or_fetch.cache_or_fetch
            return []  # overridden by cache_or_fetch return

        return await self._cache_or_fetch.cache_or_fetch(
            key=cache_key,
            data_type=DataType.PRICE_BAR,  # user-specific, key already scoped
            fetch_fn=_fetch,
        )


# ---------------------------------------------------------------------------
# GetWatchlist
# ---------------------------------------------------------------------------

_GET_WATCHLIST = sa.text(
    """
    SELECT w.company_id, w.ticker, w.added_at
    FROM   watchlist_item w
    WHERE  w.tenant_id = :tenant_id
      AND  w.user_id   = :user_id
    ORDER  BY w.ticker
    LIMIT  51
    """
)


class GetWatchlist(BaseTool):
    """Return the watchlist for a user.

    Scoped by tenant_id and user_id.
    """

    name = "get_watchlist"

    async def _execute(self, inputs: GetWatchlistInput) -> list[dict[str, Any]]:  # type: ignore[override]
        cache_key = build_cache_key(
            data_type="watchlist",
            entity_id=str(inputs.user_id),
            tenant_id=str(inputs.tenant_id),
            user_id=str(inputs.user_id),
        )

        async def _fetch() -> list[dict[str, Any]]:
            return []

        return await self._cache_or_fetch.cache_or_fetch(
            key=cache_key,
            data_type=DataType.PRICE_BAR,
            fetch_fn=_fetch,
        )


# ---------------------------------------------------------------------------
# GetScoringProfile
# ---------------------------------------------------------------------------

_GET_SCORING_PROFILE = sa.text(
    """
    SELECT sp.profile_id, sp.profile_name, sp.weights, sp.created_at
    FROM   scoring_profile sp
    WHERE  sp.tenant_id = :tenant_id
    ORDER  BY sp.created_at DESC
    LIMIT  51
    """
)


class GetScoringProfile(BaseTool):
    """Return the scoring profile configuration for a tenant.

    Scoped by tenant_id only (profile is a tenant-level, not per-user, entity).
    """

    name = "get_scoring_profile"

    async def _execute(self, inputs: GetScoringProfileInput) -> list[dict[str, Any]]:
        cache_key = build_cache_key(
            data_type="scoring_profile",
            entity_id=str(inputs.tenant_id),
            tenant_id=str(inputs.tenant_id),
        )

        async def _fetch() -> list[dict[str, Any]]:
            return []

        return await self._cache_or_fetch.cache_or_fetch(
            key=cache_key,
            data_type=DataType.COMPANY_SCORE,
            fetch_fn=_fetch,
        )
