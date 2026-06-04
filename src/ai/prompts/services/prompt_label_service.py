"""src.ai.prompts.services.prompt_label_service — re-export from label_service.

PLAN-F-014 TASK-004 (AC-002, AC-003).

The implementation lives in src.ai.prompts.label_service (flat module) to preserve
backward compatibility with existing imports. This module re-exports PromptLabelService
from the new services/ namespace as specified in the plan component design.
"""
from src.ai.prompts.label_service import PromptLabel, PromptLabelService, RollbackResult

__all__ = ["PromptLabel", "PromptLabelService", "RollbackResult"]
