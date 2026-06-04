"""
router.py — FastAPI router for Progressive Disclosure endpoints.

PLAN-F-020 TASK-004

Endpoints (all require JWT auth):
  GET /api/v1/events/{event_id}/popup        → 200 PopupDataResponse | 404
  GET /api/v1/events/{event_id}/side-panel   → 200 SidePanelDataResponse | 404
  GET /api/v1/events/{event_id}/audit-trail  → 200 AuditTrailResponse | 404
  GET /api/v1/events/{event_id}/deep-dive    → 200 DeepDiveResponse | 202 pending | 404

Controller responsibility only: parse, validate path params, delegate to service, respond.
All business logic and ownership checks live in the service layer.
"""
from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse

from src.api.auth_deps import CurrentUser, get_current_user
from src.api.progressive_disclosure.schemas import (
    AuditTrailApiResponse,
    AuditTrailResponse,
    DeepDiveApiResponse,
    DeepDivePendingResponse,
    DeepDiveResponse,
    PopupApiResponse,
    PopupDataResponse,
    SidePanelApiResponse,
    SidePanelDataResponse,
)
from src.api.progressive_disclosure.service import (
    DeepDiveNotReadyError,
    EventNotFoundError,
    ProgressiveDisclosureService,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["progressive-disclosure"])


def _get_service() -> ProgressiveDisclosureService:
    """Production dependency: wires repository + service.

    Tests override via FastAPI dependency_overrides.
    """
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from src.api.progressive_disclosure.repositories.progressive_disclosure_repository import (
        ProgressiveDisclosureRepository,
    )
    from src.config.settings import get_settings

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    session = factory()
    repo = ProgressiveDisclosureRepository(session)
    return ProgressiveDisclosureService(repository=repo)


@router.get(
    "/events/{event_id}/popup",
    response_model=PopupApiResponse,
    status_code=status.HTTP_200_OK,
    summary="Get popup-level data for a map event",
)
async def get_popup(
    event_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: ProgressiveDisclosureService = Depends(_get_service),
) -> PopupApiResponse:
    """Return Level 1 popup data for a map event.

    Renders within 300ms for events already in the TanStack Query cache.
    Returns 404 when the event does not exist or belongs to a different tenant
    (IDOR prevention — 403 would confirm existence).
    """
    try:
        data = await service.get_popup(event_id, current_user.tenant_id)
    except EventNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    except Exception:
        logger.exception("Unexpected error in get_popup for event_id=%s", event_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred",
        )

    return PopupApiResponse(data=data)


@router.get(
    "/events/{event_id}/side-panel",
    response_model=SidePanelApiResponse,
    status_code=status.HTTP_200_OK,
    summary="Get full side-panel data for a map event",
)
async def get_side_panel(
    event_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: ProgressiveDisclosureService = Depends(_get_service),
) -> SidePanelApiResponse:
    """Return Level 2 side-panel data including sparklines, analogies, and rationale.

    Returns 404 when the event does not exist or belongs to a different tenant.
    """
    try:
        data = await service.get_side_panel(event_id, current_user.tenant_id)
    except EventNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    except Exception:
        logger.exception("Unexpected error in get_side_panel for event_id=%s", event_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred",
        )

    return SidePanelApiResponse(data=data)


@router.get(
    "/events/{event_id}/audit-trail",
    response_model=AuditTrailApiResponse,
    status_code=status.HTTP_200_OK,
    summary="Get audit trail for a map event (Why this read?)",
)
async def get_audit_trail(
    event_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: ProgressiveDisclosureService = Depends(_get_service),
) -> AuditTrailApiResponse:
    """Return audit trail: prompt SHA, reasoning chain, Langfuse trace link.

    Ownership is verified via service layer. Returns 404 for foreign event IDs.
    """
    try:
        data = await service.get_audit_trail(event_id, current_user.tenant_id)
    except EventNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    except Exception:
        logger.exception("Unexpected error in get_audit_trail for event_id=%s", event_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred",
        )

    return AuditTrailApiResponse(data=data)


@router.get(
    "/events/{event_id}/deep-dive",
    status_code=status.HTTP_200_OK,
    summary="Get deep-dive analysis for a map event",
)
async def get_deep_dive(
    event_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: ProgressiveDisclosureService = Depends(_get_service),
) -> JSONResponse:
    """Return Level 3 deep-dive analysis.

    Returns 202 Accepted with ``{"status": "pending"}`` body when the deep-dive
    workflow has not yet completed. The frontend polls every 5 seconds.
    Returns 404 when the event does not exist or belongs to a different tenant.
    """
    try:
        data = await service.get_deep_dive(event_id, current_user.tenant_id)
    except EventNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    except DeepDiveNotReadyError:
        return JSONResponse(
            content={"status": "pending"},
            status_code=status.HTTP_202_ACCEPTED,
        )
    except Exception:
        logger.exception("Unexpected error in get_deep_dive for event_id=%s", event_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred",
        )

    response_body = DeepDiveApiResponse(data=data)
    return JSONResponse(
        content=response_body.model_dump(mode="json"),
        status_code=status.HTTP_200_OK,
    )
