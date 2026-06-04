"""
IProceduralRepository — abstract interface for Layer 3 procedural memory.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from src.ai.memory.schemas.procedural_schemas import ProceduralPattern, ProceduralPatternCreate


class IProceduralRepository(ABC):
    """Abstract repository for Layer 3 procedural patterns."""

    @abstractmethod
    async def get_patterns(
        self,
        context_tags: list[str],
        agent_role: str | None = None,
    ) -> list[ProceduralPattern]:
        """
        Return approved, non-retracted patterns whose context_tags overlap with
        the supplied tags; optionally filtered by agent_role.
        """
        ...

    @abstractmethod
    async def create_pattern(
        self, pattern: ProceduralPatternCreate
    ) -> ProceduralPattern:
        """Insert a new procedural pattern row (approved_at=NULL for mined patterns)."""
        ...

    @abstractmethod
    async def approve_pattern(
        self, pattern_id: UUID, approved_by: UUID
    ) -> ProceduralPattern:
        """Set approved_at=NOW() and approved_by on the pattern."""
        ...

    @abstractmethod
    async def retract_pattern(self, pattern_id: UUID, retracted_by: UUID) -> None:
        """Set retracted_at=NOW() on the pattern."""
        ...

    @abstractmethod
    async def list_pending_approval(self) -> list[ProceduralPattern]:
        """Return patterns that have not yet been approved or retracted."""
        ...
