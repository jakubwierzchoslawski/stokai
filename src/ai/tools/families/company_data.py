"""Company Data tool family.

Tools:
  - GetCompanyFundamentals  (name="get_company_fundamentals")
  - GetCompanyScores        (name="get_company_scores")
  - GetPriceHistory         (name="get_price_history")

All tools scope queries by tenant_id.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from ingestion.cache_or_fetch import build_cache_key
from ingestion.ttl_policy import DataType
from src.ai.tools.base import MAX_ROWS, BaseTool, BaseToolInput

# ---------------------------------------------------------------------------
# Input models
# ---------------------------------------------------------------------------


class GetCompanyFundamentalsInput(BaseToolInput):
    """Input for GetCompanyFundamentals."""

    ticker: str


class GetCompanyScoresInput(BaseToolInput):
    """Input for GetCompanyScores."""

    ticker: str


class GetPriceHistoryInput(BaseToolInput):
    """Input for GetPriceHistory."""

    ticker: str
    from_date: str
    to_date: str
    interval: str = "1d"


# ---------------------------------------------------------------------------
# GetCompanyFundamentals
# ---------------------------------------------------------------------------


class GetCompanyFundamentals(BaseTool):
    """Return fundamental financial data for a company.

    Uses DataType.FUNDAMENTALS (shared type — global cache, no tenant scoping in key).
    """

    name = "get_company_fundamentals"

    async def _execute(self, inputs: GetCompanyFundamentalsInput) -> list[dict[str, Any]]:  # type: ignore[override]
        cache_key = build_cache_key(
            data_type=DataType.FUNDAMENTALS,
            entity_id=inputs.ticker,
        )

        async def _fetch() -> list[dict[str, Any]]:
            return []

        return await self._cache_or_fetch.cache_or_fetch(
            key=cache_key,
            data_type=DataType.FUNDAMENTALS,
            fetch_fn=_fetch,
        )


# ---------------------------------------------------------------------------
# GetCompanyScores
# ---------------------------------------------------------------------------


class GetCompanyScores(BaseTool):
    """Return AI-generated scores for a company, scoped to the tenant.

    Uses DataType.COMPANY_SCORE which is event-driven invalidated.
    Score results are tenant-scoped (different tenants may have different scoring profiles).
    """

    name = "get_company_scores"

    async def _execute(self, inputs: GetCompanyScoresInput) -> list[dict[str, Any]]:  # type: ignore[override]
        cache_key = build_cache_key(
            data_type=DataType.COMPANY_SCORE,
            entity_id=inputs.ticker,
            tenant_id=str(inputs.tenant_id),
        )

        async def _fetch() -> list[dict[str, Any]]:
            return []

        return await self._cache_or_fetch.cache_or_fetch(
            key=cache_key,
            data_type=DataType.COMPANY_SCORE,
            fetch_fn=_fetch,
        )


# ---------------------------------------------------------------------------
# GetPriceHistory
# ---------------------------------------------------------------------------


class GetPriceHistory(BaseTool):
    """Return OHLCV price bars for a company.

    Uses DataType.PRICE_BAR_HISTORICAL (shared, immutable for past dates).
    At most MAX_ROWS bars returned — bounded by BaseTool.execute().
    """

    name = "get_price_history"

    async def _execute(self, inputs: GetPriceHistoryInput) -> list[dict[str, Any]]:  # type: ignore[override]
        params = {
            "from_date": inputs.from_date,
            "to_date": inputs.to_date,
            "interval": inputs.interval,
        }
        cache_key = build_cache_key(
            data_type=DataType.PRICE_BAR_HISTORICAL,
            entity_id=inputs.ticker,
            params=params,
        )

        async def _fetch() -> list[dict[str, Any]]:
            return []

        rows = await self._cache_or_fetch.cache_or_fetch(
            key=cache_key,
            data_type=DataType.PRICE_BAR_HISTORICAL,
            fetch_fn=_fetch,
        )
        # Enforce MAX_ROWS at the source fetch level too (belt-and-suspenders;
        # BaseTool.execute() also calls ToolResult.from_rows which re-truncates)
        return rows[:MAX_ROWS + 1] if isinstance(rows, list) else rows
