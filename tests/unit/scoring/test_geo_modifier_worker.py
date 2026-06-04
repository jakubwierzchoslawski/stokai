"""Unit tests for the GeoModifierWorker Celery task (apply_geo_modifier).

TDD: Tests were written before the implementation.
PLAN-F-018 TASK-005
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch, call
from uuid import uuid4

import pytest

from src.storage.interfaces.i_event_exposure_repository import ExposureRow
from src.scoring.schemas.indicator import IndicatorRecord
from src.scoring.schemas.company_score import CompanyScoreRecord
from src.scoring.schemas.geo_modifier import GeoModifierPayload
from src.scoring.repositories.interfaces import GeoAdjustedUpdate


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_indicator(
    *,
    tenant_id=None,
    geo_weight: float = 0.5,
    indicator_id=None,
) -> IndicatorRecord:
    return IndicatorRecord(
        indicator_id=indicator_id or uuid4(),
        tenant_id=tenant_id or uuid4(),
        name="Test Indicator",
        formula_dsl="revenue",
        normalization_mode="percentile",
        normalization_config={},
        direction="higher_better",
        geo_weight=geo_weight,
        version=1,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def _make_score_record(
    *,
    company_id=None,
    indicator_id=None,
    tenant_id=None,
    score: float = 80.0,
    geo_adjusted: float | None = None,
) -> CompanyScoreRecord:
    return CompanyScoreRecord(
        score_id=uuid4(),
        company_id=company_id or uuid4(),
        indicator_id=indicator_id or uuid4(),
        tenant_id=tenant_id or uuid4(),
        raw_value=score,
        score=score,
        percentile=50.0,
        geo_adjusted=geo_adjusted,
        inputs_hash="abc123",
        computed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestApplyGeoModifierTask:
    """Tests for the apply_geo_modifier async worker function."""

    @pytest.mark.asyncio
    async def test_happy_path_formula_correct(self):
        """Given two exposures and one indicator with geo_weight=0.5:
        - company A: magnitude=0.4, direction=positive → geo_adjusted = 80 × 1.2 = 96.0
        - company B: magnitude=0.2, direction=negative → geo_adjusted = 80 × 0.9 = 72.0
        """
        from src.scoring.geo_modifier_worker import _run_geo_modifier

        event_id = uuid4()
        tenant_id = uuid4()
        indicator_id = uuid4()
        company_a = uuid4()
        company_b = uuid4()

        exposures = [
            ExposureRow(company_id=company_a, exposure_type="geo", direction="positive", magnitude=0.4),
            ExposureRow(company_id=company_b, exposure_type="geo", direction="negative", magnitude=0.2),
        ]
        indicator = _make_indicator(tenant_id=tenant_id, geo_weight=0.5, indicator_id=indicator_id)
        score_a = _make_score_record(company_id=company_a, indicator_id=indicator_id, tenant_id=tenant_id, score=80.0)
        score_b = _make_score_record(company_id=company_b, indicator_id=indicator_id, tenant_id=tenant_id, score=80.0)

        mock_exposure_repo = AsyncMock()
        mock_exposure_repo.get_by_event.return_value = exposures

        mock_indicator_repo = AsyncMock()
        mock_indicator_repo.list_by_tenant.return_value = [indicator]

        mock_score_repo = AsyncMock()
        mock_score_repo.get_current.side_effect = [score_a, score_b]
        mock_score_repo.bulk_update_geo_adjusted.return_value = 2

        mock_broadcaster = AsyncMock()

        # Mock company ticker lookup
        mock_company_repo = AsyncMock()
        mock_company_repo.get_tickers_by_ids.return_value = {
            company_a: "AAPL",
            company_b: "MSFT",
        }

        result = await _run_geo_modifier(
            event_id=event_id,
            tenant_id=tenant_id,
            exposure_repo=mock_exposure_repo,
            indicator_repo=mock_indicator_repo,
            score_repo=mock_score_repo,
            company_repo=mock_company_repo,
            broadcaster=mock_broadcaster,
        )

        assert result["companies_updated"] == 2
        mock_score_repo.bulk_update_geo_adjusted.assert_called_once()

        # Inspect the updates
        updates = mock_score_repo.bulk_update_geo_adjusted.call_args[0][0]
        updates_by_company = {u.company_id: u for u in updates}

        assert abs(updates_by_company[company_a].geo_adjusted - 96.0) < 0.001
        assert abs(updates_by_company[company_b].geo_adjusted - 72.0) < 0.001

    @pytest.mark.asyncio
    async def test_empty_exposures_no_write_no_broadcast(self):
        """Empty exposure list → no bulk_update_geo_adjusted call, no broadcast, returns 0."""
        from src.scoring.geo_modifier_worker import _run_geo_modifier

        event_id = uuid4()
        tenant_id = uuid4()

        mock_exposure_repo = AsyncMock()
        mock_exposure_repo.get_by_event.return_value = []

        mock_indicator_repo = AsyncMock()
        mock_score_repo = AsyncMock()
        mock_broadcaster = AsyncMock()
        mock_company_repo = AsyncMock()

        result = await _run_geo_modifier(
            event_id=event_id,
            tenant_id=tenant_id,
            exposure_repo=mock_exposure_repo,
            indicator_repo=mock_indicator_repo,
            score_repo=mock_score_repo,
            company_repo=mock_company_repo,
            broadcaster=mock_broadcaster,
        )

        assert result["companies_updated"] == 0
        mock_score_repo.bulk_update_geo_adjusted.assert_not_called()
        mock_broadcaster.assert_not_called()

    @pytest.mark.asyncio
    async def test_all_zero_geo_weight_no_update_no_broadcast(self):
        """All indicators have geo_weight == 0 → no updates, no broadcast."""
        from src.scoring.geo_modifier_worker import _run_geo_modifier

        event_id = uuid4()
        tenant_id = uuid4()
        company_a = uuid4()

        exposures = [
            ExposureRow(company_id=company_a, exposure_type="geo", direction="positive", magnitude=0.5),
        ]
        indicator_zero = _make_indicator(tenant_id=tenant_id, geo_weight=0.0)

        mock_exposure_repo = AsyncMock()
        mock_exposure_repo.get_by_event.return_value = exposures

        mock_indicator_repo = AsyncMock()
        mock_indicator_repo.list_by_tenant.return_value = [indicator_zero]

        mock_score_repo = AsyncMock()
        mock_broadcaster = AsyncMock()
        mock_company_repo = AsyncMock()

        result = await _run_geo_modifier(
            event_id=event_id,
            tenant_id=tenant_id,
            exposure_repo=mock_exposure_repo,
            indicator_repo=mock_indicator_repo,
            score_repo=mock_score_repo,
            company_repo=mock_company_repo,
            broadcaster=mock_broadcaster,
        )

        assert result["companies_updated"] == 0
        mock_score_repo.bulk_update_geo_adjusted.assert_not_called()
        mock_broadcaster.assert_not_called()

    @pytest.mark.asyncio
    async def test_missing_base_score_row_skipped_no_error(self):
        """Company with no company_score row is silently skipped (no KeyError)."""
        from src.scoring.geo_modifier_worker import _run_geo_modifier

        event_id = uuid4()
        tenant_id = uuid4()
        indicator_id = uuid4()
        company_a = uuid4()

        exposures = [
            ExposureRow(company_id=company_a, exposure_type="geo", direction="positive", magnitude=0.5),
        ]
        indicator = _make_indicator(tenant_id=tenant_id, geo_weight=0.5, indicator_id=indicator_id)

        mock_exposure_repo = AsyncMock()
        mock_exposure_repo.get_by_event.return_value = exposures

        mock_indicator_repo = AsyncMock()
        mock_indicator_repo.list_by_tenant.return_value = [indicator]

        mock_score_repo = AsyncMock()
        # No existing score row
        mock_score_repo.get_current.return_value = None
        mock_score_repo.bulk_update_geo_adjusted.return_value = 0

        mock_broadcaster = AsyncMock()
        mock_company_repo = AsyncMock()
        mock_company_repo.get_tickers_by_ids.return_value = {}

        result = await _run_geo_modifier(
            event_id=event_id,
            tenant_id=tenant_id,
            exposure_repo=mock_exposure_repo,
            indicator_repo=mock_indicator_repo,
            score_repo=mock_score_repo,
            company_repo=mock_company_repo,
            broadcaster=mock_broadcaster,
        )

        # Should not raise; companies_updated = 0
        assert result["companies_updated"] == 0

    @pytest.mark.asyncio
    async def test_broadcast_called_once_after_all_writes(self):
        """broadcast is called exactly once after all bulk_update_geo_adjusted calls."""
        from src.scoring.geo_modifier_worker import _run_geo_modifier

        event_id = uuid4()
        tenant_id = uuid4()
        indicator_id = uuid4()
        company_a = uuid4()

        exposures = [
            ExposureRow(company_id=company_a, exposure_type="geo", direction="positive", magnitude=0.4),
        ]
        indicator = _make_indicator(tenant_id=tenant_id, geo_weight=0.5, indicator_id=indicator_id)
        score_a = _make_score_record(company_id=company_a, indicator_id=indicator_id, tenant_id=tenant_id, score=80.0)

        mock_exposure_repo = AsyncMock()
        mock_exposure_repo.get_by_event.return_value = exposures

        mock_indicator_repo = AsyncMock()
        mock_indicator_repo.list_by_tenant.return_value = [indicator]

        mock_score_repo = AsyncMock()
        mock_score_repo.get_current.return_value = score_a
        mock_score_repo.bulk_update_geo_adjusted.return_value = 1

        mock_broadcaster = AsyncMock()
        mock_company_repo = AsyncMock()
        mock_company_repo.get_tickers_by_ids.return_value = {company_a: "AAPL"}

        await _run_geo_modifier(
            event_id=event_id,
            tenant_id=tenant_id,
            exposure_repo=mock_exposure_repo,
            indicator_repo=mock_indicator_repo,
            score_repo=mock_score_repo,
            company_repo=mock_company_repo,
            broadcaster=mock_broadcaster,
        )

        assert mock_broadcaster.call_count == 1
        broadcast_payload = mock_broadcaster.call_args[0][0]
        assert isinstance(broadcast_payload, GeoModifierPayload)
        assert broadcast_payload.event_id == event_id
        assert len(broadcast_payload.affected_companies) == 1
        assert broadcast_payload.affected_companies[0].ticker == "AAPL"

    @pytest.mark.asyncio
    async def test_neutral_direction_yields_zero_adjustment(self):
        """Neutral direction → direction_sign = 0 → geo_adjusted == base_score."""
        from src.scoring.geo_modifier_worker import _run_geo_modifier

        event_id = uuid4()
        tenant_id = uuid4()
        indicator_id = uuid4()
        company_a = uuid4()

        exposures = [
            ExposureRow(company_id=company_a, exposure_type="geo", direction="neutral", magnitude=0.5),
        ]
        indicator = _make_indicator(tenant_id=tenant_id, geo_weight=0.5, indicator_id=indicator_id)
        score_a = _make_score_record(company_id=company_a, indicator_id=indicator_id, tenant_id=tenant_id, score=80.0, geo_adjusted=80.0)

        mock_exposure_repo = AsyncMock()
        mock_exposure_repo.get_by_event.return_value = exposures

        mock_indicator_repo = AsyncMock()
        mock_indicator_repo.list_by_tenant.return_value = [indicator]

        mock_score_repo = AsyncMock()
        mock_score_repo.get_current.return_value = score_a
        # The epsilon guard should catch this (new == current == 80.0)
        mock_score_repo.bulk_update_geo_adjusted.return_value = 0

        mock_broadcaster = AsyncMock()
        mock_company_repo = AsyncMock()
        mock_company_repo.get_tickers_by_ids.return_value = {}

        result = await _run_geo_modifier(
            event_id=event_id,
            tenant_id=tenant_id,
            exposure_repo=mock_exposure_repo,
            indicator_repo=mock_indicator_repo,
            score_repo=mock_score_repo,
            company_repo=mock_company_repo,
            broadcaster=mock_broadcaster,
        )

        assert result["companies_updated"] == 0

    @pytest.mark.asyncio
    async def test_geo_adjusted_clamped_to_100(self):
        """geo_adjusted is clamped to 100.0 when formula result exceeds 100."""
        from src.scoring.geo_modifier_worker import _run_geo_modifier

        event_id = uuid4()
        tenant_id = uuid4()
        indicator_id = uuid4()
        company_a = uuid4()

        # base=90, geo_weight=1.0, magnitude=0.5, direction=positive
        # formula: 90 * (1 + 1.0 * 0.5 * 1) = 90 * 1.5 = 135 → clamped to 100
        exposures = [
            ExposureRow(company_id=company_a, exposure_type="geo", direction="positive", magnitude=0.5),
        ]
        indicator = _make_indicator(tenant_id=tenant_id, geo_weight=1.0, indicator_id=indicator_id)
        score_a = _make_score_record(company_id=company_a, indicator_id=indicator_id, tenant_id=tenant_id, score=90.0, geo_adjusted=90.0)

        mock_exposure_repo = AsyncMock()
        mock_exposure_repo.get_by_event.return_value = exposures

        mock_indicator_repo = AsyncMock()
        mock_indicator_repo.list_by_tenant.return_value = [indicator]

        mock_score_repo = AsyncMock()
        mock_score_repo.get_current.return_value = score_a
        mock_score_repo.bulk_update_geo_adjusted.return_value = 1

        mock_broadcaster = AsyncMock()
        mock_company_repo = AsyncMock()
        mock_company_repo.get_tickers_by_ids.return_value = {company_a: "TSLA"}

        await _run_geo_modifier(
            event_id=event_id,
            tenant_id=tenant_id,
            exposure_repo=mock_exposure_repo,
            indicator_repo=mock_indicator_repo,
            score_repo=mock_score_repo,
            company_repo=mock_company_repo,
            broadcaster=mock_broadcaster,
        )

        updates = mock_score_repo.bulk_update_geo_adjusted.call_args[0][0]
        assert updates[0].geo_adjusted == 100.0
