"""
alerts.api.alerts_router — GET /api/v1/alerts (Alerts Center, PLAN-F-025).

Returns a paginated, filterable list of alerts for the authenticated user.
Always returns 200 (empty list when no results). 422 on invalid params.
"""
from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth_deps import CurrentUser, get_current_user
from src.api.dependencies import get_db
from src.alerts.repositories.alerts_read_repository import AlertsReadRepository
from src.alerts.schemas import AlertListItem, AlertListResponse

alerts_router = APIRouter(prefix="/alerts", tags=["alerts"])

# ── Dependencies ──────────────────────────────────────────────────────────────


async def _get_alerts_repo(db: AsyncSession = Depends(get_db)) -> AlertsReadRepository:
    return AlertsReadRepository(db)


# ── Endpoints ─────────────────────────────────────────────────────────────────


@alerts_router.get(
    "",
    status_code=status.HTTP_200_OK,
    response_model=AlertListResponse,
    summary="List alerts for the authenticated user",
)
async def list_alerts(
    page: Annotated[int, Query(ge=1, description="1-based page number")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="Items per page (1-100)")] = 20,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    action_signal: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    current_user: CurrentUser = Depends(get_current_user),
    repo: AlertsReadRepository = Depends(_get_alerts_repo),
) -> AlertListResponse:
    """Return a paginated, filterable list of alerts.

    Filters are optional; omitting them returns all alerts for the user.
    page_size is clamped to [1, 100].
    """
    items, total = await repo.list_alerts(
        user_id=current_user.user_id,
        tenant_id=current_user.tenant_id,
        page=page,
        page_size=page_size,
        status=status_filter,
        action_signal=action_signal,
        date_from=date_from,
        date_to=date_to,
    )
    has_next = (page * page_size) < total
    return AlertListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        has_next=has_next,
    )
