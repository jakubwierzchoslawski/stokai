"""
alerts.api.anti_fatigue_router — Anti-fatigue settings endpoints (PLAN-F-025).

Endpoints:
  GET   /api/v1/settings/anti-fatigue  — read current settings
  PATCH /api/v1/settings/anti-fatigue  — partial update settings
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth_deps import CurrentUser, get_current_user
from src.api.dependencies import get_db
from src.alerts.exceptions import ValidationError
from src.alerts.schemas import AntiFatigueSettingsResponse, UpdateAntiFatigueRequest
from src.alerts.services.anti_fatigue_settings import AntiFatigueSettingsService

anti_fatigue_router = APIRouter(prefix="/settings/anti-fatigue", tags=["anti-fatigue"])


# ── Dependencies ──────────────────────────────────────────────────────────────


async def _get_anti_fatigue_service(
    db: AsyncSession = Depends(get_db),
) -> AntiFatigueSettingsService:
    return AntiFatigueSettingsService(db)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _success(data) -> dict:
    return {"data": data, "error": None}


# ── Endpoints ─────────────────────────────────────────────────────────────────


@anti_fatigue_router.get(
    "",
    status_code=status.HTTP_200_OK,
    response_model=None,
    summary="Get anti-fatigue settings for the authenticated user",
)
async def get_anti_fatigue_settings(
    current_user: CurrentUser = Depends(get_current_user),
    svc: AntiFatigueSettingsService = Depends(_get_anti_fatigue_service),
) -> dict:
    settings = await svc.get_settings(
        user_id=current_user.user_id, tenant_id=current_user.tenant_id
    )
    return _success(settings.model_dump())


@anti_fatigue_router.patch(
    "",
    status_code=status.HTTP_200_OK,
    response_model=None,
    summary="Update anti-fatigue settings (partial update)",
)
async def update_anti_fatigue_settings(
    body: UpdateAntiFatigueRequest,
    current_user: CurrentUser = Depends(get_current_user),
    svc: AntiFatigueSettingsService = Depends(_get_anti_fatigue_service),
) -> dict:
    try:
        settings = await svc.update_settings(
            user_id=current_user.user_id,
            tenant_id=current_user.tenant_id,
            request=body,
        )
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "VALIDATION_ERROR", "message": str(exc)},
        ) from exc
    return _success(settings.model_dump())
