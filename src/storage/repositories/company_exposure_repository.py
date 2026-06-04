"""
company_exposure_repository.py — ICompanyRepository protocol + SQLAlchemy implementation.

Provides ``get_tracked_companies`` which reads the ``company`` table joined with
``company_score`` to compute normalised ``market_cap_weight`` values.

PLAN-F-003 TASK-001.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.event_pipeline.exposure_mapping import TrackedCompany


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class ICompanyRepository(Protocol):
    """Repository contract for tracked company data.

    All methods are tenant-scoped to prevent cross-tenant data leakage.
    """

    async def get_tracked_companies(self, tenant_id: UUID) -> list[TrackedCompany]:
        """Return all tracked companies for ``tenant_id``.

        Reads the ``company`` table filtered by ``is_tracked = TRUE`` and
        joins with ``company_score`` to derive normalised ``market_cap_weight``
        values (score / sum_of_all_scores across the tenant universe).

        Args:
            tenant_id: The UUID of the requesting tenant. Must not be None.

        Returns:
            List of :class:`TrackedCompany` instances, one per tracked company.
            The list is empty when no companies are tracked.
        """
        ...


# ---------------------------------------------------------------------------
# SQLAlchemy 2.0 async implementation
# ---------------------------------------------------------------------------


class CompanyExposureRepository:
    """SQLAlchemy 2.0 async repository for tracked-company exposure data.

    Args:
        session: An async SQLAlchemy session bound to the current request.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── ICompanyRepository ────────────────────────────────────────────────────

    async def get_tracked_companies(self, tenant_id: UUID) -> list[TrackedCompany]:
        """Return tracked companies with normalised market-cap weights.

        Joins ``company`` with ``company_score`` (latest score per company).
        Normalises ``market_cap_weight`` as::

            weight_i = score_i / SUM(score_j  for all tracked j)

        So that weights sum to 1.0 across the tenant's tracked universe.

        Only companies with ``is_tracked = TRUE`` and ``tenant_id = :tenant_id``
        are returned.

        Args:
            tenant_id: Tenant-scoping UUID.

        Returns:
            List of :class:`TrackedCompany`.
        """
        stmt = text(
            """
            WITH scored AS (
                SELECT
                    c.company_id,
                    c.sector_internal,
                    c.sector_gics,
                    c.geo_revenue,
                    COALESCE(cs.composite_score, 0.0)::float AS raw_score
                FROM company c
                LEFT JOIN LATERAL (
                    SELECT composite_score
                    FROM company_score
                    WHERE company_id = c.company_id
                    ORDER BY scored_at DESC
                    LIMIT 1
                ) cs ON TRUE
                WHERE c.tenant_id = :tenant_id
                  AND c.is_tracked = TRUE
            ),
            total AS (
                SELECT NULLIF(SUM(raw_score), 0.0) AS total_score FROM scored
            )
            SELECT
                s.company_id,
                s.sector_internal,
                s.sector_gics,
                s.geo_revenue,
                CASE
                    WHEN t.total_score IS NULL THEN 0.0
                    ELSE s.raw_score / t.total_score
                END AS market_cap_weight
            FROM scored s
            CROSS JOIN total t
            """
        )

        result = await self._session.execute(stmt, {"tenant_id": tenant_id})
        rows = list(result.mappings())

        companies: list[TrackedCompany] = []
        for row in rows:
            geo_revenue = row["geo_revenue"] or {}
            # geo_revenue may be stored as JSONB dict already; ensure it's a plain dict
            if not isinstance(geo_revenue, dict):
                geo_revenue = {}

            companies.append(
                TrackedCompany(
                    company_id=row["company_id"],
                    sector_internal=row["sector_internal"] or "",
                    sector_gics=row["sector_gics"] or "",
                    geo_revenue=geo_revenue,
                    market_cap_weight=float(row["market_cap_weight"]),
                )
            )

        return companies
