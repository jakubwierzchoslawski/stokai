"""src.ai.prompts.models — ORM models for the prompt management pipeline.

Note: The PromptPublication ORM model lives in src.storage.models.prompt_publication
to follow the project's storage-layer conventions. This package re-exports it for
consumers who import from the ai.prompts namespace.
"""
from src.storage.models.prompt_publication import PromptPublication

__all__ = ["PromptPublication"]
