"""
api.v1.earnings_brief_router — Earnings Brief REST endpoints.

Endpoints:
  GET /api/v1/companies/{company_id}/earnings-brief
    Return the most recent earnings brief run for the company (tenant-scoped).
    404 if none found.

  GET /api/v1/earnings-briefs
    Return all earnings brief runs for the tenant (paginated, newest first).

Both endpoints require a valid JWT (Bearer token). Tenant isolation is enforced
via tenant_id from the decoded JWT claim.

PLAN-F-009 TASK-006
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.api.auth_deps import CurrentUser, get_current_user
from src.storage.models.earnings_brief_run import EarningsBriefRun
from src.storage.repositories.earnings_repositories import EarningsBriefRunRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/companies", tags=["earnings-brief"])


# ── Response schemas ──────────────────────────────────────────────────────────


class EarningsBriefRunResponse(BaseModel):
    """Serialised earnings_brief_run row for the API."""

    run_id: UUID
    workflow_id: UUID
    company_id: UUID
    tenant_id: UUID
    earnings_date: str
    status: str
    scenario_tree: dict | None = None
    confidence: float | None = None
    cost_usd: float | None = None
    hil_status: str
    created_at: str | None = None


class EarningsBriefListResponse(BaseModel):
    """Paginated list of earnings brief runs."""

    data: list[EarningsBriefRunResponse]
    total: int


# ── Helper ────────────────────────────────────────────────────────────────────


def _orm_to_response(run: Any) -> EarningsBriefRunResponse:
    """Convert an EarningsBriefRun ORM object to an API response model."""
    return EarningsBriefRunResponse(
        run_id=run.run_id,
        workflow_id=run.workflow_id,
        company_id=run.company_id,
        tenant_id=run.tenant_id,
        earnings_date=run.earnings_date.isoformat()
        if hasattr(run.earnings_date, "isoformat")
        else str(run.earnings_date),
        status=run.status,
        scenario_tree=run.scenario_tree,
        confidence=run.confidence,
        cost_usd=run.cost_usd,
        hil_status=run.hil_status,
        created_at=run.created_at.isoformat()
        if run.created_at and hasattr(run.created_at, "isoformat")
        else None,
    )


def _get_settings():
    from src.config.settings import get_settings
    return get_settings()


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get(
    "/{company_id}/earnings-brief",
    response_model=EarningsBriefRunResponse,
    summary="Get latest earnings brief for a company",
)
async def get_company_earnings_brief(
    company_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
) -> EarningsBriefRunResponse:
    """Return the most recent earnings brief run for the company.

    Args:
        company_id: UUID of the company.
        current_user: Authenticated user from JWT.

    Returns:
        EarningsBriefRunResponse with the latest run.

    Raises:
        HTTPException 404: No earnings brief found for this company.
        HTTPException 401: Missing or invalid JWT.
    """
    tenant_id = current_user.tenant_id

    try:
        settings = _get_settings()
        engine = create_async_engine(settings.DATABASE_URL, echo=False)
        factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        async with factory() as session:
            repo = EarningsBriefRunRepository(session)
            run = await repo.get_latest_by_company(
                company_id=company_id,
                tenant_id=tenant_id,
            )
        await engine.dispose()

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("get_company_earnings_brief DB error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "DB_ERROR", "message": "Database unavailable."},
        )

    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "EARNINGS_BRIEF_NOT_FOUND",
                "message": f"No earnings brief found for company {company_id}.",
            },
        )

    return _orm_to_response(run)


# ── Earnings brief list router (separate prefix) ──────────────────────────────

list_router = APIRouter(prefix="/earnings-briefs", tags=["earnings-brief"])


@list_router.get(
    "",
    response_model=EarningsBriefListResponse,
    summary="List all earnings briefs for the tenant",
)
async def list_earnings_briefs(
    limit: int = Query(default=20, ge=1, le=100),
    current_user: CurrentUser = Depends(get_current_user),
) -> EarningsBriefListResponse:
    """Return all earnings brief runs scoped to the authenticated tenant.

    Newest first, up to `limit` items.

    Args:
        limit: Maximum number of runs to return (1–100, default 20).
        current_user: Authenticated user from JWT.

    Returns:
        EarningsBriefListResponse with paginated data.

    Raises:
        HTTPException 401: Missing or invalid JWT.
    """
    tenant_id = current_user.tenant_id

    try:
        settings = _get_settings()
        engine = create_async_engine(settings.DATABASE_URL, echo=False)
        factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        async with factory() as session:
            stmt = (
                select(EarningsBriefRun)
                .where(EarningsBriefRun.tenant_id == tenant_id)
                .order_by(EarningsBriefRun.created_at.desc())
                .limit(limit)
            )
            result = await session.execute(stmt)
            runs = result.scalars().all()
        await engine.dispose()

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("list_earnings_briefs DB error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "DB_ERROR", "message": "Database unavailable."},
        )

    items = [_orm_to_response(r) for r in runs]
    return EarningsBriefListResponse(data=items, total=len(items))
