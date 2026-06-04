"""
Unit tests for TASK-011: calibration warning flag and dashboard summary.

TDD: written before the implementation exists.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock

import pytest

from src.ai.evaluation.schemas.calibration_schemas import (
    CalibrationResult,
    CalibrationSummary,
)


def _make_cal_result(
    action_signal: str = "BUY",
    total_recommendations: int = 10,
    direction_correct_pct: float = 0.7,
) -> CalibrationResult:
    return CalibrationResult(
        result_id=uuid.uuid4(),
        date=date(2026, 6, 1),
        action_signal=action_signal,
        total_recommendations=total_recommendations,
        direction_correct_pct=direction_correct_pct,
        mean_confidence=0.75,
        computed_at=datetime.now(tz=timezone.utc),
    )


# ── get_calibration_summary ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_summary_healthy_when_corr_above_threshold():
    """assessment should be 'Healthy' when rolling_corr >= 0.3 and total >= 30."""
    from src.ai.evaluation.services.tier3_calibration_service import (
        Tier3CalibrationService,
    )

    mock_cal_repo = AsyncMock()
    # 3 results with 10 recs each = 30 total
    results = [_make_cal_result(total_recommendations=10) for _ in range(3)]
    mock_cal_repo.list_last_n_days = AsyncMock(return_value=results)
    mock_cal_repo.get_rolling_corr = AsyncMock(return_value=0.45)  # above 0.3

    mock_episodic_repo = AsyncMock()
    service = Tier3CalibrationService(
        calibration_repo=mock_cal_repo,
        episodic_repo=mock_episodic_repo,
    )

    summary = await service.get_calibration_summary(days=30)

    assert summary.assessment == "Healthy"
    assert summary.below_threshold is False


@pytest.mark.asyncio
async def test_summary_warning_when_corr_below_threshold():
    """assessment should warn when rolling_corr < 0.3 and total >= 30."""
    from src.ai.evaluation.services.tier3_calibration_service import (
        Tier3CalibrationService,
    )

    mock_cal_repo = AsyncMock()
    results = [_make_cal_result(total_recommendations=10) for _ in range(3)]
    mock_cal_repo.list_last_n_days = AsyncMock(return_value=results)
    mock_cal_repo.get_rolling_corr = AsyncMock(return_value=0.15)  # below 0.3

    mock_episodic_repo = AsyncMock()
    service = Tier3CalibrationService(
        calibration_repo=mock_cal_repo,
        episodic_repo=mock_episodic_repo,
    )

    summary = await service.get_calibration_summary(days=30)

    assert "Warning" in summary.assessment
    assert "CORR below threshold" in summary.assessment
    assert summary.below_threshold is True


@pytest.mark.asyncio
async def test_summary_insufficient_data_when_total_below_30():
    """assessment should be 'Insufficient data' when total_recommendations < 30."""
    from src.ai.evaluation.services.tier3_calibration_service import (
        Tier3CalibrationService,
    )

    mock_cal_repo = AsyncMock()
    results = [_make_cal_result(total_recommendations=5)]  # only 5 total
    mock_cal_repo.list_last_n_days = AsyncMock(return_value=results)
    mock_cal_repo.get_rolling_corr = AsyncMock(return_value=0.1)

    mock_episodic_repo = AsyncMock()
    service = Tier3CalibrationService(
        calibration_repo=mock_cal_repo,
        episodic_repo=mock_episodic_repo,
    )

    summary = await service.get_calibration_summary(days=30)

    assert summary.assessment == "Insufficient data"
    assert summary.below_threshold is False  # not triggered without data


@pytest.mark.asyncio
async def test_summary_below_threshold_false_at_boundary():
    """below_threshold should be False when rolling_corr == 0.3 (exactly at threshold)."""
    from src.ai.evaluation.services.tier3_calibration_service import (
        Tier3CalibrationService,
    )

    mock_cal_repo = AsyncMock()
    results = [_make_cal_result(total_recommendations=10) for _ in range(3)]
    mock_cal_repo.list_last_n_days = AsyncMock(return_value=results)
    mock_cal_repo.get_rolling_corr = AsyncMock(return_value=0.3)  # exactly at boundary

    mock_episodic_repo = AsyncMock()
    service = Tier3CalibrationService(
        calibration_repo=mock_cal_repo,
        episodic_repo=mock_episodic_repo,
    )

    summary = await service.get_calibration_summary(days=30)

    # rolling_corr = 0.3 is NOT below threshold (< 0.3)
    assert summary.below_threshold is False
    assert summary.assessment == "Healthy"
