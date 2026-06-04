"""src.ai.prompts.interfaces.i_prompt_label_service — IPromptLabelService abstract interface.

PLAN-F-014 TASK-004 (AC-002, AC-003).
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from src.ai.prompts.schemas.prompt_schemas import PromptLabel
from src.ai.prompts.schemas.rollback_schemas import RollbackResult


class IPromptLabelService(ABC):
    """Abstract interface for managing prompt label assignments in Langfuse."""

    @abstractmethod
    async def apply_label(
        self,
        role_id: str,
        version_sha: str,
        label: PromptLabel,
    ) -> None:
        """Apply a Langfuse label to a specific prompt version.

        Args:
            role_id: Prompt role identifier.
            version_sha: Target version SHA to assign the label to.
            label: PromptLabel enum value.
        """
        ...

    @abstractmethod
    async def get_active_version(self, role_id: str, label: PromptLabel) -> str | None:
        """Return the version SHA currently carrying the given label, or None.

        Args:
            role_id: Prompt role identifier.
            label: PromptLabel enum value.

        Returns:
            40-char hex SHA string, or None if no label is assigned.
        """
        ...

    @abstractmethod
    async def rollback(self, role_id: str, to_version: str) -> RollbackResult:
        """Re-label to_version as 'production'; strip 'production' from any other version.

        Must complete within 60 seconds (REQ-N-009 / AC-003).

        Args:
            role_id: Prompt role identifier.
            to_version: Target version SHA to roll back to.

        Returns:
            RollbackResult with effective_at timestamp and previous_version.
        """
        ...
