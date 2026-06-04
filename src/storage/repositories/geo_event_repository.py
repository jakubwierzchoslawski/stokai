"""
geo_event_repository.py — IGeoEventRepository protocol + SQLAlchemy implementation.

Provides ``insert`` and ``get_by_id`` for the ``geo_event`` table.
Both operations are tenant-scoped.

PLAN-F-003 TASK-002.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Protocol, runtime_checkable
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.event_pipeline.pipeline_state import GeoEvent, GeoEventCreate


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class IGeoEventRepository(Protocol):
    """Repository contract for the ``geo_event`` table (PLAN-F-003).

    This is a narrower protocol than the one in
    ``src.storage.interfaces.i_geo_event_repository`` which serves the full
    reactive pipeline. This protocol is purpose-built for steps 4–5.
    """

    async def insert(self, event: GeoEventCreate, tenant_id: UUID) -> GeoEvent:
        """Insert a new geo_event row and return the resulting :class:`GeoEvent`.

        Args:
            event:     Value object carrying event fields to persist.
            tenant_id: Owning tenant UUID.

        Returns:
            A :class:`GeoEvent` populated with the database-assigned ``event_id``.
        """
        ...

    async def get_by_id(self, event_id: UUID, tenant_id: UUID) -> GeoEvent | None:
        """Fetch a geo_event row by primary key, scoped to ``tenant_id``.

        Args:
            event_id:  UUID of the geo_event to retrieve.
            tenant_id: Tenant-scoping UUID; rows belonging to other tenants
                       are not returned.

        Returns:
            :class:`GeoEvent` if found and tenant matches, ``None`` otherwise.
        """
        ...


# ---------------------------------------------------------------------------
# SQLAlchemy 2.0 async implementation
# ---------------------------------------------------------------------------


class GeoEventRepository:
    """SQLAlchemy 2.0 async repository for the ``geo_event`` table.

    Implements :class:`IGeoEventRepository`.

    Args:
        session: Async SQLAlchemy session bound to the current request/task.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── IGeoEventRepository ───────────────────────────────────────────────────

    async def insert(self, event: GeoEventCreate, tenant_id: UUID) -> GeoEvent:
        """INSERT a geo_event row and return the database-assigned event_id.

        Uses ``RETURNING event_id`` for a single round-trip.  The row is
        flushed so that subsequent queries in the same transaction see it.

        Args:
            event:     Input value object.
            tenant_id: Owning tenant.

        Returns:
            :class:`GeoEvent` with the new ``event_id`` populated.
        """
        stmt = text(
            """
            INSERT INTO geo_event (
                event_id,
                occurred_at,
                detected_at,
                headline,
                geo_regions,
                affected_sectors,
                event_intensity,
                sentiment,
                source_provider,
                tenant_id
            ) VALUES (
                :event_id,
                :occurred_at,
                :detected_at,
                :headline,
                :geo_regions,
                :affected_sectors,
                :event_intensity,
                :sentiment,
                :source_provider,
                :tenant_id
            )
            RETURNING event_id
            """
        )

        new_id = uuid.uuid4()
        result = await self._session.execute(
            stmt,
            {
                "event_id": new_id,
                "occurred_at": event.occurred_at,
                "detected_at": datetime.now(tz=timezone.utc).isoformat(),
                "headline": event.headline,
                "geo_regions": event.geo_regions,
                "affected_sectors": event.sectors_affected,
                "event_intensity": event.event_intensity,
                "sentiment": event.sentiment,
                "source_provider": event.source,
                "tenant_id": tenant_id,
            },
        )
        await self._session.flush()

        returned_id: UUID = result.scalar_one()
        return GeoEvent(
            event_id=returned_id,
            headline=event.headline,
            occurred_at=event.occurred_at,
            tenant_id=tenant_id,
        )

    async def get_by_id(self, event_id: UUID, tenant_id: UUID) -> GeoEvent | None:
        """SELECT a geo_event row by PK, filtered by tenant_id.

        Rows belonging to a different tenant are treated as non-existent.

        Args:
            event_id:  UUID to look up.
            tenant_id: Tenant-scoping UUID.

        Returns:
            :class:`GeoEvent` if the row exists and the tenant matches, else ``None``.
        """
        stmt = text(
            """
            SELECT event_id, headline, occurred_at, tenant_id
            FROM geo_event
            WHERE event_id = :event_id
              AND tenant_id = :tenant_id
            """
        )
        result = await self._session.execute(
            stmt, {"event_id": event_id, "tenant_id": tenant_id}
        )
        row = result.mappings().one_or_none()
        if row is None:
            return None
        return GeoEvent(
            event_id=row["event_id"],
            headline=row.get("headline", ""),
            occurred_at=str(row.get("occurred_at", "")),
            tenant_id=row["tenant_id"],
        )
