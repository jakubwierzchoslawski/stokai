"""
Unit tests for compute_exposure_map (Step 4 of the Mode A Reactive Pipeline).

Tests:
  - test_high_geo_revenue_region_produces_high_magnitude
  - test_sector_mismatch_reduces_magnitude
  - test_negative_sentiment_sets_direction_positive_one
  - test_positive_sentiment_sets_direction_negative_one
  - test_magnitude_below_threshold_excluded
  - test_zero_geo_revenue_produces_zero_geo_weight

All DB interactions are mocked via AsyncMock so no real database is required.

PLAN-F-003 TASK-004.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest

from src.event_pipeline.exposure_mapping import (
    ExposureRecord,
    TrackedCompany,
    compute_exposure_map,
)
from src.event_pipeline.pipeline_state import PipelineContext


def _make_company(
    sector_internal: str = "energy",
    geo_revenue: dict | None = None,
    market_cap_weight: float = 1.0,
) -> TrackedCompany:
    return TrackedCompany(
        company_id=uuid.uuid4(),
        sector_internal=sector_internal,
        sector_gics="Energy",
        geo_revenue=geo_revenue or {"EMEA": 0.8, "APAC": 0.2},
        market_cap_weight=market_cap_weight,
    )


def _make_ctx(
    geo_regions: list[str] | None = None,
    sectors_affected: list[str] | None = None,
    event_intensity: int = 5,
    sentiment: str = "negative",
    tenant_id: uuid.UUID | None = None,
) -> PipelineContext:
    return PipelineContext(
        tenant_id=tenant_id or uuid.uuid4(),
        geo_regions=geo_regions or ["EMEA"],
        sectors_affected=sectors_affected or ["energy"],
        event_intensity=event_intensity,
        sentiment=sentiment,
    )


def _make_company_repo(companies: list[TrackedCompany]) -> AsyncMock:
    repo = AsyncMock()
    repo.get_tracked_companies = AsyncMock(return_value=companies)
    return repo


@pytest.mark.asyncio
class TestComputeExposureMap:
    """compute_exposure_map computes magnitudes and directions correctly."""

    async def test_high_geo_revenue_region_produces_high_magnitude(self) -> None:
        """A company with 80% revenue from the affected region gets high magnitude."""
        company = _make_company(geo_revenue={"EMEA": 0.8, "APAC": 0.2}, market_cap_weight=1.0)
        ctx = _make_ctx(geo_regions=["EMEA"], event_intensity=5, sentiment="negative")
        repo = _make_company_repo([company])

        result = await compute_exposure_map(ctx, repo, exposure_threshold=0.0)

        assert len(result.exposures) == 1
        record: ExposureRecord = result.exposures[0]
        # magnitude = 1.0 * (0.8 * 0.7 + 1.0 * 0.3) * 5/5 = 0.56 + 0.30 = 0.86
        assert record.magnitude > 0.8
        assert record.geo_weight == pytest.approx(0.8)

    async def test_sector_mismatch_reduces_magnitude(self) -> None:
        """A company in a non-matching sector has sector_match=0.0, reducing magnitude."""
        company = _make_company(
            sector_internal="technology",  # mismatches sectors_affected=["energy"]
            geo_revenue={"EMEA": 0.5},
            market_cap_weight=1.0,
        )
        ctx = _make_ctx(geo_regions=["EMEA"], sectors_affected=["energy"], event_intensity=5)
        repo = _make_company_repo([company])

        result = await compute_exposure_map(ctx, repo, exposure_threshold=0.0)

        assert len(result.exposures) == 1
        record: ExposureRecord = result.exposures[0]
        # sector_match = 0.0, so magnitude = 1.0 * (0.5 * 0.7 + 0.0 * 0.3) * 1.0 = 0.35
        assert record.sector_match == pytest.approx(0.0)
        assert record.magnitude == pytest.approx(0.35)

    async def test_negative_sentiment_sets_direction_positive_one(self) -> None:
        """Negative sentiment produces direction = +1."""
        company = _make_company(geo_revenue={"EMEA": 1.0}, market_cap_weight=1.0)
        ctx = _make_ctx(sentiment="negative", event_intensity=5)
        repo = _make_company_repo([company])

        result = await compute_exposure_map(ctx, repo, exposure_threshold=0.0)

        assert len(result.exposures) == 1
        assert result.exposures[0].direction == 1

    async def test_positive_sentiment_sets_direction_negative_one(self) -> None:
        """Non-negative sentiment produces direction = -1."""
        company = _make_company(geo_revenue={"EMEA": 1.0}, market_cap_weight=1.0)
        ctx = _make_ctx(sentiment="positive", event_intensity=5)
        repo = _make_company_repo([company])

        result = await compute_exposure_map(ctx, repo, exposure_threshold=0.0)

        assert len(result.exposures) == 1
        assert result.exposures[0].direction == -1

    async def test_magnitude_below_threshold_excluded(self) -> None:
        """Exposures with magnitude <= exposure_threshold are excluded."""
        # market_cap_weight=0.01 → small magnitude well below 0.05 default
        company = _make_company(geo_revenue={"EMEA": 0.1}, market_cap_weight=0.01)
        ctx = _make_ctx(geo_regions=["EMEA"], event_intensity=1)
        repo = _make_company_repo([company])

        result = await compute_exposure_map(ctx, repo, exposure_threshold=0.05)

        # magnitude = 0.01 * (0.1 * 0.7 + 1.0 * 0.3) * 1/5 = 0.01 * 0.37 * 0.2 = 0.00074
        assert result.exposures == []

    async def test_zero_geo_revenue_produces_zero_geo_weight(self) -> None:
        """A company with no revenue in the affected region has geo_weight=0.0."""
        company = _make_company(
            sector_internal="energy",
            geo_revenue={"APAC": 1.0},  # no EMEA revenue
            market_cap_weight=1.0,
        )
        ctx = _make_ctx(geo_regions=["EMEA"], sectors_affected=["energy"], event_intensity=5)
        repo = _make_company_repo([company])

        result = await compute_exposure_map(ctx, repo, exposure_threshold=0.0)

        assert len(result.exposures) == 1
        record: ExposureRecord = result.exposures[0]
        assert record.geo_weight == pytest.approx(0.0)
        # Only sector contributes: magnitude = 1.0 * (0.0 * 0.7 + 1.0 * 0.3) * 1.0 = 0.3
        assert record.magnitude == pytest.approx(0.3)

    async def test_empty_company_list_returns_no_exposures(self) -> None:
        """When no companies are tracked, exposures list is empty."""
        ctx = _make_ctx()
        repo = _make_company_repo([])

        result = await compute_exposure_map(ctx, repo)

        assert result.exposures == []

    async def test_multiple_regions_accumulates_geo_weight(self) -> None:
        """geo_weight sums revenue across all matching regions."""
        company = _make_company(
            geo_revenue={"EMEA": 0.4, "APAC": 0.3, "LATAM": 0.3},
            market_cap_weight=1.0,
        )
        ctx = _make_ctx(geo_regions=["EMEA", "APAC"], event_intensity=5, sectors_affected=[])
        repo = _make_company_repo([company])

        result = await compute_exposure_map(ctx, repo, exposure_threshold=0.0)

        assert len(result.exposures) == 1
        record = result.exposures[0]
        # geo_weight = 0.4 + 0.3 = 0.7
        assert record.geo_weight == pytest.approx(0.7)
