"""
CalibrationReviewRepository — SQLAlchemy 2.0 async implementation of
ICalibrationReviewRepository.

Persists weekly admin calibration review records.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.evaluation.interfaces.i_calibration_review_repository import (
    ICalibrationReviewRepository,
)
from src.ai.evaluation.models.calibration_review_models import (
    CalibrationReview as CalibrationReviewORM,
)
from src.ai.evaluation.schemas.calibration_review_schemas import (
    CalibrationReview,
    CalibrationReviewCreate,
)


class CalibrationReviewRepository(ICalibrationReviewRepository):
    """SQLAlchemy 2.0 async repository for calibration_review rows."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def insert_review(self, review: CalibrationReviewCreate) -> CalibrationReview:
        """INSERT a new calibration_review row and return it with review_id populated."""
        orm = CalibrationReviewORM(
            reviewed_by=review.reviewed_by,
            reviewed_at=datetime.now(tz=timezone.utc),
            corr_at_review=review.corr_at_review,
            below_threshold=review.below_threshold,
            action_taken=review.action_taken,
            notes=review.notes,
        )
        self._session.add(orm)
        await self._session.flush()
        await self._session.refresh(orm)
        return CalibrationReview.model_validate(orm)

    async def list_recent(self, limit: int = 10) -> list[CalibrationReview]:
        """Return the most recent calibration reviews ordered by reviewed_at DESC."""
        stmt = (
            select(CalibrationReviewORM)
            .order_by(CalibrationReviewORM.reviewed_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        rows = result.scalars().all()
        return [CalibrationReview.model_validate(r) for r in rows]

    async def get_last_review(self) -> CalibrationReview | None:
        """Return the most recent calibration review, or None if none exist."""
        stmt = (
            select(CalibrationReviewORM)
            .order_by(CalibrationReviewORM.reviewed_at.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        orm = result.scalars().first()
        if orm is None:
            return None
        return CalibrationReview.model_validate(orm)
