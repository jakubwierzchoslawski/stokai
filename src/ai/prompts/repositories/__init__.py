"""src.ai.prompts.repositories — repository interfaces for prompt management.

Note: The concrete PromptPublicationRepository lives in
src.storage.repositories.prompt_publication_repository following project conventions.
This package re-exports the interface and concrete class for consumers who prefer
to import from the ai.prompts namespace.
"""
from src.storage.repositories.prompt_publication_repository import (
    IPromptPublicationRepository,
    PromptPublicationRepository,
)

__all__ = ["IPromptPublicationRepository", "PromptPublicationRepository"]
