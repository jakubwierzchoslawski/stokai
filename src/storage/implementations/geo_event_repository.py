"""
GeoEventRepository — SQLAlchemy 2.0 async implementation of IGeoEventRepository.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.events.models import ClassificationResult, RawEvent
from src.storage.interfaces.i_geo_event_repository import GeoEventRow, IGeoEventRepository


class GeoEventRepository:
    """Async SQLAlchemy repository for the geo_event table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── IGeoEventRepository ───────────────────────────────────────────────────

    async def upsert_raw(self, raw_event: RawEvent) -> UUID:
        """Insert a staging row and return the generated event_id."""
        stmt = text(
            """
            INSERT INTO geo_event (
                occurred_at, detected_at, source_provider, raw_payload, tenant_id
            ) VALUES (
                :occurred_at, :detected_at, :source_provider, :raw_payload::jsonb, :tenant_id
            )
            RETURNING event_id
            """
        )
        result = await self._session.execute(
            stmt,
            {
                "occurred_at": raw_event.occurred_at,
                "detected_at": datetime.now(tz=timezone.utc),
                "source_provider": raw_event.source_provider,
                "raw_payload": json.dumps(raw_event.raw_payload),
                "tenant_id": raw_event.tenant_id,
            },
        )
        await self._session.flush()
        return result.scalar_one()

    async def persist_classified(
        self,
        event_id: UUID,
        classification: ClassificationResult,
        title: str,
        summary: str,
        lat: float | None,
        lon: float | None,
        source_provider: str,
        tenant_id: UUID | None,
    ) -> None:
        """Update the staging row with full classification data."""
        stmt = text(
            """
            UPDATE geo_event
            SET
                title = :title,
                summary = :summary,
                lat = :lat,
                lon = :lon,
                category = :category,
                intensity = :intensity,
                sentiment = :sentiment,
                geo_regions = :geo_regions,
                affected_sectors = :affected_sectors,
                cameo_code = :cameo_code
            WHERE event_id = :event_id
            """
        )
        await self._session.execute(
            stmt,
            {
                "title": title,
                "summary": summary,
                "lat": lat,
                "lon": lon,
                "category": classification.category,
                "intensity": classification.intensity,
                "sentiment": classification.sentiment,
                "geo_regions": classification.geo_regions,
                "affected_sectors": classification.affected_sectors,
                "cameo_code": classification.cameo_code,
                "event_id": event_id,
            },
        )
        await self._session.flush()

    async def get_by_id(self, event_id: UUID) -> GeoEventRow | None:
        """Fetch a geo_event row by primary key."""
        stmt = text(
            """
            SELECT * FROM geo_event WHERE event_id = :event_id
            """
        )
        result = await self._session.execute(stmt, {"event_id": event_id})
        row = result.scalar_one_or_none()
        if row is None:
            return None
        if hasattr(row, "_asdict"):
            return GeoEventRow(**row._asdict())
        return row
