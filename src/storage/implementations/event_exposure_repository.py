"""
EventExposureRepository — SQLAlchemy 2.0 async implementation of IEventExposureRepository.

PLAN-F-018 TASK-002: Added get_by_event method.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.events.models import ExposureCandidate
from src.storage.interfaces.i_event_exposure_repository import (
    ExposureRow,
    IEventExposureRepository,
)


class EventExposureRepository:
    """Async SQLAlchemy repository for the event_exposure table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── IEventExposureRepository ──────────────────────────────────────────────

    async def bulk_insert(
        self, event_id: UUID, candidates: list[ExposureCandidate]
    ) -> None:
        """Insert multiple exposure rows using parameterised SQL.

        Uses ON CONFLICT DO UPDATE to be idempotent on the composite PK
        (event_id, company_id).
        """
        if not candidates:
            return

        stmt = text(
            """
            INSERT INTO event_exposure (
                event_id, company_id, exposure_type, direction, magnitude
            ) VALUES (
                :event_id, :company_id, :exposure_type, :direction, :magnitude
            )
            ON CONFLICT (event_id, company_id) DO UPDATE
                SET exposure_type = EXCLUDED.exposure_type,
                    direction = EXCLUDED.direction,
                    magnitude = EXCLUDED.magnitude
            """
        )

        for candidate in candidates:
            await self._session.execute(
                stmt,
                {
                    "event_id": event_id,
                    "company_id": candidate.company_id,
                    "exposure_type": candidate.exposure_type,
                    "direction": candidate.direction,
                    "magnitude": candidate.magnitude,
                },
            )

        await self._session.flush()

    async def get_by_event(
        self, event_id: UUID, tenant_id: UUID
    ) -> list[ExposureRow]:
        """Return all event_exposure rows for the given event_id scoped to tenant_id.

        Uses a single parameterised SELECT. Returns [] on empty result set.

        Args:
            event_id: The event whose exposures to fetch.
            tenant_id: Tenant scoping for IDOR prevention.
        """
        stmt = text(
            """
            SELECT company_id, exposure_type, direction, magnitude
            FROM event_exposure
            WHERE event_id = :event_id AND tenant_id = :tenant_id
            """
        )
        result = await self._session.execute(
            stmt,
            {"event_id": event_id, "tenant_id": tenant_id},
        )
        rows = result.fetchall()
        return [
            ExposureRow(
                company_id=row.company_id,
                exposure_type=row.exposure_type,
                direction=row.direction,
                magnitude=row.magnitude,
            )
            for row in rows
        ]
