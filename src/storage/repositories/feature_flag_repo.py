"""
storage.repositories.feature_flag_repo — IFeatureFlagRepository interface and
PostgresFeatureFlagRepository implementation.

All queries are scoped by environment (not tenant — flags are system-wide per env).
"""
from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.storage.models.feature_flag import FeatureFlag


class IFeatureFlagRepository(ABC):
    """Interface for feature_flag persistence operations."""

    @abstractmethod
    async def list_all(self, environment: str) -> list[FeatureFlag]:
        """Return all flags for the given environment, ordered by flag_id."""

    @abstractmethod
    async def get(
        self, flag_id: str, environment: str
    ) -> FeatureFlag | None:
        """Return the flag for (flag_id, environment), or None."""

    @abstractmethod
    async def set_enabled(
        self,
        flag_id: str,
        environment: str,
        enabled: bool,
        updated_by: uuid.UUID,
    ) -> FeatureFlag:
        """Update the enabled state for a flag atomically.

        Raises:
            ValueError: If (flag_id, environment) does not exist.
        """


class PostgresFeatureFlagRepository(IFeatureFlagRepository):
    """SQLAlchemy 2.0 async implementation of IFeatureFlagRepository."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_all(self, environment: str) -> list[FeatureFlag]:
        stmt = (
            select(FeatureFlag)
            .where(FeatureFlag.environment == environment)
            .order_by(FeatureFlag.flag_id)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get(self, flag_id: str, environment: str) -> FeatureFlag | None:
        stmt = select(FeatureFlag).where(
            FeatureFlag.flag_id == flag_id,
            FeatureFlag.environment == environment,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def set_enabled(
        self,
        flag_id: str,
        environment: str,
        enabled: bool,
        updated_by: uuid.UUID,
    ) -> FeatureFlag:
        now = datetime.now(timezone.utc)
        stmt = (
            update(FeatureFlag)
            .where(
                FeatureFlag.flag_id == flag_id,
                FeatureFlag.environment == environment,
            )
            .values(enabled=enabled, updated_at=now, updated_by=updated_by)
            .returning(FeatureFlag)
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            raise ValueError(
                f"FeatureFlag ({flag_id!r}, {environment!r}) not found"
            )
        return row
