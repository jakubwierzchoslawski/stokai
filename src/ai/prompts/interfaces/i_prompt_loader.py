"""src.ai.prompts.interfaces.i_prompt_loader — IPromptLoader abstract interface.

PLAN-F-014 TASK-002 (AC-002, AC-004).
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from src.ai.prompts.schemas.prompt_schemas import PromptFile, PromptPublication


class IPromptLoader(ABC):
    """Abstract interface for loading prompt files and publishing them to Langfuse."""

    @abstractmethod
    def load_prompt(self, role_id: str) -> PromptFile:
        """Read prompt file from disk; parse frontmatter; compute git SHA.

        Args:
            role_id: Prompt role identifier (e.g. "relevance_analyst").

        Returns:
            Populated PromptFile Pydantic model.

        Raises:
            PromptNotFoundError: If no file is found for the given role_id.
        """
        ...

    @abstractmethod
    def get_sha(self, role_id: str) -> str:
        """Return the git blob SHA for the file containing this role's prompt.

        Args:
            role_id: Prompt role identifier.

        Returns:
            40-character hex SHA string.

        Raises:
            PromptNotFoundError: If no file is found for the given role_id.
        """
        ...

    @abstractmethod
    async def publish_to_langfuse(self, role_id: str) -> PromptPublication:
        """Push current file content to Langfuse with git SHA as version label.

        Args:
            role_id: Prompt role identifier.

        Returns:
            PromptPublication record for the published prompt.

        Raises:
            PromptNotFoundError: If no file is found for the given role_id.
            LangfusePublishError: If the Langfuse SDK call fails.
        """
        ...

    @abstractmethod
    async def publish_all(self) -> list[PromptPublication]:
        """Publish every prompt file in the prompts/ layout to Langfuse.

        Returns:
            List of PromptPublication records, one per published prompt.
        """
        ...
