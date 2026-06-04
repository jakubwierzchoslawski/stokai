"""REST API endpoint for geo-modifier reapplication.

Endpoints:
  POST /api/v1/scoring/geo-modifier/reapply — reapply geo-modifier with current profile

PLAN-F-018 TASK-007
"""
from __future__ import annotations

import logging
from uuid import UUID

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from src.api.auth_deps import CurrentUser, get_current_user

_CurrentUser = Annotated[CurrentUser, Depends(get_current_user)]

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/geo-modifier", tags=["geo-modifier"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class ReapplyGeoModifierRequest(BaseModel):
    event_id: UUID
    profile_id: UUID


# ---------------------------------------------------------------------------
# Dependency stubs — overridden in tests via app.dependency_overrides
# ---------------------------------------------------------------------------

async def get_exposure_repo():
    """Provide an IEventExposureRepository instance.

    In production this should use a real DB session from a dependency.
    Override via app.dependency_overrides[get_exposure_repo] in tests.
    """
    raise NotImplementedError("get_exposure_repo dependency must be overridden")  # pragma: no cover


async def get_profile_repo():
    """Provide an IScoringProfileRepository instance.

    In production this should use a real DB session from a dependency.
    Override via app.dependency_overrides[get_profile_repo] in tests.
    """
    raise NotImplementedError("get_profile_repo dependency must be overridden")  # pragma: no cover


# ---------------------------------------------------------------------------
# Module-level enqueue function — importable for patching in tests
# ---------------------------------------------------------------------------

def _enqueue_geo_modifier(event_id: str, tenant_id: str) -> None:
    """Enqueue the geo-modifier Celery task.

    Separated into a named module-level function so tests can patch it easily:
        patch("src.api.v1.scoring.geo_modifier._enqueue_geo_modifier")
    """
    from src.scoring.geo_modifier_worker import apply_geo_modifier_delay
    apply_geo_modifier_delay(event_id=event_id, tenant_id=tenant_id)


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post("/reapply", status_code=status.HTTP_202_ACCEPTED)
async def reapply_geo_modifier(
    body: ReapplyGeoModifierRequest,
    user: _CurrentUser,
    exposure_repo=Depends(get_exposure_repo),
    profile_repo=Depends(get_profile_repo),
) -> dict:
    """Re-trigger the geo-modifier task for a previously processed event.

    Validates that:
    - The event has event_exposure rows (404 if not).
    - The profile belongs to the calling user's tenant (403 if not).

    Then enqueues scoring.apply_geo_modifier as a fire-and-forget Celery task.
    The task loads the current indicator geo_weight values from DB at execution time.

    Authentication: valid JWT required.
    Roles: end_user, operator, admin — all permitted.

    Returns:
        202 Accepted with {"data": {"task_queued": true, "event_id": "<uuid>"}}
    """
    tenant_id = user.tenant_id

    # Step 1: Validate event has exposure rows
    try:
        exposures = await exposure_repo.get_by_event(body.event_id, tenant_id)
    except Exception as exc:
        logger.exception("reapply_geo_modifier: exposure lookup failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "INTERNAL_ERROR", "message": "Failed to look up event exposures"},
        )

    if not exposures:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "EVENT_NOT_FOUND",
                "message": f"No event_exposure rows found for event_id={body.event_id}",
            },
        )

    # Step 2: Validate profile belongs to calling tenant
    try:
        profile = await profile_repo.get_by_id(body.profile_id, tenant_id)
    except Exception as exc:
        logger.exception("reapply_geo_modifier: profile lookup failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "INTERNAL_ERROR", "message": "Failed to look up scoring profile"},
        )

    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "FORBIDDEN",
                "message": f"profile_id={body.profile_id} does not belong to your tenant",
            },
        )

    # Step 3: Enqueue the geo-modifier task (fire-and-forget)
    try:
        _enqueue_geo_modifier(
            event_id=str(body.event_id),
            tenant_id=str(tenant_id),
        )
    except Exception as exc:
        logger.exception("reapply_geo_modifier: enqueue failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "ENQUEUE_FAILED", "message": "Failed to enqueue geo-modifier task"},
        )

    logger.info(
        "reapply_geo_modifier: task enqueued for event=%s tenant=%s",
        body.event_id,
        tenant_id,
    )

    return {
        "data": {
            "task_queued": True,
            "event_id": str(body.event_id),
        },
        "meta": {},
        "error": None,
    }
