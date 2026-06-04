"""src.ai.prompts.interfaces — abstract interfaces for the prompt management pipeline."""
from src.ai.prompts.interfaces.i_prompt_label_service import IPromptLabelService
from src.ai.prompts.interfaces.i_prompt_loader import IPromptLoader

__all__ = ["IPromptLabelService", "IPromptLoader"]
