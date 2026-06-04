"""
IGeoEventRepository — protocol for geo_event table persistence.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from typing_extensions import Protocol, runtime_checkable

from src.events.models import ClassificationResult, RawEvent


class GeoEventRow:
    """Minimal value object returned by get_by_id.

    Real implementations will populate all fields from the DB row.
    """

    def __init__(self, **kwargs: Any) -> None:
        for key, value in kwargs.items():
            setattr(self, key, value)


@runtime_checkable
class IGeoEventRepository(Protocol):
    """Repository interface for the geo_event table."""

    async def upsert_raw(self, raw_event: RawEvent) -> UUID:
        """Insert a staging row from a raw event and return the generated event_id.

        Args:
            raw_event: The inbound raw event to persist.

        Returns:
            Newly assigned UUID for the event.
        """
        ...

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
        """Update the staging row with classification and derived fields.

        Args:
            event_id: PK of the existing staging row.
            classification: LLM-derived classification result.
            title: Human-readable event title.
            summary: Short event summary.
            lat: Optional latitude of event origin.
            lon: Optional longitude of event origin.
            source_provider: Original source adapter identifier.
            tenant_id: Owning tenant, or None for global events.
        """
        ...

    async def get_by_id(self, event_id: UUID) -> GeoEventRow | None:
        """Fetch a geo_event row by primary key.

        Args:
            event_id: UUID to look up.

        Returns:
            GeoEventRow if found, None otherwise.
        """
        ...
