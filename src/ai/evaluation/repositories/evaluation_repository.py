"""
EvaluationRepository — SQLAlchemy 2.0 async implementation of IEvaluationRepository.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.evaluation.interfaces.i_evaluation_repository import IEvaluationRepository
from src.ai.evaluation.models.evaluation_models import (
    EvaluationResult as EvaluationResultORM,
)
from src.ai.evaluation.schemas.evaluation_schemas import (
    EvaluationResult,
    EvaluationResultCreate,
)


class EvaluationRepository(IEvaluationRepository):
    """SQLAlchemy 2.0 async repository for evaluation_result rows."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def insert_result(self, result: EvaluationResultCreate) -> EvaluationResult:
        """INSERT a new evaluation_result row and return the schema object."""
        orm = EvaluationResultORM(
            eval_id=uuid4(),
            run_id=result.run_id,
            eval_type=result.eval_type,
            judge_model=result.judge_model,
            scores=result.scores,
            overall_quality=result.overall_quality,
            prompt_version=result.prompt_version,
            evaluated_at=datetime.now(tz=timezone.utc),
        )
        self._session.add(orm)
        await self._session.flush()
        await self._session.refresh(orm)
        return EvaluationResult.model_validate(orm)

    async def get_results_for_run(self, run_id: UUID) -> list[EvaluationResult]:
        """Return all evaluation results for a run, ordered by evaluated_at DESC."""
        stmt = (
            select(EvaluationResultORM)
            .where(EvaluationResultORM.run_id == run_id)
            .order_by(EvaluationResultORM.evaluated_at.desc())
        )
        result = await self._session.execute(stmt)
        rows = result.scalars().all()
        return [EvaluationResult.model_validate(r) for r in rows]

    async def list_recent(self, limit: int = 100) -> list[EvaluationResult]:
        """Return the most recent evaluation results, bounded by limit."""
        stmt = (
            select(EvaluationResultORM)
            .order_by(EvaluationResultORM.evaluated_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        rows = result.scalars().all()
        return [EvaluationResult.model_validate(r) for r in rows]
