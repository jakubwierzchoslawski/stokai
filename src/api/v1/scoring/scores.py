"""REST API endpoints for company scores.

Endpoints:
  GET /api/v1/scores/company/{id} — current score for a company
  GET /api/v1/scores/company/{id}/history — score history
"""
from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Query

from src.api.auth import CurrentUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scores", tags=["scores"])


@router.get("/company/{company_id}", response_model=dict)
async def get_company_score(
    company_id: UUID,
    indicator_id: UUID = Query(..., description="Indicator to retrieve score for"),
    user: CurrentUser = None,
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
    indicator_id: UUID = Query(..., description="Indicator to retrieve history for"),
    limit: int = Query(default=90, ge=1, le=365),
    user: CurrentUser = None,
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
