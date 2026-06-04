"""src.ai.prompts.version_resolver — PromptVersionResolver.

PLAN-F-014 TASK-009.

Resolves the active version SHA for a prompt role:
1. Reads the 'production' label from PromptLabelService.
2. Falls back to GitPromptLoader.get_sha(role_id) if no label is set.

This is the single authoritative source of truth for "what version of a
prompt should be used right now in production".
"""
from __future__ import annotations

import logging
from typing import Any

from src.ai.prompts.label_service import PromptLabel, PromptLabelService
from src.ai.prompts.prompt_loader import GitPromptLoader

logger = logging.getLogger(__name__)


class PromptVersionResolver:
    """Resolves the active version SHA for a prompt role.

    Resolution order:
    1. Check PromptLabelService for 'production' label → return that SHA.
    2. Fall back to GitPromptLoader.get_sha(role_id).

    Args:
        label_service: PromptLabelService for DB-backed label lookups.
        loader: GitPromptLoader for git-based SHA computation.
    """

    def __init__(
        self,
        label_service: PromptLabelService,
        loader: GitPromptLoader,
    ) -> None:
        self._label_service = label_service
        self._loader = loader

    async def resolve_version(self, role_id: str) -> str:
        """Return the active version SHA for role_id.

        Args:
            role_id: Prompt role identifier (e.g. "exposure_analyst").

        Returns:
            40-char hex SHA string.
        """
        # Step 1: Try production label from DB
        production_sha = await self._label_service.get_active_version(
            role_id, PromptLabel.production
        )
        if production_sha is not None:
            logger.debug(
                "resolve_version role_id=%s → production label sha=%s...",
                role_id,
                production_sha[:8],
            )
            return production_sha

        # Step 2: Fall back to git SHA
        git_sha = self._loader.get_sha(role_id)
        logger.debug(
            "resolve_version role_id=%s → git SHA fallback sha=%s...",
            role_id,
            git_sha[:8],
        )
        return git_sha
