"""
PriceSeeder — computes price_change_t1d for seeded historical events.

For each seeded event, fetches price_bar rows for all tracked companies and
computes price_change_t1d = (close_t1 - close_t0) / close_t0.

If T+1 is missing (weekend/holiday), advances to T+2, T+3, up to T+5.
If still absent, logs a warning and skips without raising.

All writes use INSERT ... ON CONFLICT DO NOTHING for idempotency (REQ-N-011).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Protocol
from uuid import UUID

logger = logging.getLogger(__name__)

# Maximum trading days to look ahead when T+1 is missing
MAX_LOOKAHEAD_DAYS = 5


@dataclass
class PriceBar:
    """Minimal price bar row needed for price_change_t1d calculation."""

    company_id: UUID
    ts: date
    close: float


class IPriceBarRepository(Protocol):
    """Minimal protocol for price_bar read access (DIP)."""

    async def get_price_bars_for_date(
        self,
        company_ids: list[UUID],
        target_date: date,
    ) -> list[PriceBar]:
        """Return price bars for the given companies on the exact target date."""
        ...

    async def get_tracked_company_ids(self) -> list[UUID]:
        """Return all company_ids where is_tracked=True."""
        ...


class IEventExposureRepository(Protocol):
    """Minimal protocol for event_exposure write access (DIP)."""

    async def upsert_event_exposure(
        self,
        event_id: UUID,
        company_id: UUID,
        price_change_t1d: float,
    ) -> None:
        """Insert (event_id, company_id, price_change_t1d) with ON CONFLICT DO NOTHING."""
        ...


@dataclass
class EventPriceContext:
    """Bundle of an event_id and its occurred_at date for seeding."""

    event_id: UUID
    occurred_at: datetime


class PriceSeeder:
    """Computes and stores price_change_t1d for historical events.

    Args:
        price_bar_repo: Repository for reading price_bar rows.
        exposure_repo: Repository for writing event_exposure rows.
    """

    def __init__(
        self,
        price_bar_repo: IPriceBarRepository,
        exposure_repo: IEventExposureRepository,
    ) -> None:
        self._price_bar_repo = price_bar_repo
        self._exposure_repo = exposure_repo

    async def seed_exposures(
        self,
        events: list[EventPriceContext],
        dry_run: bool = False,
    ) -> int:
        """Compute and store price_change_t1d for each event.

        Returns the number of event_exposure rows written.
        """
        company_ids = await self._price_bar_repo.get_tracked_company_ids()
        if not company_ids:
            logger.warning("PriceSeeder: no tracked companies found; skipping exposure seeding.")
            return 0

        written = 0
        for ctx in events:
            t0_date = ctx.occurred_at.date()
            t0_bars = await self._price_bar_repo.get_price_bars_for_date(company_ids, t0_date)
            t0_map: dict[UUID, float] = {b.company_id: b.close for b in t0_bars}

            for company_id in company_ids:
                close_t0 = t0_map.get(company_id)
                if close_t0 is None:
                    continue  # No T+0 bar — can't compute change

                close_t1, found_offset = await self._find_next_price(
                    company_id, t0_date, company_ids
                )
                if close_t1 is None:
                    logger.warning(
                        "PriceSeeder: no price bar found for company=%s within T+%d of event %s",
                        company_id,
                        MAX_LOOKAHEAD_DAYS,
                        ctx.event_id,
                    )
                    continue

                price_change = compute_price_change_t1d(close_t0, close_t1)
                if not dry_run:
                    await self._exposure_repo.upsert_event_exposure(
                        event_id=ctx.event_id,
                        company_id=company_id,
                        price_change_t1d=price_change,
                    )
                written += 1

        return written

    async def _find_next_price(
        self,
        company_id: UUID,
        base_date: date,
        all_company_ids: list[UUID],
    ) -> tuple[float | None, int]:
        """Find the next available trading day price starting from T+1.

        Returns (close_price, offset_days) or (None, 0) if not found within T+5.
        """
        for offset in range(1, MAX_LOOKAHEAD_DAYS + 1):
            target_date = base_date + timedelta(days=offset)
            bars = await self._price_bar_repo.get_price_bars_for_date(
                [company_id], target_date
            )
            if bars:
                return bars[0].close, offset
        return None, 0


def compute_price_change_t1d(close_t0: float, close_t1: float) -> float:
    """Compute relative price change: (close_t1 - close_t0) / close_t0.

    Args:
        close_t0: Closing price at T+0.
        close_t1: Closing price at T+1 (or next available trading day).

    Returns:
        Fractional price change, e.g. 0.05 for +5%, -0.05 for -5%.
    """
    if close_t0 == 0.0:
        logger.warning("compute_price_change_t1d: close_t0 is zero; returning 0.0")
        return 0.0
    return (close_t1 - close_t0) / close_t0
