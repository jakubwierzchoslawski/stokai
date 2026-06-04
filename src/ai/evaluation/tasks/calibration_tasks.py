"""
Celery tasks for Tier-3 calibration.

Beat schedule: daily at 02:00 UTC (registered in celery_app.py).
reference_date = yesterday (UTC).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta

from src.config.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name="src.ai.evaluation.tasks.calibration_tasks.run_daily_calibration",
    bind=True,
    max_retries=3,
    default_retry_delay=300,  # 5 minutes
)
def run_daily_calibration(self) -> dict:
    """
    Run Tier-3 calibration for yesterday's recommendation outcomes.

    Scheduled daily at 02:00 UTC via Celery beat.
    reference_date = date.today() - 1 day (UTC).
    """
    reference_date = date.today() - timedelta(days=1)
    logger.info(
        "run_daily_calibration: starting for reference_date=%s", reference_date
    )

    try:
        result = asyncio.get_event_loop().run_until_complete(
            _run_calibration_async(reference_date)
        )
        logger.info(
            "run_daily_calibration: completed date=%s rows=%d",
            reference_date,
            result.get("rows_processed", 0),
        )
        return result
    except Exception as exc:
        logger.error(
            "run_daily_calibration: failed for date=%s: %s",
            reference_date,
            type(exc).__name__,
        )
        raise self.retry(exc=exc)


async def _run_calibration_async(reference_date: date) -> dict:
    """
    Build Tier3CalibrationService from DB session and run calibration.

    In production, the DB session is obtained from the async engine.
    In tests, this function is patched or the service is mocked directly.
    """
    # Import here to avoid circular imports at module load time
    from src.ai.evaluation.services.tier3_calibration_service import (
        Tier3CalibrationService,
    )

    # Lazy-import DB session factory to avoid mandatory DB connection at import
    try:
        from src.config.database import get_async_session_factory
        session_factory = get_async_session_factory()
        async with session_factory() as session:
            from src.ai.evaluation.repositories.calibration_repository import (
                CalibrationRepository,
            )
            from src.ai.memory.repositories.episodic_repository import (
                EpisodicRepository,
            )
            cal_repo = CalibrationRepository(session)
            episodic_repo = EpisodicRepository(session)
            service = Tier3CalibrationService(
                calibration_repo=cal_repo,
                episodic_repo=episodic_repo,
            )
            pass_result = await service.run_calibration(reference_date)
            await session.commit()
    except ImportError:
        logger.warning(
            "_run_calibration_async: DB session factory not available — "
            "returning empty result (test/stub environment)"
        )
        return {"rows_processed": 0, "date": str(reference_date)}

    return {
        "rows_processed": pass_result.rows_processed,
        "date": str(pass_result.date),
        "corr_overall": pass_result.corr_overall,
        "below_threshold": pass_result.below_threshold,
    }
