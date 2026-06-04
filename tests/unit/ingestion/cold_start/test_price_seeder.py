"""
Unit tests for PriceSeeder.

Repository interactions are mocked. Tests verify price_change_t1d computation,
T+1 missing logic, T+2–T+5 fallback, and idempotency via ON CONFLICT DO NOTHING.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, call

import pytest

from src.ingestion.cold_start.price_seeder import (
    EventPriceContext,
    PriceBar,
    PriceSeeder,
    compute_price_change_t1d,
)

_COMPANY_A = uuid.UUID("00000000-0000-0000-0000-000000000001")
_COMPANY_B = uuid.UUID("00000000-0000-0000-0000-000000000002")
_EVENT_ID = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")


def _make_bar(company_id: uuid.UUID, target_date: date, close: float) -> PriceBar:
    return PriceBar(company_id=company_id, ts=target_date, close=close)


def _make_price_repo(bars_by_date: dict[date, list[PriceBar]]) -> AsyncMock:
    """Build a mock price bar repository."""
    repo = AsyncMock()
    repo.get_tracked_company_ids = AsyncMock(return_value=[_COMPANY_A])

    async def get_price_bars(company_ids, target_date):
        return [b for b in bars_by_date.get(target_date, []) if b.company_id in company_ids]

    repo.get_price_bars_for_date = AsyncMock(side_effect=get_price_bars)
    return repo


def _make_exposure_repo() -> AsyncMock:
    repo = AsyncMock()
    repo.upsert_event_exposure = AsyncMock()
    return repo


@pytest.mark.unit
class TestComputePriceChangeTd1:
    """Tests for compute_price_change_t1d helper."""

    def test_positive_change(self):
        """close_t0=100, close_t1=105 → 0.05."""
        result = compute_price_change_t1d(100.0, 105.0)
        assert result == pytest.approx(0.05)

    def test_negative_change(self):
        """close_t0=100, close_t1=95 → -0.05."""
        result = compute_price_change_t1d(100.0, 95.0)
        assert result == pytest.approx(-0.05)

    def test_zero_change(self):
        result = compute_price_change_t1d(100.0, 100.0)
        assert result == pytest.approx(0.0)

    def test_zero_denominator_returns_zero(self):
        """Edge case: close_t0=0 returns 0.0 without raising."""
        result = compute_price_change_t1d(0.0, 100.0)
        assert result == 0.0


@pytest.mark.unit
class TestMissingT1PriceFallback:
    """Tests for T+1 missing → advance to T+2, T+3 logic."""

    @pytest.mark.asyncio
    async def test_t1_missing_falls_back_to_t2(self):
        """When T+1 is missing, PriceSeeder uses T+2 instead."""
        event_date = date(1979, 1, 15)
        t0 = event_date
        t2 = event_date.replace(day=17)

        bars = {
            t0: [_make_bar(_COMPANY_A, t0, 100.0)],
            # T+1 is missing
            t2: [_make_bar(_COMPANY_A, t2, 110.0)],
        }
        price_repo = _make_price_repo(bars)
        exposure_repo = _make_exposure_repo()
        seeder = PriceSeeder(price_bar_repo=price_repo, exposure_repo=exposure_repo)

        ctx = EventPriceContext(
            event_id=_EVENT_ID,
            occurred_at=datetime(1979, 1, 15, tzinfo=timezone.utc),
        )
        written = await seeder.seed_exposures([ctx])
        assert written == 1

        # Verify exposure written with correct price change
        exposure_repo.upsert_event_exposure.assert_called_once()
        call_kwargs = exposure_repo.upsert_event_exposure.call_args
        assert call_kwargs.kwargs["price_change_t1d"] == pytest.approx(0.10)

    @pytest.mark.asyncio
    async def test_missing_through_t5_returns_none_no_exception(self):
        """Missing price bar through T+5 → no exception; logs warning; no write."""
        event_date = date(1979, 1, 15)
        t0 = event_date
        bars = {
            t0: [_make_bar(_COMPANY_A, t0, 100.0)],
            # All T+1 through T+5 missing
        }
        price_repo = _make_price_repo(bars)
        exposure_repo = _make_exposure_repo()
        seeder = PriceSeeder(price_bar_repo=price_repo, exposure_repo=exposure_repo)

        ctx = EventPriceContext(
            event_id=_EVENT_ID,
            occurred_at=datetime(1979, 1, 15, tzinfo=timezone.utc),
        )
        # Should not raise
        written = await seeder.seed_exposures([ctx])
        assert written == 0
        exposure_repo.upsert_event_exposure.assert_not_called()


@pytest.mark.unit
class TestIdempotentWrite:
    """Tests for ON CONFLICT DO NOTHING semantics via mock."""

    @pytest.mark.asyncio
    async def test_upsert_event_exposure_called_with_on_conflict_semantics(self):
        """Verify upsert_event_exposure is called (which must use ON CONFLICT DO NOTHING)."""
        event_date = date(1979, 1, 15)
        t0 = event_date
        t1 = event_date.replace(day=16)

        bars = {
            t0: [_make_bar(_COMPANY_A, t0, 100.0)],
            t1: [_make_bar(_COMPANY_A, t1, 105.0)],
        }
        price_repo = _make_price_repo(bars)
        exposure_repo = _make_exposure_repo()
        seeder = PriceSeeder(price_bar_repo=price_repo, exposure_repo=exposure_repo)

        ctx = EventPriceContext(
            event_id=_EVENT_ID,
            occurred_at=datetime(1979, 1, 15, tzinfo=timezone.utc),
        )
        await seeder.seed_exposures([ctx])

        # upsert_event_exposure is the idempotent write method
        exposure_repo.upsert_event_exposure.assert_called_once_with(
            event_id=_EVENT_ID,
            company_id=_COMPANY_A,
            price_change_t1d=pytest.approx(0.05),
        )

    @pytest.mark.asyncio
    async def test_dry_run_skips_db_write(self):
        """dry_run=True computes the change but does NOT call upsert."""
        event_date = date(1979, 1, 15)
        t0 = event_date
        t1 = event_date.replace(day=16)

        bars = {
            t0: [_make_bar(_COMPANY_A, t0, 100.0)],
            t1: [_make_bar(_COMPANY_A, t1, 105.0)],
        }
        price_repo = _make_price_repo(bars)
        exposure_repo = _make_exposure_repo()
        seeder = PriceSeeder(price_bar_repo=price_repo, exposure_repo=exposure_repo)

        ctx = EventPriceContext(event_id=_EVENT_ID, occurred_at=datetime(1979, 1, 15, tzinfo=timezone.utc))
        written = await seeder.seed_exposures([ctx], dry_run=True)

        exposure_repo.upsert_event_exposure.assert_not_called()
        assert written == 1  # still counted as "would be written"
