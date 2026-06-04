"""
IEventExposureRepository — protocol for event_exposure table persistence.
"""
from __future__ import annotations

from uuid import UUID

from typing_extensions import Protocol, runtime_checkable

from src.events.models import ExposureCandidate


@runtime_checkable
class IEventExposureRepository(Protocol):
    """Repository interface for the event_exposure table."""

    async def bulk_insert(
        self, event_id: UUID, candidates: list[ExposureCandidate]
    ) -> None:
        """Insert multiple event_exposure rows.

        Implementations should upsert on the (event_id, company_id) composite PK
        so that re-running the pipeline for the same event is idempotent.

        Args:
            event_id: FK linking exposures to the parent geo_event.
            candidates: List of exposure candidates to persist.
        """
        ...
