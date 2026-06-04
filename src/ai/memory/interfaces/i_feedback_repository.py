"""
IFeedbackRepository — abstract interface for Layer 4 user feedback.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID

from src.ai.memory.schemas.feedback_schemas import UserFeedback, UserFeedbackCreate


class IFeedbackRepository(ABC):
    """Abstract repository for Layer 4 user feedback."""

    @abstractmethod
    async def append_feedback(self, feedback: UserFeedbackCreate) -> UserFeedback:
        """INSERT a new user_feedback row (insert-only)."""
        ...

    @abstractmethod
    async def list_since(
        self,
        since: datetime,
        tenant_id: UUID | None = None,
    ) -> list[UserFeedback]:
        """Return feedback submitted after `since`, optionally filtered by tenant."""
        ...

    @abstractmethod
    async def get_feedback_for_report(self, report_id: UUID) -> list[UserFeedback]:
        """Return all feedback rows referencing the given report_id."""
        ...
