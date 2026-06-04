"""
storage.repositories.ingestion_job_repo — IIngestionJobRepository interface
and PostgresIngestionJobRepository implementation.

All queries are tenant-scoped to prevent IDOR leakage.
"""
from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.storage.models.ingestion_job import IngestionJob, IngestionJobStatus


class IIngestionJobRepository(ABC):
    """Interface for ingestion_job persistence operations."""

    @abstractmethod
    async def list_all(self, tenant_id: uuid.UUID) -> list[IngestionJob]:
        """Return all jobs for the given tenant, ordered by name."""

    @abstractmethod
    async def get_by_id(
        self, job_id: uuid.UUID, tenant_id: uuid.UUID
    ) -> IngestionJob | None:
        """Return a single IngestionJob scoped to tenant_id, or None."""

    @abstractmethod
    async def set_status(
        self,
        job_id: uuid.UUID,
        status: IngestionJobStatus,
        error_count_delta: int = 0,
    ) -> IngestionJob:
        """Update job status atomically, incrementing error_count if delta > 0.

        Also refreshes updated_at to now().

        Raises:
            ValueError: If job_id does not exist.
        """


class PostgresIngestionJobRepository(IIngestionJobRepository):
    """SQLAlchemy 2.0 async implementation of IIngestionJobRepository."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_all(self, tenant_id: uuid.UUID) -> list[IngestionJob]:
        stmt = (
            select(IngestionJob)
            .where(IngestionJob.tenant_id == tenant_id)
            .order_by(IngestionJob.name)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id(
        self, job_id: uuid.UUID, tenant_id: uuid.UUID
    ) -> IngestionJob | None:
        stmt = select(IngestionJob).where(
            IngestionJob.job_id == job_id,
            IngestionJob.tenant_id == tenant_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def set_status(
        self,
        job_id: uuid.UUID,
        status: IngestionJobStatus,
        error_count_delta: int = 0,
    ) -> IngestionJob:
        now = datetime.now(timezone.utc)
        values: dict = {
            "status": status.value,
            "updated_at": now,
        }
        if error_count_delta != 0:
            values["error_count"] = IngestionJob.error_count + error_count_delta

        stmt = (
            update(IngestionJob)
            .where(IngestionJob.job_id == job_id)
            .values(**values)
            .returning(IngestionJob)
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            raise ValueError(f"IngestionJob {job_id} not found")
        return row
