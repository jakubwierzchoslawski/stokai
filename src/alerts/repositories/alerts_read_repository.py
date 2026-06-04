"""
AlertsReadRepository — paginated read access to the alert+geo_event join.

Returns (list[AlertListItem], total_count) for the Alerts Center API.
All queries are scoped to user_id + tenant_id (no cross-tenant leakage).
"""
from __future__ import annotations

import logging
from datetime import datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.alerts.schemas import AlertListItem

logger = logging.getLogger(__name__)


class AlertsReadRepository:
    """Read-side repository for the Alerts Center list view.

    Args:
        session: Async SQLAlchemy session (injected by caller).
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_alerts(
        self,
        *,
        user_id: UUID,
        tenant_id: UUID,
        page: int = 1,
        page_size: int = 20,
        status: str | None = None,
        action_signal: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> tuple[list[AlertListItem], int]:
        """Return a paginated list of alerts and the unfiltered total count.

        Args:
            user_id: Owning user — filters and scopes the query.
            tenant_id: Tenant scope (mandatory, prevents cross-tenant leakage).
            page: 1-based page number.
            page_size: Number of items per page.
            status: Optional status filter (e.g. 'dispatched').
            action_signal: Optional action_signal filter (e.g. 'BUY_OPP').
            date_from: Optional lower bound for dispatched_at.
            date_to: Optional upper bound for dispatched_at.

        Returns:
            Tuple of (items, total_count).
        """
        offset = (page - 1) * page_size

        # Build dynamic WHERE clauses
        filters = [
            "a.user_id   = :user_id",
            "a.tenant_id = :tenant_id",
        ]
        params: dict = {
            "user_id": user_id,
            "tenant_id": tenant_id,
            "limit": page_size,
            "offset": offset,
        }

        if status is not None:
            filters.append("a.status = :status")
            params["status"] = status

        if action_signal is not None:
            filters.append("a.action_signal = :action_signal")
            params["action_signal"] = action_signal

        if date_from is not None:
            filters.append("a.dispatched_at >= :date_from")
            params["date_from"] = date_from

        if date_to is not None:
            filters.append("a.dispatched_at <= :date_to")
            params["date_to"] = date_to

        where_clause = " AND ".join(filters)

        items_sql = text(
            f"""
            SELECT
                a.alert_id,
                a.dispatched_at,
                ge.title           AS event_title,
                a.action_signal,
                a.confidence,
                a.channel,
                a.status,
                a.event_id,
                ge.lat,
                ge.lon
            FROM alert a
            LEFT JOIN geo_event ge ON ge.event_id = a.event_id
            WHERE {where_clause}
            ORDER BY a.dispatched_at DESC NULLS LAST
            LIMIT :limit OFFSET :offset
            """
        )

        count_sql = text(
            f"""
            SELECT COUNT(*)
            FROM alert a
            LEFT JOIN geo_event ge ON ge.event_id = a.event_id
            WHERE {where_clause}
            """
        )

        # Count params do not need limit/offset
        count_params = {k: v for k, v in params.items() if k not in ("limit", "offset")}

        rows_result = await self._session.execute(items_sql, params)
        count_result = await self._session.execute(count_sql, count_params)

        total = int(count_result.scalar() or 0)
        rows = rows_result.mappings().all()

        items: list[AlertListItem] = []
        for row in rows:
            lat = row["lat"]
            lon = row["lon"]
            event_id = row["event_id"]
            event_link = f"/map?event={event_id}&lat={lat}&lon={lon}"

            items.append(
                AlertListItem(
                    alert_id=row["alert_id"],
                    occurred_at=row["dispatched_at"],
                    event_title=row["event_title"] or "",
                    action_signal=row["action_signal"] or "",
                    confidence=float(row["confidence"] or 0.0),
                    channel=row["channel"],
                    status=row["status"],
                    event_link=event_link,
                    report_link=None,
                )
            )

        logger.debug(
            "AlertsReadRepository.list_alerts: user=%s page=%d returned %d/%d",
            user_id,
            page,
            len(items),
            total,
        )
        return items, total
