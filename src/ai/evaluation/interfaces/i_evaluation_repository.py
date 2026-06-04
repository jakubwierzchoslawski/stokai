"""
IEvaluationRepository — abstract interface for evaluation_result persistence.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from src.ai.evaluation.schemas.evaluation_schemas import (
    EvaluationResult,
    EvaluationResultCreate,
)


class IEvaluationRepository(ABC):
    """Abstract repository for Tier-1 evaluation results."""

    @abstractmethod
    async def insert_result(self, result: EvaluationResultCreate) -> EvaluationResult:
        """Insert a new evaluation result and return the created entity."""
        ...

    @abstractmethod
    async def get_results_for_run(self, run_id: UUID) -> list[EvaluationResult]:
        """Return all evaluation results for a workflow run, ordered by evaluated_at DESC."""
        ...

    @abstractmethod
    async def list_recent(self, limit: int = 100) -> list[EvaluationResult]:
        """Return the most recent evaluation results, bounded by limit."""
        ...
