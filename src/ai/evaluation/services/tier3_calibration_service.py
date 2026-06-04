"""
Tier3CalibrationService — ITier3Calibration implementation.

Daily calibration run that compares model confidence to actual outcomes.

Algorithm (per run_calibration(reference_date)):
  1. Query recommendation_outcome via IEpisodicRepository where
     created_at::date = reference_date and filled_at IS NOT NULL.
  2. Group by action_signal.
  3. Skip groups with < 5 rows (debug log).
  4. Per group compute:
     - direction_correct_pct = mean(direction_correct)
     - mean_confidence = mean(confidence)
     - mean_actual_t1d = mean(actual_t1d) if any not None
     - corr_confidence_actual = statistics.correlation(confidence, actual_t1d)
       Guard: None if < 2 samples OR zero variance in either series.
  5. Upsert calibration_result per signal.
  6. Compute rolling_corr = get_rolling_corr(days=30).
  7. below_threshold = rolling_corr < 0.3 when total_recommendations >= 30, else None.
  8. Return CalibrationPassResult.

Also provides get_calibration_summary(days=30) for TASK-011.
"""
from __future__ import annotations

import logging
import statistics
from datetime import date
from typing import Optional

from src.ai.evaluation.interfaces.i_calibration_repository import (
    ICalibrationRepository,
)
from src.ai.evaluation.interfaces.i_tier3_calibration import ITier3Calibration
from src.ai.evaluation.schemas.calibration_schemas import (
    CalibrationPassResult,
    CalibrationResult,
    CalibrationResultCreate,
    CalibrationSummary,
)
from src.ai.memory.interfaces.i_episodic_repository import IEpisodicRepository
from src.ai.memory.schemas.episodic_schemas import RecommendationOutcome
from src.config.settings import get_settings

logger = logging.getLogger(__name__)

_MIN_SIGNAL_ROWS = 5


