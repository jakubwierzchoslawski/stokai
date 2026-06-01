"""TDD tests for market-scoped scoring (PLAN-F-003 TASK-011).

Tests written before implementation.
AC-003: New MarketConfig entry scores companies with zero code changes to
scoring, alert, AI, or map code.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.markets.config import MarketConfig, MarketRegistry
from src.scoring.interfaces import InputSnapshot


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_market(market_id: str, enabled: bool = True, geo_weight_cap: float = 2.0):
    return MarketConfig(
        market_id=market_id,
        display_name=market_id,
        price_provider="stub",
        fundamentals_provider="stub",
        news_provider="stub",
        currency="USD",
        trading_calendar="NYSE",
        enabled=enabled,
        geo_weight_cap=geo_weight_cap,
    )


def _make_pipeline(market_registry: MarketRegistry, company_market_id: str = "US_EQUITIES",
                   dsl_score: float = 1.0, geo_weight: float = 1.0):
    from src.scoring.pipeline import ConcreteScoringPipeline

    hash_engine = MagicMock()
    hash_engine.compute.return_value = "new_hash"
    hash_engine.has_changed.return_value = True

    repo = AsyncMock()
    repo.get_stored_hash.return_value = "old_hash"
    repo.append.return_value = None

    evaluator = MagicMock()
    evaluator.evaluate.return_value = dsl_score

    geo_calc = MagicMock()
    geo_calc.calculate.return_value = geo_weight

    return ConcreteScoringPipeline(
        hash_engine=hash_engine,
        dsl_evaluator=evaluator,
        geo_weight_calculator=geo_calc,
        score_repository=repo,
        market_registry=market_registry,
        company_market_id=company_market_id,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestMarketScopedScoring:

    @pytest.mark.asyncio
    async def test_scoring_accepts_new_market_config_without_code_change(self):
        """Add MARKET_TEST_CONFIG to the registry; pipeline returns a ScoreResult."""
        registry = MarketRegistry()
        registry.register(_make_market("MARKET_TEST"))

        pipeline = _make_pipeline(market_registry=registry, company_market_id="MARKET_TEST")

        snapshot = InputSnapshot(
            company_id=uuid.uuid4(),
            indicator_id=uuid.uuid4(),
            raw_inputs={"price": 100.0},
        )
        result = await pipeline.recompute_if_stale(
            snapshot=snapshot,
            indicator_version_id=uuid.uuid4(),
            dsl_expression="price",
            tenant_id=uuid.uuid4(),
        )

        assert result is not None

    @pytest.mark.asyncio
    async def test_inactive_market_raises_value_error(self):
        """Market with enabled=False raises ValueError before any computation."""
        registry = MarketRegistry()
        registry.register(_make_market("INACTIVE_MARKET", enabled=False))

        pipeline = _make_pipeline(
            market_registry=registry,
            company_market_id="INACTIVE_MARKET",
        )

        snapshot = InputSnapshot(
            company_id=uuid.uuid4(),
            indicator_id=uuid.uuid4(),
            raw_inputs={"price": 100.0},
        )

        with pytest.raises(ValueError, match="inactive"):
            await pipeline.recompute_if_stale(
                snapshot=snapshot,
                indicator_version_id=uuid.uuid4(),
                dsl_expression="price",
                tenant_id=uuid.uuid4(),
            )

    @pytest.mark.asyncio
    async def test_different_markets_use_their_own_geo_weight_cap(self):
        """Two companies in different markets produce different scores from same events."""
        from src.scoring.pipeline import ConcreteScoringPipeline

        registry_a = MarketRegistry()
        registry_a.register(_make_market("MARKET_A", geo_weight_cap=1.5))

        registry_b = MarketRegistry()
        registry_b.register(_make_market("MARKET_B", geo_weight_cap=3.0))

        # Pipeline A: geo_weight limited to 1.5
        pipeline_a = _make_pipeline(
            market_registry=registry_a,
            company_market_id="MARKET_A",
            dsl_score=1.0,
            geo_weight=1.5,
        )
        # Pipeline B: geo_weight limited to 3.0
        pipeline_b = _make_pipeline(
            market_registry=registry_b,
            company_market_id="MARKET_B",
            dsl_score=1.0,
            geo_weight=3.0,
        )

        snapshot = InputSnapshot(
            company_id=uuid.uuid4(),
            indicator_id=uuid.uuid4(),
            raw_inputs={"price": 100.0},
        )

        result_a = await pipeline_a.recompute_if_stale(
            snapshot=snapshot,
            indicator_version_id=uuid.uuid4(),
            dsl_expression="price",
            tenant_id=uuid.uuid4(),
        )
        result_b = await pipeline_b.recompute_if_stale(
            snapshot=snapshot,
            indicator_version_id=uuid.uuid4(),
            dsl_expression="price",
            tenant_id=uuid.uuid4(),
        )

        assert result_a is not None
        assert result_b is not None
        assert result_a.score != result_b.score
        assert result_a.geo_weight_applied == pytest.approx(1.5)
        assert result_b.geo_weight_applied == pytest.approx(3.0)

    @pytest.mark.asyncio
    async def test_unknown_market_does_not_raise_when_no_registry(self):
        """Pipeline without market_registry accepts any snapshot (backward-compat)."""
        from src.scoring.pipeline import ConcreteScoringPipeline

        hash_engine = MagicMock()
        hash_engine.compute.return_value = "hash"
        hash_engine.has_changed.return_value = True
        repo = AsyncMock()
        repo.get_stored_hash.return_value = None
        repo.append.return_value = None
        evaluator = MagicMock()
        evaluator.evaluate.return_value = 1.0
        geo_calc = MagicMock()
        geo_calc.calculate.return_value = 1.0

        pipeline = ConcreteScoringPipeline(
            hash_engine=hash_engine,
            dsl_evaluator=evaluator,
            geo_weight_calculator=geo_calc,
            score_repository=repo,
            # No market_registry supplied
        )

        snapshot = InputSnapshot(
            company_id=uuid.uuid4(),
            indicator_id=uuid.uuid4(),
            raw_inputs={"price": 50.0},
        )
        result = await pipeline.recompute_if_stale(
            snapshot=snapshot,
            indicator_version_id=uuid.uuid4(),
            dsl_expression="price",
            tenant_id=uuid.uuid4(),
        )
        assert result is not None
