"""
IEventExposureRepository — protocol for event_exposure table persistence.

PLAN-F-018 TASK-001: Added ExposureRow dataclass.
PLAN-F-018 TASK-002: Added get_by_event method to protocol.
"""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from typing_extensions import Protocol, runtime_checkable

from src.events.models import ExposureCandidate


@dataclass(frozen=True)
class ExposureRow:
    """Immutable snapshot of a single event_exposure row.

    Used by the geo-modifier worker to read event exposure data.
    """

    company_id: UUID
    exposure_type: str  # "geo" | "sector" | "combined"
    direction: str       # "positive" | "negative" | "neutral"
    magnitude: float     # 0.0–1.0


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

    async def get_by_event(
        self, event_id: UUID, tenant_id: UUID
    ) -> list[ExposureRow]:
        """Return all event_exposure rows for the given event_id scoped to tenant_id.

        Returns an empty list (never raises) when no rows exist.

        Args:
            event_id: The event whose exposures to fetch.
            tenant_id: Tenant scoping for IDOR prevention.
        """
        ...
