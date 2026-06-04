"""
Celery task for weekly procedural pattern mining.

Beat schedule: Tuesday 03:00 UTC (registered in src/config/celery_app.py).
"""
from __future__ import annotations

import asyncio
import logging

from src.config.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="src.ai.memory.tasks.mining_tasks.run_pattern_mining", bind=True)
def run_pattern_mining(self):
    """
    Weekly Celery task: mine procedural patterns from recent agent invocations.
    """
    async def _run():
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
        from sqlalchemy.orm import sessionmaker
        from src.config.settings import get_settings
        from src.ai.memory.repositories.procedural_repository import ProceduralRepository
        from src.ai.memory.services.pattern_mining_service import PatternMiningService

        settings = get_settings()
        engine = create_async_engine(settings.DATABASE_URL, echo=False)
        async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async with async_session() as session:
            repo = ProceduralRepository(session)
            service = PatternMiningService(procedural_repo=repo, session=session)
            result = await service.run_mining_pass()
            await session.commit()

        await engine.dispose()
        logger.info(
            "Pattern mining complete: candidates_created=%d at=%s",
            result.candidates_created,
            result.run_at.isoformat(),
        )
        return {"candidates_created": result.candidates_created}

    return asyncio.get_event_loop().run_until_complete(_run())
