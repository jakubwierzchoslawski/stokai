"""
Unit tests for the compute_exposure_map step.

All DB queries are mocked via AsyncMock so no real DB is required.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.events.cost_accumulator import CostAccumulator
from src.events.models import ClassificationResult, ExposureCandidate, PipelineContext, RawEvent
from src.events.steps.compute_exposure_map import compute_exposure_map


def _make_ctx(
    geo_regions: list[str] | None = None,
    affected_sectors: list[str] | None = None,
    tickers: list[str] | None = None,
) -> PipelineContext:
    classification = ClassificationResult(
        category=["conflict"],
        intensity=3,
        sentiment="negative",
        geo_regions=geo_regions or ["EMEA"],
        affected_sectors=affected_sectors or ["energy"],
        cameo_code="14",
    )
    return PipelineContext(
        raw_event=RawEvent(
            source_provider="gdelt",
            occurred_at=datetime(2024, 1, 15, tzinfo=timezone.utc),
            raw_payload={"title": "T", "summary": "S"},
        ),
        event_id=uuid.uuid4(),
        classification=classification,
        tickers=tickers or [],
        cost_accumulator=CostAccumulator(),
        langfuse_trace_id="trace-001",
    )


def _make_company_row(
    company_id=None,
    ticker="XOM",
    sector_internal="energy",
    hq_country="DE",
    geo_revenue=None,
):
    row = MagicMock()
    row.company_id = company_id or uuid.uuid4()
    row.ticker = ticker
    row.sector_internal = sector_internal
    row.hq_country = hq_country
    row.geo_revenue = geo_revenue or {}
    return row


@pytest.mark.asyncio
class TestComputeExposureMap:

    async def test_geo_region_match_gives_currency_exposure(self) -> None:
        ctx = _make_ctx(geo_regions=["DE"])
        session = AsyncMock()
        company = _make_company_row(hq_country="DE", sector_internal="materials")
        result_mock = MagicMock()
        result_mock.mappings.return_value = [
            {
                "company_id": company.company_id,
                "ticker": company.ticker,
                "sector_internal": company.sector_internal,
                "hq_country": company.hq_country,
                "geo_revenue": {},
            }
        ]
        session.execute = AsyncMock(return_value=result_mock)

        result = await compute_exposure_map(ctx, session)

        assert len(result.exposures) >= 1
        currency_exp = next(
            (e for e in result.exposures if e.exposure_type == "currency"), None
        )
        assert currency_exp is not None

    async def test_sector_match_gives_sector_exposure(self) -> None:
        ctx = _make_ctx(affected_sectors=["energy"], geo_regions=["APAC"])
        session = AsyncMock()
        company = _make_company_row(sector_internal="energy", hq_country="JP")
        result_mock = MagicMock()
        result_mock.mappings.return_value = [
            {
                "company_id": company.company_id,
                "ticker": "TM",
                "sector_internal": "energy",
                "hq_country": "JP",
                "geo_revenue": {},
            }
        ]
        session.execute = AsyncMock(return_value=result_mock)

        result = await compute_exposure_map(ctx, session)

        sector_exp = next(
            (e for e in result.exposures if e.exposure_type == "sector"), None
        )
        assert sector_exp is not None

    async def test_ticker_match_gives_direct_exposure_with_magnitude_1(self) -> None:
        ctx = _make_ctx(tickers=["XOM"], geo_regions=[], affected_sectors=[])
        session = AsyncMock()
        company_id = uuid.uuid4()
        result_mock = MagicMock()
        result_mock.mappings.return_value = [
            {
                "company_id": company_id,
                "ticker": "XOM",
                "sector_internal": "energy",
                "hq_country": "US",
                "geo_revenue": {},
            }
        ]
        session.execute = AsyncMock(return_value=result_mock)

        result = await compute_exposure_map(ctx, session)

        direct_exp = next(
            (e for e in result.exposures if e.exposure_type == "direct"), None
        )
        assert direct_exp is not None
        assert direct_exp.magnitude == 1.0

    async def test_non_matching_company_excluded(self) -> None:
        ctx = _make_ctx(geo_regions=["EMEA"], affected_sectors=["energy"], tickers=["XOM"])
        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.mappings.return_value = []
        session.execute = AsyncMock(return_value=result_mock)

        result = await compute_exposure_map(ctx, session)

        assert result.exposures == []

    async def test_empty_criteria_returns_empty_exposures(self) -> None:
        ctx = _make_ctx(geo_regions=[], affected_sectors=[], tickers=[])
        session = AsyncMock()

        result = await compute_exposure_map(ctx, session)

        assert result.exposures == []
        session.execute.assert_not_called()

    async def test_sql_uses_parameterised_query(self) -> None:
        ctx = _make_ctx(tickers=["AAPL"])
        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.mappings.return_value = []
        session.execute = AsyncMock(return_value=result_mock)

        await compute_exposure_map(ctx, session)

        call_args = session.execute.call_args
        stmt = call_args[0][0]
        # Must be a SQLAlchemy statement object, not a raw interpolated string
        assert not isinstance(stmt, str), "SQL must be parameterised"
