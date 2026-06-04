"""
Unit tests for TASK-010: Tier3CalibrationService and calibration Celery task.

TDD: written before the implementations exist.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.ai.evaluation.schemas.calibration_schemas import (
    CalibrationPassResult,
    CalibrationResult,
    CalibrationResultCreate,
)
from src.ai.memory.schemas.episodic_schemas import RecommendationOutcome


# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_outcome(
    action_signal: str = "BUY",
    confidence: float = 0.8,
    actual_t1d: float = 0.02,
    direction_correct: bool = True,
) -> RecommendationOutcome:
    return RecommendationOutcome(
        rec_id=uuid.uuid4(),
        workflow_id=uuid.uuid4(),
        action_signal=action_signal,
        confidence=confidence,
        actual_t1d=actual_t1d,
        direction_correct=direction_correct,
        filled_at=datetime.now(tz=timezone.utc),
        created_at=datetime.now(tz=timezone.utc),
    )


# ── run_calibration ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tier3_run_calibration_skips_signal_with_fewer_than_5_rows():
    """Signals with <5 outcomes should be skipped (debug-logged, not inserted)."""
    from src.ai.evaluation.services.tier3_calibration_service import (
        Tier3CalibrationService,
    )

    mock_cal_repo = AsyncMock()
    mock_cal_repo.insert_result = AsyncMock()
    mock_cal_repo.get_rolling_corr = AsyncMock(return_value=None)

    mock_episodic_repo = AsyncMock()
    # Only 3 BUY outcomes — below threshold
    outcomes = [_make_outcome("BUY") for _ in range(3)]
    mock_episodic_repo.list_outcomes_by_date = AsyncMock(return_value=outcomes)

    service = Tier3CalibrationService(
        calibration_repo=mock_cal_repo,
        episodic_repo=mock_episodic_repo,
    )

    result = await service.run_calibration(reference_date=date(2026, 6, 1))

    # Nothing inserted because signal has <5 rows
    mock_cal_repo.insert_result.assert_not_called()
    assert result.rows_processed == 3


@pytest.mark.asyncio
async def test_tier3_run_calibration_processes_signal_with_5_or_more_rows():
    """Signals with >=5 outcomes should be computed and upserted."""
    from src.ai.evaluation.services.tier3_calibration_service import (
        Tier3CalibrationService,
    )

    mock_cal_repo = AsyncMock()
    cal_result = CalibrationResult(
        result_id=uuid.uuid4(),
        date=date(2026, 6, 1),
        action_signal="BUY",
        total_recommendations=5,
        direction_correct_pct=0.8,
        mean_confidence=0.75,
        computed_at=datetime.now(tz=timezone.utc),
    )
    mock_cal_repo.insert_result = AsyncMock(return_value=cal_result)
    mock_cal_repo.get_rolling_corr = AsyncMock(return_value=0.45)

    mock_episodic_repo = AsyncMock()
    outcomes = [_make_outcome("BUY", confidence=0.8, actual_t1d=0.02) for _ in range(5)]
    mock_episodic_repo.list_outcomes_by_date = AsyncMock(return_value=outcomes)

    service = Tier3CalibrationService(
        calibration_repo=mock_cal_repo,
        episodic_repo=mock_episodic_repo,
    )

    result = await service.run_calibration(reference_date=date(2026, 6, 1))

    mock_cal_repo.insert_result.assert_called_once()
    assert result.rows_processed == 5


@pytest.mark.asyncio
async def test_tier3_below_threshold_when_corr_low_and_sample_ge_30():
    """below_threshold=True when rolling_corr < 0.3 and total >= 30."""
    from src.ai.evaluation.services.tier3_calibration_service import (
        Tier3CalibrationService,
    )

    mock_cal_repo = AsyncMock()
    cal_result = CalibrationResult(
        result_id=uuid.uuid4(),
        date=date(2026, 6, 1),
        action_signal="BUY",
        total_recommendations=30,
        direction_correct_pct=0.5,
        mean_confidence=0.6,
        computed_at=datetime.now(tz=timezone.utc),
    )
    mock_cal_repo.insert_result = AsyncMock(return_value=cal_result)
    mock_cal_repo.get_rolling_corr = AsyncMock(return_value=0.15)  # below 0.3

    mock_episodic_repo = AsyncMock()
    outcomes = [
        _make_outcome("BUY", confidence=0.7, actual_t1d=0.01) for _ in range(30)
    ]
    mock_episodic_repo.list_outcomes_by_date = AsyncMock(return_value=outcomes)

    service = Tier3CalibrationService(
        calibration_repo=mock_cal_repo,
        episodic_repo=mock_episodic_repo,
    )

    result = await service.run_calibration(reference_date=date(2026, 6, 1))

    assert result.below_threshold is True


@pytest.mark.asyncio
async def test_tier3_below_threshold_none_when_sample_below_30():
    """below_threshold=None when total < 30 (insufficient data)."""
    from src.ai.evaluation.services.tier3_calibration_service import (
        Tier3CalibrationService,
    )

    mock_cal_repo = AsyncMock()
    cal_result = CalibrationResult(
        result_id=uuid.uuid4(),
        date=date(2026, 6, 1),
        action_signal="BUY",
        total_recommendations=10,
        direction_correct_pct=0.7,
        mean_confidence=0.75,
        computed_at=datetime.now(tz=timezone.utc),
    )
    mock_cal_repo.insert_result = AsyncMock(return_value=cal_result)
    mock_cal_repo.get_rolling_corr = AsyncMock(return_value=0.15)

    mock_episodic_repo = AsyncMock()
    # 10 outcomes (< 30 rolling threshold)
    outcomes = [
        _make_outcome("BUY", confidence=0.7, actual_t1d=0.01) for _ in range(10)
    ]
    mock_episodic_repo.list_outcomes_by_date = AsyncMock(return_value=outcomes)

    service = Tier3CalibrationService(
        calibration_repo=mock_cal_repo,
        episodic_repo=mock_episodic_repo,
    )

    result = await service.run_calibration(reference_date=date(2026, 6, 1))

    # 10 total recommendations across all runs in the last 30 days
    # below_threshold is None because we need total >= 30
    assert result.below_threshold is None


@pytest.mark.asyncio
async def test_tier3_corr_none_when_fewer_than_2_samples():
    """corr_confidence_actual should be None when fewer than 2 samples."""
    from src.ai.evaluation.services.tier3_calibration_service import (
        Tier3CalibrationService,
    )

    mock_cal_repo = AsyncMock()
    # Capture what gets inserted
    inserted: list[Any] = []
    async def _capture_insert(result):
        inserted.append(result)
        return CalibrationResult(
            result_id=uuid.uuid4(),
            date=result.date,
            action_signal=result.action_signal,
            total_recommendations=result.total_recommendations,
            direction_correct_pct=result.direction_correct_pct,
            mean_confidence=result.mean_confidence,
            computed_at=datetime.now(tz=timezone.utc),
        )
    mock_cal_repo.insert_result = _capture_insert
    mock_cal_repo.get_rolling_corr = AsyncMock(return_value=None)

    mock_episodic_repo = AsyncMock()
    # 5 outcomes — all with identical confidence AND actual_t1d → zero variance → corr undefined
    outcomes = [
        _make_outcome("SELL", confidence=0.5, actual_t1d=0.5) for _ in range(5)
    ]

    mock_episodic_repo.list_outcomes_by_date = AsyncMock(return_value=outcomes)

    service = Tier3CalibrationService(
        calibration_repo=mock_cal_repo,
        episodic_repo=mock_episodic_repo,
    )

    await service.run_calibration(reference_date=date(2026, 6, 1))

    # corr_confidence_actual should be None (zero variance)
    assert len(inserted) == 1
    assert inserted[0].corr_confidence_actual is None


# ── Celery task ───────────────────────────────────────────────────────────────


def test_calibration_task_is_registered():
    """calibration_tasks module should expose run_daily_calibration Celery task."""
    from src.ai.evaluation.tasks import calibration_tasks

    assert hasattr(calibration_tasks, "run_daily_calibration")
