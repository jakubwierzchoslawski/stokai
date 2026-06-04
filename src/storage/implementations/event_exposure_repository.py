"""
EventExposureRepository — SQLAlchemy 2.0 async implementation of IEventExposureRepository.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.events.models import ExposureCandidate
from src.storage.interfaces.i_event_exposure_repository import IEventExposureRepository


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
