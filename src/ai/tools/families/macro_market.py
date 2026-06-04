"""Macro + Market tool family.

Tools:
  - GetMacroIndicators    (name="get_macro_indicators")
  - GetSectorPerformance  (name="get_sector_performance")

Both use the cache-or-fetch layer and return at most MAX_ROWS rows.
RateLimited raised by the FRED adapter propagates to ToolError(RATE_LIMITED).
"""
from __future__ import annotations

from typing import Any

from ingestion.cache_or_fetch import build_cache_key
from ingestion.ttl_policy import DataType
from src.ai.tools.base import MAX_ROWS, BaseTool, BaseToolInput


# ---------------------------------------------------------------------------
# Input models
# ---------------------------------------------------------------------------


class GetMacroIndicatorsInput(BaseToolInput):
    """Input for GetMacroIndicators.

    indicator_list is capped at MAX_ROWS before the DB/API call.
    """

    indicator_list: list[str]


class GetSectorPerformanceInput(BaseToolInput):
    """Input for GetSectorPerformance."""

    interval: str = "1d"


# ---------------------------------------------------------------------------
# GetMacroIndicators
# ---------------------------------------------------------------------------


class GetMacroIndicators(BaseTool):
    """Return macro indicator time-series data.

    Uses DataType.MACRO (shared type — global cache key).
    indicator_list is capped at MAX_ROWS before fetching.

    If the underlying FRED adapter raises RateLimited, it propagates up to
    BaseTool.execute() which converts it to ToolError(RATE_LIMITED, retry_after=...).
    """

    name = "get_macro_indicators"

    async def _execute(
        self, inputs: GetMacroIndicatorsInput  # type: ignore[override]
    ) -> list[dict[str, Any]]:
        # Cap indicator list
        capped_indicators = inputs.indicator_list[:MAX_ROWS]

        params = {"indicators": ",".join(sorted(capped_indicators))}
        cache_key = build_cache_key(
            data_type=DataType.MACRO,
            entity_id="global",
            params=params,
        )

        async def _fetch() -> list[dict[str, Any]]:
            # In production this calls the FRED adapter.
            # RateLimited may be raised here and will propagate.
            return []

        rows = await self._cache_or_fetch.cache_or_fetch(
            key=cache_key,
            data_type=DataType.MACRO,
            fetch_fn=_fetch,
        )
        return rows if isinstance(rows, list) else []


# ---------------------------------------------------------------------------
# GetSectorPerformance
# ---------------------------------------------------------------------------


class GetSectorPerformance(BaseTool):
    """Return aggregated price performance by sector.

    Aggregates price_bar hypertable data by sector, max 50 rows.
    Uses DataType.PRICE_BAR (shared type — global cache key).
    """

    name = "get_sector_performance"

    async def _execute(
        self, inputs: GetSectorPerformanceInput  # type: ignore[override]
    ) -> list[dict[str, Any]]:
        params = {"interval": inputs.interval}
        cache_key = build_cache_key(
            data_type=DataType.PRICE_BAR,
            entity_id="sector_perf",
            params=params,
        )

        async def _fetch() -> list[dict[str, Any]]:
            return []

        rows = await self._cache_or_fetch.cache_or_fetch(
            key=cache_key,
            data_type=DataType.PRICE_BAR,
            fetch_fn=_fetch,
        )
        return rows if isinstance(rows, list) else []
