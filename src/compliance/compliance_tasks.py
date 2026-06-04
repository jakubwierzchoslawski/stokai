"""
compliance.compliance_tasks — Celery beat task for hourly episodic coverage checks.

REQ-N-012: Periodic integrity check that detects agent invocation gaps.

The task is read-only and idempotent: running it twice in an hour produces
the same report (the underlying episodic tables are append-only).

Registered in src/config/celery_app.py beat schedule: every hour at minute 0.
"""
from __future__ import annotations

import asyncio
import logging

from celery import shared_task

from src.config.settings import get_settings

logger = logging.getLogger(__name__)


@shared_task(name="src.compliance.compliance_tasks.run_episodic_coverage_check")
def run_episodic_coverage_check() -> dict:
    """
    Celery task: run episodic completeness check and log results.

    Logs:
      - INFO when coverage_pct == 100.0
      - WARNING when coverage_pct < 100.0, including all gap workflow_run_ids

    Returns a dict summary (serialisable for Celery result backend).
    """
    return asyncio.get_event_loop().run_until_complete(_run_check_async())


async def _run_check_async() -> dict:
    """Async core of the compliance check task."""
    from src.compliance.compliance_check_service import (
        ComplianceCheckService,
    )
    from src.compliance.repositories import (
        SqlComplianceRepository,
        SqlRecommendationRepository,
    )

    settings = get_settings()
    lookback_days: int = settings.COMPLIANCE_CHECK_LOOKBACK_DAYS

    # Build lightweight repository instances using a fresh DB session.
    # Import here to avoid circular imports at module load time.
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
        bind=engine, expire_on_commit=False
    )

    async with session_factory() as session:
        compliance_repo = SqlComplianceRepository(session)
        rec_repo = SqlRecommendationRepository(session)
        service = ComplianceCheckService(
            compliance_repo=compliance_repo,
            recommendation_repo=rec_repo,
            disclaimer_threshold=settings.DISCLAIMER_SAMPLE_SIZE_THRESHOLD,
        )
        report = await service.run_coverage_check(lookback_days)

    if report.coverage_pct < 100.0:
        gap_ids = [str(gap.workflow_run_id) for gap in report.gaps]
        logger.warning(
            "Episodic coverage check: %.1f%% — %d gap(s) detected in last %d days. "
            "Gap workflow_run_ids: %s",
            report.coverage_pct,
            report.runs_with_zero_invocations,
            lookback_days,
            gap_ids,
        )
    else:
        logger.info(
            "Episodic coverage check: 100.0%% — all %d completed runs have "
            "agent_invocation rows (lookback=%d days).",
            report.total_completed_runs,
            lookback_days,
        )

    await engine.dispose()

    return {
        "coverage_pct": report.coverage_pct,
        "total_completed_runs": report.total_completed_runs,
        "runs_with_zero_invocations": report.runs_with_zero_invocations,
        "gap_ids": [str(g.workflow_run_id) for g in report.gaps],
    }
