"""
api.routers.onboarding_router — FastAPI router for onboarding endpoints.

Endpoints:
  GET  /api/v1/onboarding/state   — return current onboarding state
  POST /api/v1/onboarding/profile — select scoring profile
  POST /api/v1/onboarding/skip    — skip onboarding

Security: JWT auth required on all endpoints (get_current_user).
tenant_id: extracted from JWT claims only — never from request body.

PLAN-F-024 TASK-006
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from src.api.auth_deps import CurrentUser, get_current_user
from src.portfolio.onboarding_service import OnboardingService, OnboardingState

onboarding_router = APIRouter(prefix="/onboarding", tags=["onboarding"])


# ── Helpers ───────────────────────────────────────────────────────────────────


def _success(data, meta: dict | None = None) -> dict:
    return {"data": data, "meta": meta or {}, "error": None}


def _error(code: str, message: str) -> dict:
    return {"data": None, "error": {"code": code, "message": message}}


# ── Dependency (overridden in tests and composition root) ─────────────────────


async def _get_onboarding_service() -> OnboardingService:
    """Build an OnboardingService. Overridden in tests via dependency_overrides."""
    raise NotImplementedError(
        "_get_onboarding_service must be overridden in the composition root or tests."
    )


# ── Request schemas ───────────────────────────────────────────────────────────


class SelectProfileRequest(BaseModel):
    profile_id: uuid.UUID


# ── Endpoints ─────────────────────────────────────────────────────────────────


@onboarding_router.get(
    "/state",
    status_code=status.HTTP_200_OK,
    summary="Get current onboarding state",
)
async def get_onboarding_state(
    current_user: CurrentUser = Depends(get_current_user),
    svc: OnboardingService = Depends(_get_onboarding_service),
) -> dict:
    """Return the onboarding state for the authenticated user."""
    state = await svc.get_onboarding_state(current_user.tenant_id, current_user.user_id)
    return _success(state.model_dump())


@onboarding_router.post(
    "/profile",
    status_code=status.HTTP_200_OK,
    summary="Select a scoring profile",
)
async def select_scoring_profile(
    body: SelectProfileRequest,
    current_user: CurrentUser = Depends(get_current_user),
    svc: OnboardingService = Depends(_get_onboarding_service),
) -> dict:
    """Persist the user's chosen scoring profile."""
    await svc.select_scoring_profile(
        current_user.tenant_id,
        current_user.user_id,
        body.profile_id,
    )
    return _success({"profile_id": str(body.profile_id)})


@onboarding_router.post(
    "/skip",
    status_code=status.HTTP_200_OK,
    summary="Skip onboarding",
)
async def skip_onboarding(
    current_user: CurrentUser = Depends(get_current_user),
    svc: OnboardingService = Depends(_get_onboarding_service),
) -> dict:
    """Mark onboarding as skipped for the authenticated user."""
    await svc.mark_skipped(current_user.tenant_id, current_user.user_id)
    return _success({"skipped": True})