class Tier3CalibrationService(ITier3Calibration):
    """
    Runs daily Tier-3 calibration checks.

    Parameters
    ----------
    calibration_repo:
        ICalibrationRepository — persists calibration_result rows (upsert).
    episodic_repo:
        IEpisodicRepository — source of recommendation_outcome rows.
    """

    def __init__(
        self,
        calibration_repo: ICalibrationRepository,
        episodic_repo: IEpisodicRepository,
    ) -> None:
        self._cal_repo = calibration_repo
        self._episodic_repo = episodic_repo

    async def run_calibration(self, reference_date: date) -> CalibrationPassResult:
        """
        Run calibration for the given reference_date.

        Returns CalibrationPassResult with per_signal metrics.
        """
        settings = get_settings()
        _rolling_threshold = settings.CALIBRATION_CORR_THRESHOLD
        _min_sample = settings.CALIBRATION_MIN_SAMPLE

        # Load filled outcomes for the reference date
        outcomes = await self._episodic_repo.list_outcomes_by_date(reference_date)
        rows_processed = len(outcomes)

        logger.debug(
            "Tier3CalibrationService: %d outcomes for date=%s",
            rows_processed,
            reference_date,
        )

        # Group by action_signal
        by_signal: dict[str, list[RecommendationOutcome]] = {}
        for outcome in outcomes:
            sig = outcome.action_signal or "UNKNOWN"
            by_signal.setdefault(sig, []).append(outcome)

        per_signal: dict[str, CalibrationResult] = {}

        for signal, signal_outcomes in by_signal.items():
            if len(signal_outcomes) < _MIN_SIGNAL_ROWS:
                logger.debug(
                    "Tier3CalibrationService: skipping signal=%r (%d rows < %d)",
                    signal,
                    len(signal_outcomes),
                    _MIN_SIGNAL_ROWS,
                )
                continue

            # direction_correct_pct
            direction_flags = [
                1.0 if o.direction_correct else 0.0
                for o in signal_outcomes
                if o.direction_correct is not None
            ]
            direction_correct_pct = (
                statistics.mean(direction_flags) if direction_flags else 0.0
            )

            # mean_confidence
            confidences = [
                o.confidence
                for o in signal_outcomes
                if o.confidence is not None
            ]
            mean_confidence = statistics.mean(confidences) if confidences else 0.0

            # mean_actual_t1d
            actuals = [
                o.actual_t1d
                for o in signal_outcomes
                if o.actual_t1d is not None
            ]
            mean_actual_t1d: Optional[float] = (
                statistics.mean(actuals) if actuals else None
            )

            # corr_confidence_actual — guard < 2 samples or zero variance
            corr_confidence_actual: Optional[float] = None
            paired = [
                (o.confidence, o.actual_t1d)
                for o in signal_outcomes
                if o.confidence is not None and o.actual_t1d is not None
            ]
            if len(paired) >= 2:
                xs = [p[0] for p in paired]
                ys = [p[1] for p in paired]
                try:
                    corr_confidence_actual = statistics.correlation(xs, ys)
                except statistics.StatisticsError:
                    # Zero variance in one or both series
                    corr_confidence_actual = None

            create = CalibrationResultCreate(
                date=reference_date,
                action_signal=signal,
                total_recommendations=len(signal_outcomes),
                direction_correct_pct=direction_correct_pct,
                corr_confidence_actual=corr_confidence_actual,
                mean_confidence=mean_confidence,
                mean_actual_t1d=mean_actual_t1d,
            )
            result = await self._cal_repo.insert_result(create)
            per_signal[signal] = result

        # Rolling correlation
        rolling_corr = await self._cal_repo.get_rolling_corr(days=30)
        corr_overall = rolling_corr

        # below_threshold
        total_recs = sum(r.total_recommendations for r in per_signal.values())
        below_threshold: Optional[bool]
        if total_recs >= _min_sample and rolling_corr is not None:
            below_threshold = rolling_corr < _rolling_threshold
        else:
            below_threshold = None

        return CalibrationPassResult(
            date=reference_date,
            rows_processed=rows_processed,
            corr_overall=corr_overall,
            per_signal=per_signal,
            below_threshold=below_threshold,
            threshold_used=_rolling_threshold,
            min_sample_used=_min_sample,
        )

    async def get_calibration_summary(self, days: int = 30) -> CalibrationSummary:
        """
        Return aggregated calibration summary for the last N days.

        assessment:
          - 'Healthy' when rolling_corr >= CALIBRATION_CORR_THRESHOLD and total >= CALIBRATION_MIN_SAMPLE
          - 'Warning: CORR below threshold — improvement loop recommended'
            when rolling_corr < CALIBRATION_CORR_THRESHOLD and total >= CALIBRATION_MIN_SAMPLE
          - 'Insufficient data' when total < CALIBRATION_MIN_SAMPLE
        """
        settings = get_settings()
        _rolling_threshold = settings.CALIBRATION_CORR_THRESHOLD
        _min_sample = settings.CALIBRATION_MIN_SAMPLE

        results = await self._cal_repo.list_last_n_days(days=days)
        rolling_corr = await self._cal_repo.get_rolling_corr(days=days)

        total = sum(r.total_recommendations for r in results)

        per_signal: dict[str, float] = {}
        for r in results:
            sig = r.action_signal
            if sig not in per_signal:
                per_signal[sig] = r.direction_correct_pct
            else:
                per_signal[sig] = (per_signal[sig] + r.direction_correct_pct) / 2.0

        below_threshold = False
        if total >= _min_sample and rolling_corr is not None:
            below_threshold = rolling_corr < _rolling_threshold

        if total < _min_sample:
            assessment = "Insufficient data"
        elif below_threshold:
            assessment = "Warning: CORR below threshold — improvement loop recommended"
        else:
            assessment = "Healthy"

        return CalibrationSummary(
            days=days,
            total_recommendations=total,
            per_signal_accuracy=per_signal,
            rolling_corr=rolling_corr,
            below_threshold=below_threshold,
            assessment=assessment,
        )
