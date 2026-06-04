"""
Integration tests for Tier-3 calibration flow.

Tests the full path: Tier3CalibrationService → CalibrationRepository →
CalibrationPassResult.

Uses mocked episodic repository and DB (no real DB or network I/O).
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock

import pytest

from src.ai.evaluation.schemas.calibration_schemas import (
    CalibrationPassResult,
    CalibrationResult,
    CalibrationResultCreate,
)
from src.ai.memory.schemas.episodic_schemas import RecommendationOutcome


def _make_outcome(
    action_signal: str = "BUY",
    confidence: float = 0.8,
    actual_t1d: float = 0.02,
    direction_correct: bool = True,
) -> RecommendationOutcome:
    """Create a filled recommendation outcome for testing."""
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


def _make_cal_result(
    action_signal: str = "BUY",
    total: int = 5,
    corr: float | None = None,
) -> CalibrationResult:
    return CalibrationResult(
        result_id=uuid.uuid4(),
        date=date(2026, 6, 1),
        action_signal=action_signal,
        total_recommendations=total,
        direction_correct_pct=0.7,
        corr_confidence_actual=corr,
        mean_confidence=0.75,
        computed_at=datetime.now(tz=timezone.utc),
    )


# ── full calibration run ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tier3_flow_full_run_computes_metrics():
    """
    Integration: run_calibration with 5 BUY outcomes produces CalibrationPassResult
    with populated per_signal data.
    """
    from src.ai.evaluation.services.tier3_calibration_service import (
        Tier3CalibrationService,
    )

    reference_date = date(2026, 6, 1)
    outcomes = [
        _make_outcome("BUY", confidence=0.7 + i * 0.02, actual_t1d=0.01 + i * 0.005)
        for i in range(5)
    ]

    mock_cal_repo = AsyncMock()
    cal_result = _make_cal_result("BUY", total=5)
    mock_cal_repo.insert_result = AsyncMock(return_value=cal_result)
    mock_cal_repo.get_rolling_corr = AsyncMock(return_value=0.45)

    mock_episodic_repo = AsyncMock()
    mock_episodic_repo.list_outcomes_by_date = AsyncMock(return_value=outcomes)

    service = Tier3CalibrationService(
        calibration_repo=mock_cal_repo,
        episodic_repo=mock_episodic_repo,
    )

    result = await service.run_calibration(reference_date)

    assert result.date == reference_date
    assert result.rows_processed == 5
    assert "BUY" in result.per_signal
    mock_cal_repo.insert_result.assert_called_once()


# ── mixed signals ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tier3_flow_multiple_signals():
    """Integration: BUY and SELL signals each with 5+ rows both get upserted."""
    from src.ai.evaluation.services.tier3_calibration_service import (
        Tier3CalibrationService,
    )

    reference_date = date(2026, 6, 1)
    buy_outcomes = [_make_outcome("BUY") for _ in range(5)]
    sell_outcomes = [_make_outcome("SELL", confidence=0.6, actual_t1d=-0.01) for _ in range(5)]
    all_outcomes = buy_outcomes + sell_outcomes

    mock_cal_repo = AsyncMock()
    mock_cal_repo.insert_result = AsyncMock(
        side_effect=lambda create: _make_cal_result(create.action_signal, create.total_recommendations)
    )
    mock_cal_repo.get_rolling_corr = AsyncMock(return_value=0.35)

    mock_episodic_repo = AsyncMock()
    mock_episodic_repo.list_outcomes_by_date = AsyncMock(return_value=all_outcomes)

    service = Tier3CalibrationService(
        calibration_repo=mock_cal_repo,
        episodic_repo=mock_episodic_repo,
    )

    result = await service.run_calibration(reference_date)

    assert result.rows_processed == 10
    # Both signals should have been processed
    assert mock_cal_repo.insert_result.call_count == 2


# ── calibration summary ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tier3_flow_calibration_summary_healthy():
    """Integration: get_calibration_summary returns Healthy assessment."""
    from src.ai.evaluation.services.tier3_calibration_service import (
        Tier3CalibrationService,
    )

    mock_cal_repo = AsyncMock()
    results = [_make_cal_result("BUY", total=10) for _ in range(3)]
    mock_cal_repo.list_last_n_days = AsyncMock(return_value=results)
    mock_cal_repo.get_rolling_corr = AsyncMock(return_value=0.42)

    mock_episodic_repo = AsyncMock()
    service = Tier3CalibrationService(
        calibration_repo=mock_cal_repo,
        episodic_repo=mock_episodic_repo,
    )

    summary = await service.get_calibration_summary(days=30)

    assert summary.total_recommendations == 30
    assert summary.assessment == "Healthy"
    assert summary.rolling_corr == 0.42


@pytest.mark.asyncio
async def test_tier3_flow_calibration_summary_warning():
    """Integration: get_calibration_summary returns Warning when corr < 0.3."""
    from src.ai.evaluation.services.tier3_calibration_service import (
        Tier3CalibrationService,
    )

    mock_cal_repo = AsyncMock()
    results = [_make_cal_result("BUY", total=15) for _ in range(2)]
    mock_cal_repo.list_last_n_days = AsyncMock(return_value=results)
    mock_cal_repo.get_rolling_corr = AsyncMock(return_value=0.18)

    mock_episodic_repo = AsyncMock()
    service = Tier3CalibrationService(
        calibration_repo=mock_cal_repo,
        episodic_repo=mock_episodic_repo,
    )

    summary = await service.get_calibration_summary(days=30)

    assert "Warning" in summary.assessment
    assert summary.below_threshold is True
