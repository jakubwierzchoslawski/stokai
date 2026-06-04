"""
api.briefs.briefs_router — FastAPI router for briefs list and detail endpoints.

GET /api/v1/briefs          — paginated briefs list (JWT required)
GET /api/v1/briefs/{id}     — brief detail (JWT required)

PLAN-F-026 TASK-004
"""
from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.api.auth_deps import CurrentUser, get_current_user
from src.api.briefs.briefs_schemas import (
    BriefDetailApiResponse,
    BriefDetailResponse,
    BriefListApiResponse,
    BriefListDataEnvelope,
    BriefListItemResponse,
)
from src.briefs.interfaces.i_brief_service import IBriefService
from src.briefs.schemas.brief_schemas import BriefType
from src.briefs.services.brief_service import BriefNotFoundError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/briefs", tags=["briefs"])


def _get_brief_service() -> IBriefService:
    """Dependency that resolves the BriefService with a real DB session.

    Production wiring: constructs AsyncSession + BriefRepository + BriefService.
    Tests override this dependency via FastAPI's dependency_overrides.
    """
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from src.briefs.repositories.brief_repository import BriefRepository
    from src.briefs.services.brief_service import BriefService
    from src.config.settings import get_settings

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    session = factory()
    repo = BriefRepository(session)
    return BriefService(brief_repository=repo)


@router.get("", response_model=BriefListApiResponse, status_code=status.HTTP_200_OK)
async def list_briefs(
    type: Optional[BriefType] = Query(None, description="Filter by brief type"),
    cursor: Optional[str] = Query(None, description="Pagination cursor"),
    limit: int = Query(20, ge=1, le=50, description="Page size (max 50)"),
    current_user: CurrentUser = Depends(get_current_user),
    brief_service: IBriefService = Depends(_get_brief_service),
) -> BriefListApiResponse:
    """Return paginated briefs list for the authenticated tenant."""
    result = await brief_service.list_briefs(
        user_id=current_user.user_id,
        tenant_id=current_user.tenant_id,
        brief_type=type,
        cursor=cursor,
        limit=limit,
    )

    items = [
        BriefListItemResponse(
            brief_id=p.brief_id,
            type=p.type,
            date=p.sent_at,
            headline=p.headline,
            confidence=p.confidence,
            delivery_status=p.delivery_status,
        )
        for p in result.items
    ]

    return BriefListApiResponse(
        data=BriefListDataEnvelope(items=items, next_cursor=result.next_cursor),
        meta={"limit": limit},
    )


@router.get(
    "/{brief_id}",
    response_model=BriefDetailApiResponse,
    status_code=status.HTTP_200_OK,
)
async def get_brief_detail(
    brief_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    brief_service: IBriefService = Depends(_get_brief_service),
) -> BriefDetailApiResponse:
    """Return full brief detail for the authenticated tenant."""
    try:
        projection = await brief_service.get_brief_detail(
            brief_id=brief_id,
            user_id=current_user.user_id,
            tenant_id=current_user.tenant_id,
        )
    except BriefNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "BRIEF_NOT_FOUND", "message": f"Brief {brief_id} not found."},
        )

    detail = BriefDetailResponse(
        brief_id=projection.brief_id,
        type=projection.type,
        date=projection.sent_at,
        headline=projection.headline,
        confidence=projection.confidence,
        sample_size=projection.sample_size,
        low_sample=projection.low_sample,
        content_html=projection.content_html,
        delivery_status=projection.delivery_status,
    )

    return BriefDetailApiResponse(data=detail, meta={})
