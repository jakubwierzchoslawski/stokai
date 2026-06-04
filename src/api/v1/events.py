"""REST API endpoint for geo-events.

Endpoints:
  GET /api/v1/events — list recent events (with optional date-range filter)

Date-range filter (PLAN-F-021):
  When ?from= and ?to= are both provided, returns events with
  occurred_at >= from_date AND occurred_at <= to_date + 1 day (inclusive bounds).
  Both parameters must be supplied together or not at all.

PLAN-F-019 defined the original endpoint.
PLAN-F-021 TASK-011 adds the from/to date-range filter.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, status

from src.api.auth import CurrentUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/events", tags=["events"])


@router.get("", response_model=dict)
async def get_events(
    user: CurrentUser,
    context: Optional[str] = Query(
        default="global",
        description="Map context: global | portfolio | sector",
    ),
    sector: Optional[str] = Query(default=None, description="Sector filter (sector mode only)"),
    bbox: Optional[str] = Query(default=None, description="Bounding box: west,south,east,north"),
    zoom: Optional[int] = Query(default=None, description="Map zoom level"),
    # Date-range filter (PLAN-F-021)
    from_date: Optional[date] = Query(
        default=None,
        alias="from",
        description="ISO date YYYY-MM-DD (inclusive). Must be used together with 'to'.",
    ),
    to_date: Optional[date] = Query(
        default=None,
        alias="to",
        description="ISO date YYYY-MM-DD (inclusive). Must be used together with 'from'.",
    ),
) -> dict:
    """Return geo-events matching the current filters.

    When ?from and ?to are both supplied, the endpoint returns historical events
    within the date range instead of the live feed.  The WebSocket subscription
    is NOT established for date-filtered calls — range queries are strictly REST.

    When ?from/?to are absent, the endpoint returns the most recent live events.
    """
    # Guard: from and to must both be present or both absent.
    if (from_date is None) != (to_date is None):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "VALIDATION_ERROR",
                "message": "Both 'from' and 'to' parameters are required when either is provided",
            },
        )

    # Guard: from must be before or equal to to.
    if from_date is not None and to_date is not None:
        if from_date > to_date:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "code": "VALIDATION_ERROR",
                    "message": "from_date must be before to_date",
                },
            )

    # Historical range query.
    if from_date is not None and to_date is not None:
        events = _stub_get_events_in_range(
            from_date=from_date,
            to_date=to_date,
            tenant_id=user.tenant_id,
        )
        return {
            "data": events,
            "meta": {
                "from": str(from_date),
                "to": str(to_date),
                "count": len(events),
            },
            "error": None,
        }

    # Live mode — return recent events (stub).
    events = _stub_get_recent_events(
        context=context or "global",
        sector=sector,
        bbox=bbox,
        zoom=zoom,
        tenant_id=user.tenant_id,
    )
    return {
        "data": events,
        "meta": {"context": context, "count": len(events)},
        "error": None,
    }


# ── Repository stubs ──────────────────────────────────────────────────────────
# These stubs are replaced when IEventRepository is injected via FastAPI
# dependency injection (wired in a future plan or in production setup).

def _stub_get_events_in_range(
    from_date: date,
    to_date: date,
    tenant_id,
) -> List[dict]:
    """Stub: IEventRepository.get_events_in_range.

    Real SQL:
        SELECT * FROM geo_event
        WHERE occurred_at >= :from_date
          AND occurred_at <= :to_date + interval '1 day'
          AND (tenant_id = :tenant_id OR tenant_id IS NULL)
        ORDER BY occurred_at ASC
    """
    return []


def _stub_get_recent_events(
    context: str,
    sector: Optional[str],
    bbox: Optional[str],
    zoom: Optional[int],
    tenant_id,
) -> List[dict]:
    """Stub: IEventRepository.get_recent_events."""
    return []
