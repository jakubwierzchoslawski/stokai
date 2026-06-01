"""RawEventRepository — DB access for raw_events table.

Single Responsibility: all DB queries for raw_events in one place.
No business logic here — only data access.

Dependency Inversion: the repository is injected into pipeline steps and the
  executor; steps never import SQLAlchemy directly.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

logger = logging.getLogger(__name__)


class RawEventRepository:
    """Async repository for the ``raw_events`` table.

    In production this class uses an injected ``AsyncSession``.  For the
    purposes of the pipeline task wiring, a session factory is used.

    Methods
    -------
    get_status(raw_event_id) -> str | None
    get_by_id(raw_event_id) -> RawEvent | None
    update_status(raw_event_id, status, *, failed_step, error_detail)
    save(raw_event) -> None
    update_fingerprint(raw_event_id, fingerprint) -> None
    set_generated_at(raw_event_id, generated_at) -> None
    """

    def __init__(self, session: Any = None) -> None:
        self._session = session

    async def get_status(self, raw_event_id: uuid.UUID) -> str | None:
        """Return pipeline_status for the given raw_event_id, or None."""
        if self._session is None:
            return None
        from sqlalchemy import select
        from src.db.models.raw_event import RawEvent

        stmt = select(RawEvent.pipeline_status).where(
            RawEvent.event_id == raw_event_id
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id(self, raw_event_id: uuid.UUID) -> Any | None:
        """Return the RawEvent ORM instance by primary key."""
        if self._session is None:
            return None
        from sqlalchemy import select
        from src.db.models.raw_event import RawEvent

        stmt = select(RawEvent).where(RawEvent.event_id == raw_event_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def save(self, raw_event: Any) -> None:
        """Persist a new RawEvent to the DB."""
        if self._session is None:
            return
        self._session.add(raw_event)
        await self._session.flush()

    async def update_status(
        self,
        raw_event_id: uuid.UUID,
        status: str,
        *,
        failed_step: str | None = None,
        error_detail: str | None = None,
    ) -> None:
        """Update pipeline_status (and optionally failed_step/error_detail)."""
        if self._session is None:
            logger.warning(
                "RawEventRepository.update_status called without session; "
                "raw_event_id=%s status=%s",
                raw_event_id,
                status,
            )
            return
        from sqlalchemy import update
        from src.db.models.raw_event import RawEvent

        values: dict[str, Any] = {"pipeline_status": status}
        if failed_step is not None:
            values["failed_step"] = failed_step
        if error_detail is not None:
            values["error_detail"] = error_detail

        stmt = (
            update(RawEvent)
            .where(RawEvent.event_id == raw_event_id)
            .values(**values)
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def update_fingerprint(
        self, raw_event_id: uuid.UUID, fingerprint: str
    ) -> None:
        """Write the computed fingerprint to the raw_events record."""
        if self._session is None:
            return
        from sqlalchemy import update
        from src.db.models.raw_event import RawEvent

        stmt = (
            update(RawEvent)
            .where(RawEvent.event_id == raw_event_id)
            .values(fingerprint=fingerprint)
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def set_generated_at(
        self, raw_event_id: uuid.UUID, generated_at: Any
    ) -> None:
        """Write generated_at timestamp when the pipeline trace closes."""
        if self._session is None:
            return
        from sqlalchemy import update
        from src.db.models.raw_event import RawEvent

        stmt = (
            update(RawEvent)
            .where(RawEvent.event_id == raw_event_id)
            .values(generated_at=generated_at)
        )
        await self._session.execute(stmt)
        await self._session.flush()
