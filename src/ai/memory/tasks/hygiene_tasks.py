"""
Celery tasks for semantic memory hygiene and recommendation outcome filling.

Beat schedule entries are registered in src/config/celery_app.py.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from src.config.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="src.ai.memory.tasks.hygiene_tasks.run_semantic_hygiene", bind=True)
def run_semantic_hygiene(self):
    """
    Weekly Celery task: run the semantic fact decay pass.

    Connects to the DB, instantiates SemanticHygieneService, and runs
    run_decay_pass(). Logs the number of decayed facts.
    """
    from src.ai.memory.services.semantic_hygiene_service import SemanticHygieneService

    async def _run():
        # Import here to avoid circular imports at module load time
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
        from sqlalchemy.orm import sessionmaker
        from src.config.settings import get_settings
        from src.ai.memory.repositories.semantic_repository import SemanticRepository

        settings = get_settings()
        engine = create_async_engine(settings.DATABASE_URL, echo=False)
        async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async with async_session() as session:
            repo = SemanticRepository(session)
            service = SemanticHygieneService(semantic_repo=repo)
            result = await service.run_decay_pass()
            await session.commit()

        await engine.dispose()
        logger.info(
            "Semantic hygiene pass complete: decayed=%d at=%s",
            result.facts_decayed,
            result.run_at.isoformat(),
        )
        return {"facts_decayed": result.facts_decayed}

    return asyncio.get_event_loop().run_until_complete(_run())


@celery_app.task(
    name="src.ai.memory.tasks.hygiene_tasks.run_outcome_fill", bind=True
)
def run_outcome_fill(self):
    """
    Celery task: fill actual_t1d and actual_t1w for pending recommendation outcomes.

    Queries recommendation_outcome WHERE actual_t1d IS NULL AND filled_at IS NULL,
    fetches price data (placeholder), and calls fill_outcome_actuals.
    """
    async def _run():
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy import select
        from src.config.settings import get_settings
        from src.ai.memory.models.episodic_models import RecommendationOutcome
        from src.ai.memory.repositories.episodic_repository import EpisodicRepository

        settings = get_settings()
        engine = create_async_engine(settings.DATABASE_URL, echo=False)
        async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        filled_count = 0
        async with async_session() as session:
            repo = EpisodicRepository(session)
            stmt = select(RecommendationOutcome).where(
                RecommendationOutcome.actual_t1d.is_(None),
                RecommendationOutcome.filled_at.is_(None),
            )
            result = await session.execute(stmt)
            pending = result.scalars().all()

            for outcome in pending:
                try:
                    # Placeholder: in production, fetch actual price data here
                    actual_t1d = 0.0
                    actual_t1w = 0.0
                    direction_correct = False

                    await repo.fill_outcome_actuals(
                        rec_id=outcome.rec_id,
                        actual_t1d=actual_t1d,
                        actual_t1w=actual_t1w,
                        direction_correct=direction_correct,
                    )
                    filled_count += 1
                except Exception as exc:
                    logger.warning(
                        "Failed to fill outcome %s: %s", outcome.rec_id, exc
                    )

            await session.commit()

        await engine.dispose()
        logger.info("Outcome fill complete: filled=%d", filled_count)
        return {"filled": filled_count}

    return asyncio.get_event_loop().run_until_complete(_run())
