"""
event_exposure_repository.py — IEventExposureRepository protocol + SQLAlchemy impl.

Provides ``bulk_insert`` and ``get_active_for_company`` for the
``event_exposure`` table.  Both operations are tenant-scoped.

PLAN-F-003 TASK-003.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Protocol, runtime_checkable
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.event_pipeline.exposure_mapping import ExposureRecord


# ---------------------------------------------------------------------------
# Lightweight value object returned by get_active_for_company
# ---------------------------------------------------------------------------


class EventExposure:
    """Minimal value object for a retrieved event_exposure row.

    Fields are populated from database row mappings.
    """

    def __init__(self, **kwargs: Any) -> None:
        for key, value in kwargs.items():
            setattr(self, key, value)


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class IEventExposureRepository(Protocol):
    """Repository contract for the ``event_exposure`` table (PLAN-F-003).

    All methods include ``tenant_id`` to prevent cross-tenant data leakage.
    """

    async def bulk_insert(
        self,
        event_id: UUID,
        exposures: list[ExposureRecord],
        tenant_id: UUID,
    ) -> None:
        """Insert multiple event_exposure rows atomically.

        Uses ``ON CONFLICT DO UPDATE`` so the operation is idempotent if the
        pipeline is retried for the same ``event_id``.

        Args:
            event_id:  FK linking exposures to the parent geo_event row.
            exposures: List of :class:`ExposureRecord` to persist.
            tenant_id: Owning tenant (written to each row for RLS).
        """
        ...

    async def get_active_for_company(
        self,
        company_id: UUID,
        tenant_id: UUID,
        days: int = 30,
    ) -> list[EventExposure]:
        """Return active exposures for ``company_id`` in the last ``days`` days.

        Joins ``event_exposure`` → ``geo_event`` to apply the ``occurred_at``
        recency filter.

        Args:
            company_id: UUID of the company whose exposures to retrieve.
            tenant_id:  Tenant-scoping UUID.
            days:       Rolling lookback window in days. Defaults to 30.

        Returns:
            List of :class:`EventExposure` objects, possibly empty.
        """
        ...


# ---------------------------------------------------------------------------
# SQLAlchemy 2.0 async implementation
# ---------------------------------------------------------------------------


class EventExposureRepository:
    """SQLAlchemy 2.0 async repository for the ``event_exposure`` table.

    Implements :class:`IEventExposureRepository`.

    Args:
        session: Async SQLAlchemy session bound to the current request/task.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── IEventExposureRepository ──────────────────────────────────────────────

    async def bulk_insert(
        self,
        event_id: UUID,
        exposures: list[ExposureRecord],
        tenant_id: UUID,
    ) -> None:
        """INSERT multiple event_exposure rows, upsert-safe.

        Iterates over ``exposures`` and executes a parameterised
        ``INSERT ... ON CONFLICT DO UPDATE`` for each row.  The
        ``(event_id, company_id)`` composite key uniquely identifies a row.

        Args:
            event_id:  Parent geo_event UUID.
            exposures: Exposure records to persist.
            tenant_id: Tenant-scoping UUID written to each row.
        """
        if not exposures:
            return

        stmt = text(
            """
            INSERT INTO event_exposure (
                event_id,
                company_id,
                magnitude,
                direction,
                geo_weight,
                sector_match,
                tenant_id
            ) VALUES (
                :event_id,
                :company_id,
                :magnitude,
                :direction,
                :geo_weight,
                :sector_match,
                :tenant_id
            )
            ON CONFLICT (event_id, company_id) DO UPDATE
                SET magnitude    = EXCLUDED.magnitude,
                    direction    = EXCLUDED.direction,
                    geo_weight   = EXCLUDED.geo_weight,
                    sector_match = EXCLUDED.sector_match
            """
        )

        for exposure in exposures:
            await self._session.execute(
                stmt,
                {
                    "event_id": event_id,
                    "company_id": exposure.company_id,
                    "magnitude": exposure.magnitude,
                    "direction": exposure.direction,
                    "geo_weight": exposure.geo_weight,
                    "sector_match": exposure.sector_match,
                    "tenant_id": tenant_id,
                },
            )

        await self._session.flush()

    async def get_active_for_company(
        self,
        company_id: UUID,
        tenant_id: UUID,
        days: int = 30,
    ) -> list[EventExposure]:
        """SELECT event_exposure rows for ``company_id`` within ``days`` days.

        Joins to ``geo_event`` to apply the ``occurred_at >= cutoff`` filter.
        Only rows where both ``event_exposure.tenant_id`` and
        ``geo_event.tenant_id`` match are returned.

        Args:
            company_id: Target company UUID.
            tenant_id:  Tenant-scoping UUID.
            days:       Rolling lookback window in days.

        Returns:
            List of :class:`EventExposure` value objects.
        """
        cutoff = datetime.now(tz=timezone.utc) - timedelta(days=days)

        stmt = text(
            """
            SELECT
                ee.event_id,
                ee.company_id,
                ee.magnitude,
                ee.direction,
                ee.geo_weight,
                ee.sector_match,
                ge.occurred_at
            FROM event_exposure ee
            JOIN geo_event ge ON ge.event_id = ee.event_id
            WHERE ee.company_id  = :company_id
              AND ee.tenant_id   = :tenant_id
              AND ge.occurred_at >= :cutoff
            ORDER BY ge.occurred_at DESC
            """
        )

        result = await self._session.execute(
            stmt,
            {
                "company_id": company_id,
                "tenant_id": tenant_id,
                "cutoff": cutoff,
            },
        )

        rows = list(result.mappings())
        return [EventExposure(**dict(row)) for row in rows]
