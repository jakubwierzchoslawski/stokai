"""
CalibrationRepository — SQLAlchemy 2.0 async implementation of ICalibrationRepository.

The insert_result method uses INSERT ... ON CONFLICT (date, action_signal) DO UPDATE
to upsert calibration results.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.evaluation.interfaces.i_calibration_repository import (
    ICalibrationRepository,
)
from src.ai.evaluation.models.calibration_models import (
    CalibrationResult as CalibrationResultORM,
)
from src.ai.evaluation.schemas.calibration_schemas import (
    CalibrationResult,
    CalibrationResultCreate,
)


class CalibrationRepository(ICalibrationRepository):
    """SQLAlchemy 2.0 async repository for calibration_result rows."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def insert_result(
        self, result: CalibrationResultCreate
    ) -> CalibrationResult:
        """Upsert a calibration_result row using ON CONFLICT (date, action_signal) DO UPDATE."""
        stmt = (
            pg_insert(CalibrationResultORM)
            .values(
                date=result.date,
                action_signal=result.action_signal,
                total_recommendations=result.total_recommendations,
                direction_correct_pct=result.direction_correct_pct,
                corr_confidence_actual=result.corr_confidence_actual,
                mean_confidence=result.mean_confidence,
                mean_actual_t1d=result.mean_actual_t1d,
                computed_at=datetime.now(tz=timezone.utc),
            )
            .on_conflict_do_update(
                constraint="uq_calibration_result_date_signal",
                set_={
                    "total_recommendations": result.total_recommendations,
                    "direction_correct_pct": result.direction_correct_pct,
                    "corr_confidence_actual": result.corr_confidence_actual,
                    "mean_confidence": result.mean_confidence,
                    "mean_actual_t1d": result.mean_actual_t1d,
                    "computed_at": datetime.now(tz=timezone.utc),
                },
            )
        )
        await self._session.execute(stmt)
        await self._session.flush()

        # Fetch the upserted row
        fetch = select(CalibrationResultORM).where(
            CalibrationResultORM.date == result.date,
            CalibrationResultORM.action_signal == result.action_signal,
        )
        fetch_result = await self._session.execute(fetch)
        orm = fetch_result.scalars().first()
        return CalibrationResult.model_validate(orm)

    async def list_last_n_days(
        self, days: int, action_signal: Optional[str] = None
    ) -> list[CalibrationResult]:
        """Return calibration results for the last N days."""
        stmt = select(CalibrationResultORM).where(
            CalibrationResultORM.date
            >= func.current_date() - text(f"interval '{days} days'")
        )
        if action_signal is not None:
            stmt = stmt.where(
                CalibrationResultORM.action_signal == action_signal
            )
        result = await self._session.execute(stmt)
        rows = result.scalars().all()
        return [CalibrationResult.model_validate(r) for r in rows]

    async def get_rolling_corr(self, days: int = 30) -> Optional[float]:
        """Return the rolling average of corr_confidence_actual over the last N days."""
        stmt = (
            select(func.avg(CalibrationResultORM.corr_confidence_actual))
            .where(
                CalibrationResultORM.date
                >= func.current_date() - text(f"interval '{days} days'"),
                CalibrationResultORM.corr_confidence_actual.isnot(None),
            )
        )
        result = await self._session.execute(stmt)
        val = result.scalar_one_or_none()
        return float(val) if val is not None else None
