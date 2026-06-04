"""
ISemanticRepository — abstract interface for Layer 2 semantic memory operations.

Evidence gate: a fact must accumulate evidence_count >= 3 in staging before
it can be committed to semantic_fact.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID

from src.ai.memory.schemas.semantic_schemas import (
    SemanticFact,
    SemanticFactStaging,
    SemanticFactStagingCreate,
)


class ISemanticRepository(ABC):
    """Abstract repository for Layer 2 semantic memory."""

    @abstractmethod
    async def stage_fact(self, fact: SemanticFactStagingCreate) -> SemanticFactStaging:
        """Insert a new staging row with evidence_count=1."""
        ...

    @abstractmethod
    async def increment_evidence(
        self, staging_id: UUID, source_invocation_id: UUID
    ) -> SemanticFactStaging:
        """Increment evidence_count by 1 and append source_invocation_id."""
        ...

    @abstractmethod
    async def commit_fact(
        self, staging_id: UUID, embedding: list[float]
    ) -> SemanticFact:
        """
        Move the staging row to semantic_fact when evidence_count >= 3.

        Raises EvidenceGateError if evidence_count < 3.
        Deletes the staging row after successful commit.
        """
        ...

    @abstractmethod
    async def query_facts(
        self,
        embedding: list[float],
        limit: int = 20,
        exclude_decayed: bool = True,
    ) -> list[SemanticFact]:
        """
        Return the nearest semantic facts by cosine similarity.

        When exclude_decayed=True, omits rows where decayed_at IS NOT NULL
        or retracted_at IS NOT NULL.
        """
        ...

    @abstractmethod
    async def mark_decayed(self, fact_ids: list[UUID]) -> int:
        """
        Bulk-set decayed_at=NOW() for the given fact IDs.

        Returns the count of rows actually updated.
        """
        ...

    @abstractmethod
    async def retract_fact(self, fact_id: UUID, retracted_by: UUID) -> None:
        """Set retracted_at=NOW() and retracted_by on a single fact."""
        ...

    @abstractmethod
    async def list_unconfirmed_older_than(self, months: int) -> list[SemanticFact]:
        """
        Return committed facts whose last_confirmed is older than `months` months
        and that have not yet been decayed.
        """
        ...
