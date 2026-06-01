"""Integration tests: end-to-end hash invalidation → recomputation → persistence.

PLAN-F-003 TASK-013.
AC-001: inputs_hash mismatch triggers recomputation; unchanged skipped.
AC-005: ScoreResult contains indicator_version_id, inputs_hash, computed_at.

These tests require a live PostgreSQL test database with the scoring schema.
Run with: pytest tests/integration/scoring/ -m integration -v

Full flow tested:
    1. Seed snapshot → call pipeline → assert ScoreResult persisted.
    2. Call again with SAME snapshot → assert None returned, no new DB row.
    3. Mutate one field → call again → assert new row; old rows still present
       (append-only, P-08).
    4. Verify provenance fields in persisted ScoreResult.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.scoring import ScoreRecord
from src.markets.config import MarketConfig, MarketRegistry
from src.scoring.dsl.evaluator import ConcreteDslEvaluator
from src.scoring.geo_weight import ConcreteGeoWeightCalculator
from src.scoring.hash_engine import ConcreteHashEngine
from src.scoring.interfaces import InputSnapshot, ScoreQuery
from src.scoring.pipeline import ConcreteScoringPipeline
from src.scoring.repository import ConcreteScoreRepository


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def repository(db_session: AsyncSession):
    return ConcreteScoreRepository(session=db_session)


@pytest_asyncio.fixture
def pipeline_factory(db_session: AsyncSession):
    """Factory that builds a full pipeline with real components."""
    def _make(company_market_id: str = "US_EQUITIES"):
        event_tool = MagicMock()
        event_tool.get_active_events.return_value = []

        registry = MarketRegistry()
        registry.register(MarketConfig(
            market_id="US_EQUITIES",
            display_name="US Equities",
            price_provider="stub",
            fundamentals_provider="stub",
            news_provider="stub",
            currency="USD",
            trading_calendar="NYSE",
            enabled=True,
            geo_weight_cap=2.0,
        ))

        geo_calc = ConcreteGeoWeightCalculator(
            event_tool=event_tool,
            market_registry=registry,
            company_market_id=company_market_id,
        )

        repo = ConcreteScoreRepository(session=db_session)

        return ConcreteScoringPipeline(
            hash_engine=ConcreteHashEngine(),
            dsl_evaluator=ConcreteDslEvaluator(),
            geo_weight_calculator=geo_calc,
            score_repository=repo,
            market_registry=registry,
            company_market_id=company_market_id,
        ), repo

    return _make


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
async def test_initial_computation_persists_score_record(
    db_session, test_tenant, pipeline_factory
):
    """1. First call → ScoreResult returned and row present in DB."""
    pipeline, repo = pipeline_factory()
    company_id = uuid.uuid4()
    indicator_id = uuid.uuid4()
    indicator_version_id = uuid.uuid4()
    tenant_id = test_tenant.id

    snapshot = InputSnapshot(
        company_id=company_id,
        indicator_id=indicator_id,
        raw_inputs={"price": 100.0, "pe_ratio": 15.0},
    )

    result = await pipeline.recompute_if_stale(
        snapshot=snapshot,
        indicator_version_id=indicator_version_id,
        dsl_expression="price",
        tenant_id=tenant_id,
    )

    assert result is not None
    assert result.inputs_hash is not None
    assert result.computed_at is not None
    assert result.indicator_version_id == indicator_version_id

    # Verify DB row
    rows_q = await db_session.execute(
        select(ScoreRecord).where(
            ScoreRecord.company_id == company_id,
            ScoreRecord.tenant_id == tenant_id,
        )
    )
    rows = rows_q.scalars().all()
    assert len(rows) == 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_no_recompute_with_same_snapshot(
    db_session, test_tenant, pipeline_factory
):
    """2. Second call with same snapshot → None returned; no new DB row."""
    pipeline, repo = pipeline_factory()
    company_id = uuid.uuid4()
    indicator_id = uuid.uuid4()
    tenant_id = test_tenant.id

    snapshot = InputSnapshot(
        company_id=company_id,
        indicator_id=indicator_id,
        raw_inputs={"price": 100.0},
    )

    # First call
    r1 = await pipeline.recompute_if_stale(
        snapshot=snapshot,
        indicator_version_id=uuid.uuid4(),
        dsl_expression="price",
        tenant_id=tenant_id,
    )
    assert r1 is not None

    # Second call with same snapshot
    r2 = await pipeline.recompute_if_stale(
        snapshot=snapshot,
        indicator_version_id=uuid.uuid4(),
        dsl_expression="price",
        tenant_id=tenant_id,
    )
    assert r2 is None

    # Still only one row in DB
    rows_q = await db_session.execute(
        select(ScoreRecord).where(
            ScoreRecord.company_id == company_id,
            ScoreRecord.tenant_id == tenant_id,
        )
    )
    rows = rows_q.scalars().all()
    assert len(rows) == 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_mutated_input_triggers_new_row_and_preserves_old(
    db_session, test_tenant, pipeline_factory
):
    """3. Mutate field → new row; prior rows still present (append-only)."""
    pipeline, repo = pipeline_factory()
    company_id = uuid.uuid4()
    indicator_id = uuid.uuid4()
    tenant_id = test_tenant.id

    snapshot_v1 = InputSnapshot(
        company_id=company_id,
        indicator_id=indicator_id,
        raw_inputs={"price": 100.0},
    )
    snapshot_v2 = InputSnapshot(
        company_id=company_id,
        indicator_id=indicator_id,
        raw_inputs={"price": 105.0},  # mutated
    )

    r1 = await pipeline.recompute_if_stale(
        snapshot=snapshot_v1,
        indicator_version_id=uuid.uuid4(),
        dsl_expression="price",
        tenant_id=tenant_id,
    )
    assert r1 is not None

    r2 = await pipeline.recompute_if_stale(
        snapshot=snapshot_v2,
        indicator_version_id=uuid.uuid4(),
        dsl_expression="price",
        tenant_id=tenant_id,
    )
    assert r2 is not None
    assert r2.inputs_hash != r1.inputs_hash

    # Two rows in DB (append-only — P-08)
    rows_q = await db_session.execute(
        select(ScoreRecord).where(
            ScoreRecord.company_id == company_id,
            ScoreRecord.tenant_id == tenant_id,
        )
    )
    rows = rows_q.scalars().all()
    assert len(rows) == 2

    hashes = {r.inputs_hash for r in rows}
    assert len(hashes) == 2  # two distinct hashes


@pytest.mark.integration
@pytest.mark.asyncio
async def test_score_result_contains_required_provenance_fields(
    db_session, test_tenant, pipeline_factory
):
    """4. ScoreResult has indicator_version_id, inputs_hash, computed_at (AC-005)."""
    pipeline, repo = pipeline_factory()
    indicator_version_id = uuid.uuid4()
    tenant_id = test_tenant.id

    snapshot = InputSnapshot(
        company_id=uuid.uuid4(),
        indicator_id=uuid.uuid4(),
        raw_inputs={"price": 50.0},
    )

    result = await pipeline.recompute_if_stale(
        snapshot=snapshot,
        indicator_version_id=indicator_version_id,
        dsl_expression="price",
        tenant_id=tenant_id,
    )

    assert result is not None
    assert result.indicator_version_id == indicator_version_id
    assert len(result.inputs_hash) == 64  # SHA-256 hex = 64 chars
    assert result.computed_at is not None
    assert isinstance(result.computed_at, datetime)
