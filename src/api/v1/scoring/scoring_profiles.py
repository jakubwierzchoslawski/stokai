"""REST API endpoints for scoring profiles.

Endpoints:
  GET  /api/v1/scoring-profiles — list profiles
  POST /api/v1/scoring-profiles — create profile
  DELETE /api/v1/scoring-profiles/{id} — delete (built-ins protected)
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from src.api.auth import CurrentUser, AdminUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scoring-profiles", tags=["scoring-profiles"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class ProfileIndicatorWeightRequest(BaseModel):
    indicator_id: UUID
    weight: float


class CreateProfileRequest(BaseModel):
    name: str
    indicators: list[ProfileIndicatorWeightRequest]


class ProfileResponse(BaseModel):
    profile_id: str
    name: str
    is_builtin: bool
    version: int
    indicators: list[dict[str, Any]]
    tenant_id: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("", response_model=dict)
async def list_scoring_profiles(user: CurrentUser) -> dict:
    """List all scoring profiles for the current tenant."""
    # In production: load from DB via ProfileService
    return {
        "data": {"profiles": []},
        "meta": {"tenant_id": str(user.tenant_id)},
        "error": None,
    }


@router.post("", status_code=status.HTTP_201_CREATED, response_model=dict)
async def create_scoring_profile(
    request: CreateProfileRequest,
    user: AdminUser,
) -> dict:
    """Create a custom scoring profile."""
    from src.scoring.schemas.scoring_profile import ProfileIndicatorWeight, ScoringProfileRecord

    indicators = [
        ProfileIndicatorWeight(indicator_id=iw.indicator_id, weight=iw.weight)
        for iw in request.indicators
    ]
    record = ScoringProfileRecord.new(
        tenant_id=user.tenant_id,
        name=request.name,
        indicators=indicators,
        is_builtin=False,
    )

    return {
        "data": _profile_to_dict(record),
        "meta": {},
        "error": None,
    }


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_scoring_profile(
    profile_id: UUID,
    user: AdminUser,
) -> None:
    """Delete a custom scoring profile. Built-in profiles are protected."""
    # In production: check is_builtin flag from DB, raise 409 if builtin
    pass


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _profile_to_dict(record) -> dict:
    return {
        "profile_id": str(record.profile_id),
        "name": record.name,
        "is_builtin": record.is_builtin,
        "version": record.version,
        "indicators": [
            {"indicator_id": str(iw.indicator_id), "weight": iw.weight}
            for iw in record.indicators
        ],
        "tenant_id": str(record.tenant_id),
    }
