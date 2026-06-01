"""TDD unit tests for ConcreteScoringPipeline (PLAN-F-003 TASK-010).

Tests written before implementation (red phase).
AC-001: inputs_hash mismatch triggers recomputation; unchanged hashes skip it.
AC-002: DSL evaluation.
AC-004: geo_weight applied.
AC-005: provenance fields in ScoreResult.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, call

import pytest

from src.scoring.exceptions import DslEvalError
from src.scoring.interfaces import InputSnapshot, ScoreResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_snapshot(raw_inputs: dict | None = None) -> InputSnapshot:
    return InputSnapshot(
        company_id=uuid.uuid4(),
        indicator_id=uuid.uuid4(),
        raw_inputs=raw_inputs or {"price": 100.0},
    )


def _make_pipeline(
    stored_hash: str | None = None,
    dsl_score: float = 1.0,
    geo_weight: float = 1.0,
):
    """Build a pipeline with fully mocked collaborators."""
    from src.scoring.pipeline import ConcreteScoringPipeline

    hash_engine = MagicMock()
    hash_engine.compute.return_value = "fresh_hash"
    hash_engine.has_changed.return_value = (stored_hash != "fresh_hash")

    repo = AsyncMock()
    repo.get_stored_hash.return_value = stored_hash
    repo.append.return_value = None

    evaluator = MagicMock()
    evaluator.evaluate.return_value = dsl_score

    geo_calc = MagicMock()
    geo_calc.calculate.return_value = geo_weight

    pipeline = ConcreteScoringPipeline(
        hash_engine=hash_engine,
        dsl_evaluator=evaluator,
        geo_weight_calculator=geo_calc,
        score_repository=repo,
    )
    return pipeline, hash_engine, repo, evaluator, geo_calc


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestConcreteScoringPipeline:
    """Unit tests for ConcreteScoringPipeline."""

    @pytest.mark.asyncio
    async def test_no_recompute_when_hash_unchanged(self):
        """Hash unchanged → returns None; repo.append never called."""
        pipeline, hash_engine, repo, evaluator, geo_calc = _make_pipeline(
            stored_hash="fresh_hash",  # same as what compute() returns
        )
        # Override has_changed to return False
        hash_engine.has_changed.return_value = False

        snapshot = _make_snapshot()
        result = await pipeline.recompute_if_stale(
            snapshot=snapshot,
            indicator_version_id=uuid.uuid4(),
            dsl_expression="price * 2",
            tenant_id=uuid.uuid4(),
        )

        assert result is None
        repo.append.assert_not_called()

    @pytest.mark.asyncio
    async def test_recomputes_when_hash_changes(self):
        """Hash changed → evaluator and appender each called exactly once."""
        pipeline, hash_engine, repo, evaluator, geo_calc = _make_pipeline(
            stored_hash="old_hash",
            dsl_score=5.0,
            geo_weight=1.5,
        )
        hash_engine.has_changed.return_value = True

        snapshot = _make_snapshot()
        result = await pipeline.recompute_if_stale(
            snapshot=snapshot,
            indicator_version_id=uuid.uuid4(),
            dsl_expression="price",
            tenant_id=uuid.uuid4(),
        )

        assert result is not None
        evaluator.evaluate.assert_called_once()
        repo.append.assert_called_once()

    @pytest.mark.asyncio
    async def test_result_carries_correct_provenance(self):
        """Returned ScoreResult has inputs_hash, indicator_version_id, computed_at, tenant_id."""
        pipeline, hash_engine, repo, evaluator, geo_calc = _make_pipeline(
            stored_hash=None,  # first-time → always recompute
        )
        hash_engine.has_changed.return_value = True

        indicator_version_id = uuid.uuid4()
        tenant_id = uuid.uuid4()
        snapshot = _make_snapshot()

        result = await pipeline.recompute_if_stale(
            snapshot=snapshot,
            indicator_version_id=indicator_version_id,
            dsl_expression="price",
            tenant_id=tenant_id,
        )

        assert result is not None
        assert result.inputs_hash == "fresh_hash"
        assert result.indicator_version_id == indicator_version_id
        assert result.computed_at is not None
        assert result.tenant_id == tenant_id

    @pytest.mark.asyncio
    async def test_geo_weight_applied_to_score(self):
        """evaluator returns 1.0, geo_weight=1.5 → result.score=1.5, geo_weight_applied=1.5."""
        pipeline, hash_engine, repo, evaluator, geo_calc = _make_pipeline(
            stored_hash=None,
            dsl_score=1.0,
            geo_weight=1.5,
        )
        hash_engine.has_changed.return_value = True

        result = await pipeline.recompute_if_stale(
            snapshot=_make_snapshot(),
            indicator_version_id=uuid.uuid4(),
            dsl_expression="1",
            tenant_id=uuid.uuid4(),
        )

        assert result is not None
        assert result.score == pytest.approx(1.5)
        assert result.geo_weight_applied == pytest.approx(1.5)

    @pytest.mark.asyncio
    async def test_dsl_eval_error_propagates(self):
        """DslEvalError from evaluator propagates without being caught by pipeline."""
        pipeline, hash_engine, repo, evaluator, geo_calc = _make_pipeline(
            stored_hash=None,
        )
        hash_engine.has_changed.return_value = True
        evaluator.evaluate.side_effect = DslEvalError("bad expression")

        with pytest.raises(DslEvalError):
            await pipeline.recompute_if_stale(
                snapshot=_make_snapshot(),
                indicator_version_id=uuid.uuid4(),
                dsl_expression="bad",
                tenant_id=uuid.uuid4(),
            )

        repo.append.assert_not_called()

    @pytest.mark.asyncio
    async def test_score_result_company_id_matches_snapshot(self):
        """ScoreResult.company_id matches the input snapshot company_id."""
        pipeline, hash_engine, repo, evaluator, geo_calc = _make_pipeline(
            stored_hash=None,
            dsl_score=2.0,
            geo_weight=1.0,
        )
        hash_engine.has_changed.return_value = True

        snapshot = _make_snapshot()
        result = await pipeline.recompute_if_stale(
            snapshot=snapshot,
            indicator_version_id=uuid.uuid4(),
            dsl_expression="price",
            tenant_id=uuid.uuid4(),
        )

        assert result is not None
        assert result.company_id == snapshot.company_id
        assert result.indicator_id == snapshot.indicator_id
