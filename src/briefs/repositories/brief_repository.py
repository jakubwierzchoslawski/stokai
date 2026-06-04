"""
briefs.repositories.brief_repository — BriefRepository.

Queries workflow_run as a brief projection. Cursor-based pagination.
IDOR prevention enforced at query level via tenant_id in every WHERE clause.

PLAN-F-026 TASK-001
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.briefs.interfaces.i_brief_repository import IBriefRepository
from src.briefs.schemas.brief_schemas import (
    BRIEF_WORKFLOW_TYPES,
    BriefProjection,
    BriefType,
    decode_cursor,
    encode_cursor,
)
from src.storage.models.workflow_run import WorkflowRun

logger = logging.getLogger(__name__)

_LOW_SAMPLE_THRESHOLD = 5


def _extract_projection(row: WorkflowRun) -> BriefProjection:
    """Extract a BriefProjection from a WorkflowRun ORM row."""
    fs: dict = row.final_state or {}
    headline = fs.get("headline") or ""
    content_html = fs.get("content_html") or ""
    confidence = float(fs.get("confidence") or 0.0)
    sample_size = int(fs.get("sample_size") or 0)
    low_sample = sample_size < _LOW_SAMPLE_THRESHOLD

    return BriefProjection(
        brief_id=row.workflow_id,
        type=BriefType(row.workflow_type),
        headline=headline,
        content_html=content_html,
        confidence=confidence,
        sample_size=sample_size,
        low_sample=low_sample,
        delivery_status=row.status,
        sent_at=row.completed_at,
    )


class BriefRepository(IBriefRepository):
    """SQLAlchemy 2.0 async repository for brief projections over workflow_run.

    Constructor-injected AsyncSession (DIP).
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_briefs(
        self,
        tenant_id: UUID,
        brief_type: Optional[BriefType],
        cursor: Optional[str],
        limit: int,
    ) -> tuple[list[BriefProjection], Optional[str]]:
        """Return (items, next_cursor) for brief list with cursor pagination."""
        type_filter = [brief_type.value] if brief_type else BRIEF_WORKFLOW_TYPES

        conditions = [
            WorkflowRun.tenant_id == tenant_id,
            WorkflowRun.workflow_type.in_(type_filter),
        ]

        if cursor:
            try:
                cursor_dt, cursor_id = decode_cursor(cursor)
                # Keyset pagination: rows where (completed_at, workflow_id) < cursor
                # completed_at DESC ordering means "less than" in time = older
                conditions.append(
                    and_(
                        WorkflowRun.completed_at != None,  # noqa: E711
                        WorkflowRun.completed_at <= cursor_dt,
                        ~(
                            (WorkflowRun.completed_at == cursor_dt)
                            & (WorkflowRun.workflow_id == cursor_id)
                        ),
                    )
                    | (WorkflowRun.completed_at < cursor_dt)
                )
            except Exception:
                logger.warning("Invalid cursor %s; ignoring", cursor)

        stmt = (
            select(WorkflowRun)
            .where(*conditions)
            .order_by(
                WorkflowRun.completed_at.desc().nullslast(),
                WorkflowRun.workflow_id.desc(),
            )
            .limit(limit + 1)  # fetch one extra to determine if next page exists
        )

        result = await self._session.execute(stmt)
        rows = list(result.scalars().all())

        has_next = len(rows) > limit
        page_rows = rows[:limit]

        next_cursor: Optional[str] = None
        if has_next and page_rows:
            last = page_rows[-1]
            if last.completed_at:
                next_cursor = encode_cursor(last.completed_at, last.workflow_id)

        projections = [_extract_projection(r) for r in page_rows]
        return projections, next_cursor

    async def get_brief(
        self,
        brief_id: UUID,
        tenant_id: UUID,
    ) -> Optional[BriefProjection]:
        """Return the brief projection or None.

        Never raises for missing / tenant mismatch (IDOR prevention).
        """
        stmt = select(WorkflowRun).where(
            WorkflowRun.workflow_id == brief_id,
            WorkflowRun.tenant_id == tenant_id,
            WorkflowRun.workflow_type.in_(BRIEF_WORKFLOW_TYPES),
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return _extract_projection(row)
