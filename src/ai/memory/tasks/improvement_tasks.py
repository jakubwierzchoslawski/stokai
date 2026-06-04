"""
Celery task for the weekly improvement loop.

Beat schedule: Wednesday 04:00 UTC (registered in src/config/celery_app.py).
"""
from __future__ import annotations

import asyncio
import logging

from src.config.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name="src.ai.memory.tasks.improvement_tasks.run_improvement_loop", bind=True
)
def run_improvement_loop(self):
    """
    Weekly Celery task: aggregate user feedback and generate pending proposals.
    """
    async def _run():
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
        from sqlalchemy.orm import sessionmaker
        from src.config.settings import get_settings
        from src.ai.memory.repositories.feedback_repository import FeedbackRepository
        from src.ai.memory.repositories.improvement_repository import ImprovementRepository
        from src.ai.memory.services.improvement_loop_service import ImprovementLoopService

        settings = get_settings()
        engine = create_async_engine(settings.DATABASE_URL, echo=False)
        async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async with async_session() as session:
            feedback_repo = FeedbackRepository(session)
            improvement_repo = ImprovementRepository(session)
            service = ImprovementLoopService(
                feedback_repo=feedback_repo,
                improvement_repo=improvement_repo,
            )
            result = await service.run_improvement_loop()
            await session.commit()

        await engine.dispose()
        logger.info(
            "Improvement loop complete: proposals_created=%d at=%s",
            result.proposals_created,
            result.run_at.isoformat(),
        )
        return {"proposals_created": result.proposals_created}

    return asyncio.get_event_loop().run_until_complete(_run())
