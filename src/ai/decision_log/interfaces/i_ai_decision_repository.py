"""IAIDecisionRepository — abstract interface for ai_decision persistence.

PLAN-F-029 TASK-002
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional, Tuple
from uuid import UUID

from src.ai.decision_log.schemas.ai_decision_schemas import (
    AIDecisionCreate,
    AIDecisionDetail,
    AIDecisionRow,
    DecisionLogFilter,
)


class IAIDecisionRepository(ABC):
    """Interface for the ai_decision audit log repository."""

    @abstractmethod
    async def insert(self, decision: AIDecisionCreate) -> AIDecisionRow:
        """Persist a new ai_decision row; returns the created row (truncated view)."""
        ...

    @abstractmethod
    async def get_by_id(self, decision_id: UUID) -> Optional[AIDecisionDetail]:
        """Return full detail for the given decision_id, or None if not found."""
        ...

    @abstractmethod
    async def list_paginated(
        self, filters: DecisionLogFilter
    ) -> Tuple[list[AIDecisionRow], Optional[str]]:
        """
        Return a page of AIDecisionRow objects matching the given filters.

        Uses keyset pagination with (created_at, decision_id) as the cursor
        tuple encoded as a base64 string.

        Returns:
            (rows, next_cursor) — next_cursor is None when no more pages exist.
        """
        ...
