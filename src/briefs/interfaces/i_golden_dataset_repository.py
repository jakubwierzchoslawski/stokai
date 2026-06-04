"""
briefs.interfaces.i_golden_dataset_repository — IGoldenDatasetRepository.

PLAN-F-026 TASK-002
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from src.briefs.models.brief_models import GoldenDatasetCandidate
from src.briefs.schemas.brief_schemas import GoldenDatasetCandidateCreate


class IGoldenDatasetRepository(ABC):
    """Abstract repository for golden dataset candidates."""

    @abstractmethod
    async def create_candidate(
        self, candidate: GoldenDatasetCandidateCreate
    ) -> GoldenDatasetCandidate:
        """Insert a new golden_dataset_candidate row and return it."""
        ...
