"""src.ai.prompts.label_service — PromptLabelService.

PLAN-F-014 TASK-005.

Manages prompt label assignments (production/staging/canary/experimental).
The rollback path is DB-only so it succeeds even when Langfuse is unavailable.

Contracts:
    apply_label(role_id, version_sha, label) → None
    get_active_version(role_id, label) → str | None
    rollback(role_id, to_version) → RollbackResult
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Protocol

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public data classes and enums
# ---------------------------------------------------------------------------


class PromptLabel(str, Enum):
    production = "production"
    staging = "staging"
    canary = "canary"
    experimental = "experimental"


@dataclass
class RollbackResult:
    role_id: str
    previous_version: str   # SHA before rollback
    rolled_back_to: str     # SHA after rollback
    effective_at: datetime


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


class IPromptLabelService(Protocol):
    async def apply_label(
        self, role_id: str, version_sha: str, label: PromptLabel
    ) -> None: ...

    async def get_active_version(
        self, role_id: str, label: PromptLabel
    ) -> str | None: ...

    async def rollback(self, role_id: str, to_version: str) -> RollbackResult: ...


# ---------------------------------------------------------------------------
# Implementation
# ---------------------------------------------------------------------------


class PromptLabelService:
    """Applies and queries prompt label assignments via the DB repository.

    The rollback operation moves the 'production' label to the specified
    version_sha using a single upsert. Langfuse is NOT involved in rollback
    to ensure the SLA is met even when Langfuse is unavailable.

    Args:
        repository: IPromptPublicationRepository for DB read/write.
    """

    def __init__(self, repository: Any) -> None:  # IPromptPublicationRepository
        self._repository = repository

    # ------------------------------------------------------------------
    # IPromptLabelService contract
    # ------------------------------------------------------------------

    async def apply_label(
        self, role_id: str, version_sha: str, label: PromptLabel
    ) -> None:
        """Persist a label assignment for the given (role_id, version_sha).

        This is an upsert: if (role_id, label) already exists, it is updated
        to point to version_sha.

        Args:
            role_id: Prompt role identifier.
            version_sha: Target version SHA to assign the label to.
            label: PromptLabel enum value.
        """
        await self._repository.upsert_label(
            role_id=role_id,
            version_sha=version_sha,
            label=label.value,
        )
        logger.info(
            "apply_label role_id=%s label=%s sha=%s...",
            role_id,
            label.value,
            version_sha[:8],
        )

    async def get_active_version(
        self, role_id: str, label: PromptLabel
    ) -> str | None:
        """Return the version SHA currently assigned to (role_id, label).

        Args:
            role_id: Prompt role identifier.
            label: PromptLabel enum value.

        Returns:
            40-char hex SHA string, or None if no label is assigned.
        """
        pub = await self._repository.get_by_label(role_id, label.value)
        if pub is None:
            return None
        return pub.version_sha

    async def rollback(self, role_id: str, to_version: str) -> RollbackResult:
        """Move the 'production' label to to_version (DB-only, Langfuse not required).

        Reads the current production version SHA before overwriting it so the
        result carries meaningful previous_version information.

        Args:
            role_id: Prompt role identifier.
            to_version: Target version SHA to roll back to.

        Returns:
            RollbackResult with previous_version, rolled_back_to, and effective_at.
        """
        # Read current production version before overwriting
        current_pub = await self._repository.get_by_label(
            role_id, PromptLabel.production.value
        )
        previous_version = current_pub.version_sha if current_pub else "unknown"

        # Atomically move production label
        await self._repository.upsert_label(
            role_id=role_id,
            version_sha=to_version,
            label=PromptLabel.production.value,
        )

        effective_at = datetime.now(tz=timezone.utc)
        logger.warning(
            "rollback role_id=%s from=%s... to=%s...",
            role_id,
            previous_version[:8],
            to_version[:8],
        )
        return RollbackResult(
            role_id=role_id,
            previous_version=previous_version,
            rolled_back_to=to_version,
            effective_at=effective_at,
        )
