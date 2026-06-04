"""
storage.repositories.prompt_publication_repository — PromptPublicationRepository.

PLAN-F-014 TASK-003 (AC-003).

Provides upsert_label / get_by_label / list_history operations over the
prompt_publication table. The UNIQUE (role_id, label) constraint means
that moving a label to a new version requires an upsert (INSERT ... ON CONFLICT).

No tenant scoping — prompt publications are system-level artefacts.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Protocol, runtime_checkable
from uuid import UUID

from sqlalchemy import desc, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.storage.models.prompt_publication import PromptPublication

logger = logging.getLogger(__name__)


# ── Protocol ──────────────────────────────────────────────────────────────────


@runtime_checkable
class IPromptPublicationRepository(Protocol):
    """Repository contract for prompt_publication CRUD."""

    async def upsert_label(
        self,
        role_id: str,
        version_sha: str,
        label: str,
        langfuse_version_id: str | None = None,
        published_by: UUID | None = None,
    ) -> PromptPublication:
        """Insert or update the (role_id, label) row to the given version_sha."""
        ...

    async def get_by_label(
        self, role_id: str, label: str
    ) -> PromptPublication | None:
        """Return the active publication for the given (role_id, label), or None."""
        ...

    async def list_history(
        self, role_id: str, limit: int = 50
    ) -> list[PromptPublication]:
        """Return publication history for role_id ordered by published_at DESC."""
        ...


# ── SQLAlchemy implementation ─────────────────────────────────────────────────


class PromptPublicationRepository:
    """SQLAlchemy 2.0 async repository for the prompt_publication table.

    Uses PostgreSQL INSERT ... ON CONFLICT (role_id, label) DO UPDATE to
    atomically move a label to a new version without deleting audit rows
    (the row is updated in-place, keeping the same pub_id).

    Args:
        session: AsyncSession to use for all queries.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── IPromptPublicationRepository contract ─────────────────────────────────

    async def upsert_label(
        self,
        role_id: str,
        version_sha: str,
        label: str,
        langfuse_version_id: str | None = None,
        published_by: UUID | None = None,
    ) -> PromptPublication:
        """INSERT or UPDATE the (role_id, label) row.

        If the (role_id, label) pair already exists, version_sha,
        langfuse_version_id, published_by, and published_at are updated.
        Otherwise, a new row is inserted.

        Args:
            role_id: Prompt role identifier (e.g. "exposure_analyst").
            version_sha: 40-char git blob SHA or hashlib fallback.
            label: One of production|staging|canary|experimental.
            langfuse_version_id: Optional Langfuse version identifier.
            published_by: UUID of the publisher.

        Returns:
            The refreshed PromptPublication ORM object.
        """
        now = datetime.now(tz=timezone.utc)

        # Use raw SQL for PostgreSQL-specific ON CONFLICT ... DO UPDATE
        stmt = text(
            """
            INSERT INTO prompt_publication
                (role_id, version_sha, label, langfuse_version_id, published_by, published_at)
            VALUES
                (:role_id, :version_sha, :label, :langfuse_version_id, :published_by, :published_at)
            ON CONFLICT (role_id, label)
            DO UPDATE SET
                version_sha        = EXCLUDED.version_sha,
                langfuse_version_id = EXCLUDED.langfuse_version_id,
                published_by       = EXCLUDED.published_by,
                published_at       = EXCLUDED.published_at
            RETURNING pub_id
            """
        )
        result = await self._session.execute(
            stmt,
            {
                "role_id": role_id,
                "version_sha": version_sha,
                "label": label,
                "langfuse_version_id": langfuse_version_id,
                "published_by": str(published_by) if published_by else None,
                "published_at": now,
            },
        )
        pub_id = result.scalar_one()

        # Fetch the refreshed ORM object
        select_stmt = select(PromptPublication).where(
            PromptPublication.pub_id == pub_id
        )
        row_result = await self._session.execute(select_stmt)
        pub = row_result.scalar_one()
        logger.debug(
            "upsert_label role_id=%s label=%s sha=%s...", role_id, label, version_sha[:8]
        )
        return pub

    async def get_by_label(
        self, role_id: str, label: str
    ) -> PromptPublication | None:
        """Return the active publication for the given (role_id, label), or None.

        Args:
            role_id: Prompt role identifier.
            label: One of production|staging|canary|experimental.

        Returns:
            PromptPublication ORM object, or None if no matching row exists.
        """
        stmt = select(PromptPublication).where(
            PromptPublication.role_id == role_id,
            PromptPublication.label == label,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_history(
        self, role_id: str, limit: int = 50
    ) -> list[PromptPublication]:
        """Return publication history for role_id ordered by published_at DESC.

        Args:
            role_id: Prompt role identifier.
            limit: Maximum number of rows to return (default 50).

        Returns:
            List of PromptPublication objects, newest first.
        """
        stmt = (
            select(PromptPublication)
            .where(PromptPublication.role_id == role_id)
            .order_by(desc(PromptPublication.published_at))
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
