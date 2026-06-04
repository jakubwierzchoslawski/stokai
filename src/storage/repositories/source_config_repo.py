"""
storage.repositories.source_config_repo — ISourceConfigRepository interface and
PostgresSourceConfigRepository implementation.

All queries use SQLAlchemy 2.0 async sessions with parameterised statements only.
set_enabled() atomically updates ``enabled`` and ``updated_at`` in a single UPDATE
so the RegistryRefresher can poll on ``updated_at`` to detect stale state.

No business logic lives here — only data access.
"""
from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.storage.models.source_config import SourceConfig

if TYPE_CHECKING:
    from src.admin.schemas import SourceConfigCreate, SourceConfigUpdate


class ISourceConfigRepository(ABC):
    """Interface for source_config persistence operations."""

    @abstractmethod
    async def list_all(self) -> list[SourceConfig]:
        """Return all source_config rows, including disabled ones."""

    @abstractmethod
    async def get_by_id(self, source_id: uuid.UUID) -> SourceConfig | None:
        """Return a single SourceConfig or None if not found."""

    @abstractmethod
    async def create(self, data: "SourceConfigCreate") -> SourceConfig:
        """Persist a new SourceConfig and return it with generated source_id."""

    @abstractmethod
    async def set_enabled(self, source_id: uuid.UUID, enabled: bool) -> SourceConfig:
        """Atomically flip enabled and refresh updated_at. Return updated row.

        Idempotent: disabling an already-disabled source succeeds without error.

        Raises:
            ValueError: If source_id does not exist.
        """

    @abstractmethod
    async def update(self, source_id: uuid.UUID, data: "SourceConfigUpdate") -> SourceConfig:
        """Update mutable fields on an existing SourceConfig. Return updated row.

        Raises:
            ValueError: If source_id does not exist.
        """


class PostgresSourceConfigRepository(ISourceConfigRepository):
    """SQLAlchemy 2.0 async implementation of ISourceConfigRepository.

    Constructor-injected AsyncSession (DIP). No new sessions are created here.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_all(self) -> list[SourceConfig]:
        """Return all source_config rows ordered by priority DESC, display_name ASC."""
        stmt = select(SourceConfig).order_by(
            SourceConfig.priority.desc(),
            SourceConfig.display_name,
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id(self, source_id: uuid.UUID) -> SourceConfig | None:
        stmt = select(SourceConfig).where(SourceConfig.source_id == source_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, data: "SourceConfigCreate") -> SourceConfig:
        """Insert a new SourceConfig. enabled is always False on creation."""
        now = datetime.now(timezone.utc)
        sc = SourceConfig(
            interface_type=data.interface_type,
            display_name=data.display_name,
            enabled=False,  # AC-002: new sources start disabled
            credentials_ref=data.credentials_ref,
            config=data.config or {},
            cost_tier=data.cost_tier,
            priority=data.priority,
            updated_at=now,
        )
        self._session.add(sc)
        await self._session.flush()  # populate server defaults (source_id)
        await self._session.refresh(sc)
        return sc

    async def set_enabled(self, source_id: uuid.UUID, enabled: bool) -> SourceConfig:
        """Atomically update enabled and updated_at in one UPDATE statement.

        The atomic update of updated_at lets RegistryRefresher detect changes
        by polling MAX(updated_at) instead of doing a full table scan.
        """
        now = datetime.now(timezone.utc)
        stmt = (
            update(SourceConfig)
            .where(SourceConfig.source_id == source_id)
            .values(enabled=enabled, updated_at=now)
            .returning(SourceConfig)
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            raise ValueError(f"SourceConfig {source_id} not found")
        return row

    async def update(self, source_id: uuid.UUID, data: "SourceConfigUpdate") -> SourceConfig:
        now = datetime.now(timezone.utc)
        values: dict = {"updated_at": now}
        if data.display_name is not None:
            values["display_name"] = data.display_name
        if data.interface_type is not None:
            values["interface_type"] = data.interface_type
        if data.credentials_ref is not None:
            values["credentials_ref"] = data.credentials_ref
        if data.config is not None:
            values["config"] = data.config
        if data.cost_tier is not None:
            values["cost_tier"] = data.cost_tier
        if data.priority is not None:
            values["priority"] = data.priority

        stmt = (
            update(SourceConfig)
            .where(SourceConfig.source_id == source_id)
            .values(**values)
            .returning(SourceConfig)
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            raise ValueError(f"SourceConfig {source_id} not found")
        return row
