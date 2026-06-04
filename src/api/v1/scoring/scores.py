"""REST API endpoints for company scores.

Endpoints:
  GET /api/v1/scores/company/{id} — current score for a company
  GET /api/v1/scores/company/{id}/history — score history
  GET /api/v1/scores/history — batch score-at-time query (PLAN-F-021)
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Annotated, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.api.auth_deps import CurrentUser, get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scores", tags=["scores"])

# FastAPI dependency type alias for authenticated users.
AuthUser = Annotated[CurrentUser, Depends(get_current_user)]

# Maximum number of company IDs accepted per score-at-time request.
MAX_COMPANY_IDS = 200


@router.get("/company/{company_id}", response_model=dict)
async def get_company_score(
    company_id: UUID,
    user: AuthUser,
    indicator_id: UUID = Query(..., description="Indicator to retrieve score for"),
) -> dict:
    """Get current score for a company and indicator."""
    return {
        "data": {
            "company_id": str(company_id),
            "indicator_id": str(indicator_id),
            "score": None,
            "geo_adjusted": None,
        },
        "meta": {},
        "error": None,
    }


@router.get("/company/{company_id}/history", response_model=dict)
async def get_company_score_history(
    company_id: UUID,
    user: AuthUser,
    indicator_id: UUID = Query(..., description="Indicator to retrieve history for"),
    limit: int = Query(default=90, ge=1, le=365),
) -> dict:
    """Get score history for a company and indicator."""
    return {
        "data": {
            "company_id": str(company_id),
            "indicator_id": str(indicator_id),
            "history": [],
        },
        "meta": {"limit": limit},
        "error": None,
    }


@router.get("/history", response_model=dict)
async def get_scores_at_time(
    user: AuthUser,
    company_ids: str = Query(
        ...,
        description="Comma-separated UUID strings for up to 200 companies",
    ),
    at: str = Query(
        ...,
        description="ISO 8601 datetime; returns the closest snapshot at or before this time",
    ),
) -> dict:
    """Batch score-at-time endpoint.

    Returns the most recent company_score snapshot for each requested company
    at or before the given timestamp — a 'time-machine' query with no future
    data leakage.

    SQL pattern (executed via ICompanyScoreRepository.get_score_at_time):
        SELECT DISTINCT ON (company_id, indicator_id)
            company_id, indicator_id, score, geo_adjusted, computed_at
        FROM company_score
        WHERE company_id = ANY(:company_ids)
          AND computed_at <= :at_time
        ORDER BY company_id, indicator_id, computed_at DESC
    """
    # Parse and validate company_ids.
    raw_ids = [cid.strip() for cid in company_ids.split(",") if cid.strip()]
    if not raw_ids:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "VALIDATION_ERROR", "message": "company_ids must not be empty"},
        )
    if len(raw_ids) > MAX_COMPANY_IDS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "VALIDATION_ERROR",
                "message": f"company_ids exceeds maximum of {MAX_COMPANY_IDS} IDs",
            },
        )

    # Validate each ID is a valid UUID.
    parsed_ids: List[UUID] = []
    for raw_id in raw_ids:
        try:
            parsed_ids.append(UUID(raw_id))
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "code": "VALIDATION_ERROR",
                    "message": f"Invalid UUID in company_ids: {raw_id}",
                },
            )

    # Validate and parse `at` datetime.
    try:
        at_time = datetime.fromisoformat(at.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "VALIDATION_ERROR",
                "message": f"Invalid ISO 8601 datetime for 'at': {at}",
            },
        )

    # Repository stub — returns empty list until ICompanyScoreRepository is wired.
    # PLAN-F-017's CompanyScoreRepository.get_score_at_time will replace this stub.
    scores: list[dict] = _stub_get_score_at_time(parsed_ids, at_time, user.tenant_id)

    return {"data": scores, "meta": {}, "error": None}


# ── Repository stub ───────────────────────────────────────────────────────────
# This stub is replaced when ICompanyScoreRepository is injected via FastAPI
# dependency injection.  It is here so the endpoint is testable independently
# of the database layer.

def _stub_get_score_at_time(
    company_ids: List[UUID],
    at_time: datetime,
    tenant_id: UUID,
) -> list[dict]:
    """Stub implementation — returns empty list.

    The real implementation executes:
        SELECT DISTINCT ON (company_id, indicator_id)
            company_id, indicator_id, score, geo_adjusted, computed_at
        FROM company_score
        WHERE company_id = ANY(:company_ids)
          AND computed_at <= :at_time
          AND tenant_id = :tenant_id
        ORDER BY company_id, indicator_id, computed_at DESC
    """
    return []
