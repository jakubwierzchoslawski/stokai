"""
storage.repositories.price_bar_repository — PriceBar domain model + IPriceBarRepository.

Provides OHLCV price history queries against the price_bar hypertable (TimescaleDB).
All queries are tenant-scoped to prevent IDOR data leakage.

PLAN-F-023 TASK-001
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_INTERNAL_MAX_LIMIT = 1000


class PriceBar(BaseModel):
    """OHLCV price bar for a single time slice."""

    company_id: UUID
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    interval: str  # "1d" | "1h" | "15m"


class IPriceBarRepository(Protocol):
    """Protocol for OHLCV price history access."""

    async def get_ohlcv_history(
        self,
        company_id: UUID,
        tenant_id: UUID,
        interval: str,
        from_ts: datetime,
        to_ts: datetime,
        limit: int = 500,
    ) -> list[PriceBar]:
        """Return OHLCV bars in ascending timestamp order.

        Args:
            company_id: UUID of the company.
            tenant_id: Tenant identifier for IDOR prevention.
            interval: Price bar interval — "1d", "1h", or "15m".
            from_ts: Inclusive start of the time range.
            to_ts: Exclusive end of the time range.
            limit: Maximum number of bars to return; internally capped at 1000.

        Returns:
            List of PriceBar objects ordered by ts ASC.
        """
        ...  # pragma: no cover


class PriceBarRepository:
    """SQLAlchemy 2.0 async implementation of IPriceBarRepository.

    Queries the ``price_bar`` hypertable with compound WHERE clause covering
    company_id, tenant_id, interval, and the ts range. The limit is capped
    at min(requested, 1000) to prevent runaway queries.
    """

    def __init__(self, session: AsyncSession) -> None:
        """Inject the SQLAlchemy async session (DIP)."""
        self._session = session

    async def get_ohlcv_history(
        self,
        company_id: UUID,
        tenant_id: UUID,
        interval: str,
        from_ts: datetime,
        to_ts: datetime,
        limit: int = 500,
    ) -> list[PriceBar]:
        """Return OHLCV bars in ascending ts order, tenant-scoped.

        Args:
            company_id: UUID of the company.
            tenant_id: Tenant identifier for IDOR prevention.
            interval: Price bar interval — "1d", "1h", or "15m".
            from_ts: Inclusive start of the time range.
            to_ts: Exclusive end of the time range.
            limit: Caller-requested limit; silently capped at 1000.

        Returns:
            List of PriceBar objects ordered by ts ASC.  Empty list when no
            matching rows exist.
        """
        effective_limit = min(limit, _INTERNAL_MAX_LIMIT)

        result = await self._session.execute(
            text(
                """
                SELECT company_id, ts, open, high, low, close, volume, interval
                FROM price_bar
                WHERE company_id = :company_id
                  AND tenant_id  = :tenant_id
                  AND interval   = :interval
                  AND ts >= :from_ts
                  AND ts <  :to_ts
                ORDER BY ts ASC
                LIMIT :limit
                """
            ),
            {
                "company_id": str(company_id),
                "tenant_id": str(tenant_id),
                "interval": interval,
                "from_ts": from_ts,
                "to_ts": to_ts,
                "limit": effective_limit,
            },
        )

        rows = result.fetchall()
        bars: list[PriceBar] = []
        for row in rows:
            bars.append(
                PriceBar(
                    company_id=UUID(str(row[0])),
                    ts=row[1],
                    open=float(row[2]),
                    high=float(row[3]),
                    low=float(row[4]),
                    close=float(row[5]),
                    volume=float(row[6]),
                    interval=row[7],
                )
            )

        logger.debug(
            "get_ohlcv_history: company=%s interval=%s rows=%d limit=%d",
            company_id,
            interval,
            len(bars),
            effective_limit,
        )
        return bars
