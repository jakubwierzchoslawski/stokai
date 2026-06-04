"""
compliance.compliance_router — FastAPI router for REQ-N-012 compliance endpoints.

Endpoints:
  GET /api/v1/compliance/track-record/{company_id}
      Returns the recommendation track record and ex-post accuracy for a company.
      Authenticated (any role). No admin restriction — all authenticated users
      can view the track record from the Company Detail screen.

Registered in src/api/main.py with prefix /api/v1/compliance.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth_deps import CurrentUser, get_current_user
from src.api.dependencies import get_db
from src.compliance.compliance_check_service import ComplianceCheckService
from src.compliance.compliance_schemas import TrackRecordResponse
from src.compliance.repositories import (
    SqlComplianceRepository,
    SqlRecommendationRepository,
)
from src.config.settings import get_settings

compliance_router = APIRouter(tags=["compliance"])

_settings = get_settings()


def _get_compliance_service(
    db: AsyncSession = Depends(get_db),
) -> ComplianceCheckService:
    """Dependency: build ComplianceCheckService with SQL repositories."""
    compliance_repo = SqlComplianceRepository(db)
    rec_repo = SqlRecommendationRepository(db)
    return ComplianceCheckService(
        compliance_repo=compliance_repo,
        recommendation_repo=rec_repo,
        disclaimer_threshold=_settings.DISCLAIMER_SAMPLE_SIZE_THRESHOLD,
    )


@compliance_router.get(
    "/compliance/track-record/{company_id}",
    response_model=TrackRecordResponse,
    summary="Get recommendation track record for a company",
    description=(
        "Returns the historical recommendation track record and ex-post accuracy "
        "for the specified company. All authenticated users can access this endpoint. "
        "Entries with sample_size < DISCLAIMER_SAMPLE_SIZE_THRESHOLD have "
        "disclaimer_required=True."
    ),
)
async def get_track_record(
    company_id: UUID,
    limit: int = Query(default=50, ge=1, le=200, description="Maximum number of entries to return"),
    current_user: CurrentUser = Depends(get_current_user),
    service: ComplianceCheckService = Depends(_get_compliance_service),
) -> TrackRecordResponse:
    """
    Retrieve the recommendation track record for a company.

    - limit: 1–200, default 50.
    - Returns 401 for unauthenticated requests (enforced by get_current_user).
    - Returns empty entries list when the company has no recommendations.
    """
    return await service.get_company_track_record(
        company_id=company_id,
        limit=limit,
    )
