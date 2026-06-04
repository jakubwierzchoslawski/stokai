"""
storage.repositories.company_repo — CompanyRepository.

Provides admin-facing operations for the company universe:
  - set_tracked: toggle is_tracked flag for a company
  - list_tracked: paginated list of tracked companies for a tenant
  - search_by_name_or_ticker: fuzzy name/ticker search (ILIKE)

PLAN-F-030 TASK-003
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, String, Text, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession


class CompanyRepository:
    """SQLAlchemy 2.0 async repository for company universe admin operations.

    Uses raw SQL via text() since the company table lives outside the ORM
    models already defined in this service. Queries are always tenant-scoped.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def set_tracked(
        self,
        company_id: uuid.UUID,
        is_tracked: bool,
        tenant_id: uuid.UUID,
    ) -> dict | None:
        """Toggle is_tracked on a company row.

        Returns:
            The updated company row as a dict, or None if not found.
        """
        stmt = text(
            """
            UPDATE company
               SET is_tracked = :is_tracked,
                   updated_at = :now
             WHERE company_id = :company_id
               AND tenant_id  = :tenant_id
            RETURNING company_id, ticker, name, is_tracked
            """
        )
        result = await self._session.execute(
            stmt,
            {
                "is_tracked": is_tracked,
                "now": datetime.now(timezone.utc),
                "company_id": company_id,
                "tenant_id": tenant_id,
            },
        )
        row = result.mappings().one_or_none()
        if row is None:
            return None
        return dict(row)

    async def list_tracked(
        self,
        tenant_id: uuid.UUID,
        page: int = 1,
        page_size: int = 50,
    ) -> dict:
        """Return a paginated list of tracked companies for a tenant.

        Returns:
            {"items": [...], "total": int, "page": int, "page_size": int}
        """
        offset = (page - 1) * page_size

        count_stmt = text(
            """
            SELECT COUNT(*) FROM company
             WHERE tenant_id = :tenant_id
               AND is_tracked = TRUE
            """
        )
        total_result = await self._session.execute(count_stmt, {"tenant_id": tenant_id})
        total = total_result.scalar_one()

        items_stmt = text(
            """
            SELECT company_id, ticker, name, is_tracked, sector_gics
              FROM company
             WHERE tenant_id = :tenant_id
               AND is_tracked = TRUE
             ORDER BY name
             LIMIT :limit OFFSET :offset
            """
        )
        items_result = await self._session.execute(
            items_stmt,
            {"tenant_id": tenant_id, "limit": page_size, "offset": offset},
        )
        items = [dict(row) for row in items_result.mappings().all()]

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    async def search_by_name_or_ticker(
        self,
        tenant_id: uuid.UUID,
        query: str,
        limit: int = 20,
    ) -> list[dict]:
        """Search companies by name or ticker using ILIKE.

        Returns up to *limit* matching rows ordered by ticker.
        """
        pattern = f"%{query}%"
        stmt = text(
            """
            SELECT company_id, ticker, name, is_tracked
              FROM company
             WHERE tenant_id = :tenant_id
               AND (name ILIKE :pattern OR ticker ILIKE :pattern)
             ORDER BY ticker
             LIMIT :limit
            """
        )
        result = await self._session.execute(
            stmt,
            {"tenant_id": tenant_id, "pattern": pattern, "limit": limit},
        )
        return [dict(row) for row in result.mappings().all()]
