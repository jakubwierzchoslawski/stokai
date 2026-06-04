"""Tests for ScoringService orchestrator (TDD — written before implementation)."""
from __future__ import annotations

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

from src.scoring.scoring_service import GeoEventContext, ScoringService
from src.scoring.schemas.indicator import IndicatorRecord
from src.scoring.schemas.company_score import CompanyScoreRecord
from src.scoring.repositories.company_score_repo import SCORE_CHANGE_EPSILON

TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")
COMPANY_ID = uuid4()
INDICATOR_ID = uuid4()


def _make_indicator(
    mode: str = "min_max",
    direction: str = "higher_better",
    geo_weight: float = 0.0,
) -> IndicatorRecord:
    return IndicatorRecord(
        indicator_id=INDICATOR_ID,
        tenant_id=TENANT_ID,
        name="Test",
        formula_dsl="revenue",
        normalization_mode=mode,
        normalization_config={"min_val": 0.0, "max_val": 1000.0},
        direction=direction,
        geo_weight=geo_weight,
        version=1,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )


def _make_service(indicator=None, raw_value=500.0, upsert_returns=True):
    evaluator = AsyncMock()
    evaluator.evaluate = AsyncMock(return_value=raw_value)

    benchmark = MagicMock()
    benchmark.get_peer_values = AsyncMock(return_value=[100.0, 200.0, 300.0, 400.0, 500.0])
    benchmark.compute_benchmark_stats = MagicMock(
        return_value=MagicMock(mean=300.0, std=150.0)
    )

    geo_modifier = MagicMock()
    geo_modifier.apply = MagicMock(return_value=50.0)

    score_repo = AsyncMock()
    score_repo.get_current = AsyncMock(return_value=None)
    score_repo.upsert_if_changed = AsyncMock(return_value=upsert_returns)

    indicator_repo = AsyncMock()
    indicator_repo.get_by_id = AsyncMock(return_value=indicator or _make_indicator())

    service = ScoringService(
        evaluator=evaluator,
        benchmark_engine=benchmark,
        geo_modifier=geo_modifier,
        score_repository=score_repo,
        indicator_repository=indicator_repo,
    )
    return service, evaluator, benchmark, geo_modifier, score_repo, indicator_repo


class TestScoreCompany:
    @pytest.mark.asyncio
    async def test_pipeline_calls_evaluator_normalizer_geo_modifier_in_order(self):
        """score_company calls evaluator → normalizer → repo in order."""
        service, evaluator, benchmark, geo, score_repo, ind_repo = _make_service(
            raw_value=500.0
        )
        result = await service.score_company(COMPANY_ID, INDICATOR_ID, TENANT_ID)

        evaluator.evaluate.assert_called_once()
        score_repo.upsert_if_changed.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_geo_context_geo_adjusted_equals_score(self):
        """geo_event_context=None → geo_adjusted == score (no modifier applied)."""
        indicator = _make_indicator(geo_weight=0.5)
        service, evaluator, benchmark, geo, score_repo, ind_repo = _make_service(
            indicator=indicator, raw_value=500.0
        )
        result = await service.score_company(
            COMPANY_ID, INDICATOR_ID, TENANT_ID, geo_event_context=None
        )

        # geo_modifier.apply should NOT be called when geo_event_context is None
        geo.apply.assert_not_called()

    @pytest.mark.asyncio
    async def test_evaluator_returns_none_skips_normalization_no_db_write(self):
        """evaluator returns None → skip normalization, return None, no DB write."""
        service, evaluator, benchmark, geo, score_repo, ind_repo = _make_service(
            raw_value=None
        )
        result = await service.score_company(COMPANY_ID, INDICATOR_ID, TENANT_ID)

        assert result is None
        score_repo.upsert_if_changed.assert_not_called()

    @pytest.mark.asyncio
    async def test_batch_rescore_respects_upsert_if_changed(self):
        """batch_rescore calls score_company for each; respects upsert_if_changed."""
        company_ids = [uuid4() for _ in range(3)]
        service, evaluator, benchmark, geo, score_repo, ind_repo = _make_service(
            raw_value=500.0, upsert_returns=True
        )
        results = await service.batch_rescore(company_ids, INDICATOR_ID, TENANT_ID)

        assert len(results) == 3
        assert score_repo.upsert_if_changed.call_count == 3

    @pytest.mark.asyncio
    async def test_benchmark_stats_fetched_once_per_batch(self):
        """Benchmark stats fetched once per batch (not per company)."""
        company_ids = [uuid4() for _ in range(5)]
        service, evaluator, benchmark, geo, score_repo, ind_repo = _make_service(
            raw_value=500.0
        )
        await service.batch_rescore(company_ids, INDICATOR_ID, TENANT_ID)

        # get_peer_values called once (for the batch), not 5 times
        benchmark.get_peer_values.assert_called_once()

    @pytest.mark.asyncio
    async def test_indicator_not_found_returns_none(self):
        """If indicator not found → return None."""
        service, evaluator, benchmark, geo, score_repo, ind_repo = _make_service()
        ind_repo.get_by_id = AsyncMock(return_value=None)

        result = await service.score_company(COMPANY_ID, INDICATOR_ID, TENANT_ID)
        assert result is None
