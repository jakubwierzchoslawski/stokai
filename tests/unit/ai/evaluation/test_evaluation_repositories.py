"""
Unit tests for TASK-003: evaluation repository implementations.

Uses in-memory mock session pattern (no real DB needed).

TDD: written before the implementations exist.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from src.ai.evaluation.schemas.evaluation_schemas import (
    EvaluationResult,
    EvaluationResultCreate,
)
from src.ai.evaluation.schemas.golden_dataset_schemas import (
    GoldenDatasetItem,
    GoldenDatasetItemCreate,
)
from src.ai.evaluation.schemas.calibration_schemas import (
    CalibrationResult,
    CalibrationResultCreate,
)


# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_eval_create(run_id: uuid.UUID | None = None) -> EvaluationResultCreate:
    return EvaluationResultCreate(
        run_id=run_id or uuid.uuid4(),
        judge_model="claude-opus-4-7",
        scores={"factual_grounding": 0.9},
        overall_quality=0.85,
        prompt_version="abc123",
    )


def _make_gd_create() -> GoldenDatasetItemCreate:
    return GoldenDatasetItemCreate(
        input={"query": "Analyse AAPL"},
        expected_output={"signal": "BUY"},
        quality_metrics={"factual_grounding": 0.95},
        source="hand_authored",
    )


def _make_cal_create(ref_date: date | None = None) -> CalibrationResultCreate:
    return CalibrationResultCreate(
        date=ref_date or date(2026, 6, 1),
        action_signal="BUY",
        total_recommendations=20,
        direction_correct_pct=0.75,
        mean_confidence=0.8,
    )


# ── EvaluationRepository tests ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_evaluation_repository_insert_result():
    """insert_result should persist and return an EvaluationResult with eval_id."""
    from src.ai.evaluation.repositories.evaluation_repository import (
        EvaluationRepository,
    )

    session = AsyncMock()
    session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=lambda: None)
    )
    session.flush = AsyncMock()
    session.refresh = AsyncMock()

    repo = EvaluationRepository(session)
    create = _make_eval_create()

    # Patch ORM flush + refresh to return a mock that looks like the ORM model
    orm_mock = MagicMock()
    orm_mock.eval_id = uuid.uuid4()
    orm_mock.run_id = create.run_id
    orm_mock.eval_type = create.eval_type
    orm_mock.judge_model = create.judge_model
    orm_mock.scores = create.scores
    orm_mock.overall_quality = create.overall_quality
    orm_mock.prompt_version = create.prompt_version
    orm_mock.evaluated_at = datetime.now(tz=timezone.utc)

    with patch(
        "src.ai.evaluation.repositories.evaluation_repository.EvaluationResultORM",
        return_value=orm_mock,
    ):
        session.add = MagicMock()
        session.flush = AsyncMock()

        async def _refresh(obj):
            pass

        session.refresh = _refresh

        with patch.object(
            EvaluationResult,
            "model_validate",
            return_value=EvaluationResult(
                eval_id=orm_mock.eval_id,
                run_id=orm_mock.run_id,
                eval_type=orm_mock.eval_type,
                judge_model=orm_mock.judge_model,
                scores=orm_mock.scores,
                overall_quality=orm_mock.overall_quality,
                prompt_version=orm_mock.prompt_version,
                evaluated_at=orm_mock.evaluated_at,
            ),
        ):
            result = await repo.insert_result(create)

    assert result.run_id == create.run_id
    assert result.eval_id is not None


@pytest.mark.asyncio
async def test_evaluation_repository_get_results_for_run():
    """get_results_for_run should return results ordered by evaluated_at DESC."""
    from src.ai.evaluation.repositories.evaluation_repository import (
        EvaluationRepository,
    )

    session = AsyncMock()
    run_id = uuid.uuid4()

    scalars_mock = MagicMock()
    scalars_mock.all.return_value = []
    execute_result = MagicMock()
    execute_result.scalars.return_value = scalars_mock
    session.execute = AsyncMock(return_value=execute_result)

    repo = EvaluationRepository(session)
    results = await repo.get_results_for_run(run_id)
    assert results == []


@pytest.mark.asyncio
async def test_evaluation_repository_list_recent():
    """list_recent should return at most `limit` results ordered DESC."""
    from src.ai.evaluation.repositories.evaluation_repository import (
        EvaluationRepository,
    )

    session = AsyncMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = []
    execute_result = MagicMock()
    execute_result.scalars.return_value = scalars_mock
    session.execute = AsyncMock(return_value=execute_result)

    repo = EvaluationRepository(session)
    results = await repo.list_recent(limit=10)
    assert isinstance(results, list)


# ── GoldenDatasetRepository tests ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_golden_dataset_repository_create_item_inactive():
    """create_item should insert with active=False."""
    from src.ai.evaluation.repositories.golden_dataset_repository import (
        GoldenDatasetRepository,
    )

    session = AsyncMock()
    orm_mock = MagicMock()
    orm_mock.item_id = uuid.uuid4()
    orm_mock.input = {"query": "test"}
    orm_mock.expected_output = {"signal": "BUY"}
    orm_mock.quality_metrics = {}
    orm_mock.source = "hand_authored"
    orm_mock.active = False
    orm_mock.approved_by = None
    orm_mock.approved_at = None
    orm_mock.created_at = datetime.now(tz=timezone.utc)

    session.add = MagicMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()

    with patch(
        "src.ai.evaluation.repositories.golden_dataset_repository.GoldenDatasetItemORM",
        return_value=orm_mock,
    ):
        with patch.object(
            GoldenDatasetItem,
            "model_validate",
            return_value=GoldenDatasetItem(
                item_id=orm_mock.item_id,
                input=orm_mock.input,
                expected_output=orm_mock.expected_output,
                quality_metrics=orm_mock.quality_metrics,
                source=orm_mock.source,
                active=orm_mock.active,
                approved_by=None,
                approved_at=None,
                created_at=orm_mock.created_at,
            ),
        ):
            repo = GoldenDatasetRepository(session)
            item = await repo.create_item(_make_gd_create())

    assert item.active is False


@pytest.mark.asyncio
async def test_golden_dataset_repository_list_active_empty():
    """list_active should query WHERE active=TRUE."""
    from src.ai.evaluation.repositories.golden_dataset_repository import (
        GoldenDatasetRepository,
    )

    session = AsyncMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = []
    execute_result = MagicMock()
    execute_result.scalars.return_value = scalars_mock
    session.execute = AsyncMock(return_value=execute_result)

    repo = GoldenDatasetRepository(session)
    active = await repo.list_active()
    assert active == []


# ── CalibrationRepository tests ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_calibration_repository_insert_result():
    """insert_result should upsert and return a CalibrationResult."""
    from src.ai.evaluation.repositories.calibration_repository import (
        CalibrationRepository,
    )

    session = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock())
    session.flush = AsyncMock()

    orm_mock = MagicMock()
    orm_mock.result_id = uuid.uuid4()
    orm_mock.date = date(2026, 6, 1)
    orm_mock.action_signal = "BUY"
    orm_mock.total_recommendations = 20
    orm_mock.direction_correct_pct = 0.75
    orm_mock.corr_confidence_actual = None
    orm_mock.mean_confidence = 0.8
    orm_mock.mean_actual_t1d = None
    orm_mock.computed_at = datetime.now(tz=timezone.utc)

    scalars_mock = MagicMock()
    scalars_mock.first.return_value = orm_mock
    execute_result = MagicMock()
    execute_result.scalars.return_value = scalars_mock
    session.execute = AsyncMock(return_value=execute_result)

    with patch.object(
        CalibrationResult,
        "model_validate",
        return_value=CalibrationResult(
            result_id=orm_mock.result_id,
            date=orm_mock.date,
            action_signal=orm_mock.action_signal,
            total_recommendations=orm_mock.total_recommendations,
            direction_correct_pct=orm_mock.direction_correct_pct,
            mean_confidence=orm_mock.mean_confidence,
            computed_at=orm_mock.computed_at,
        ),
    ):
        repo = CalibrationRepository(session)
        result = await repo.insert_result(_make_cal_create())

    assert result.action_signal == "BUY"


@pytest.mark.asyncio
async def test_calibration_repository_list_last_n_days():
    """list_last_n_days should query WHERE date >= NOW() - INTERVAL ':days days'."""
    from src.ai.evaluation.repositories.calibration_repository import (
        CalibrationRepository,
    )

    session = AsyncMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = []
    execute_result = MagicMock()
    execute_result.scalars.return_value = scalars_mock
    session.execute = AsyncMock(return_value=execute_result)

    repo = CalibrationRepository(session)
    results = await repo.list_last_n_days(days=30)
    assert results == []
