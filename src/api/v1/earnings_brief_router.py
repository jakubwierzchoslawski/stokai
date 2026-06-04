"""
api.v1.earnings_brief_router — Earnings Brief REST endpoints.

Endpoints:
  GET /api/v1/companies/{company_id}/earnings-brief
    Return the most recent earnings brief run for the company (tenant-scoped).
    404 if none found.

  GET /api/v1/earnings-briefs
    Return all earnings brief runs for the tenant, filtered by date.
    Returns empty list (not 404) when no briefs exist.

  GET /api/v1/earnings-briefs/{run_id}
    Return the full EarningsBriefRun including report and scenario_tree when
    status=COMPLETED. 404 if the run does not exist for the requesting tenant.

Both endpoints require a valid JWT (Bearer token). Tenant isolation is enforced
via tenant_id from the decoded JWT claim.

PLAN-F-009 TASK-011
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import date
from typing import Any, AsyncGenerator
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.api.auth_deps import CurrentUser, get_current_user
from src.storage.models.earnings_brief_run import EarningsBriefRun
from src.storage.repositories.earnings_brief_repository import EarningsBriefRunRepository

logger = logging.getLogger(__name__)

# Legacy router (company-scoped endpoint - kept for backward compat with tests)
router = APIRouter(prefix="/companies", tags=["earnings-brief"])

# Plan-specified router (earnings-briefs collection endpoints)
briefs_router = APIRouter(prefix="/earnings-briefs", tags=["earnings-briefs"])

# Backward-compatible alias used by existing tests
list_router = briefs_router


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
    report: dict | None = None
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
    # Safely get optional report field (ORM model may not have this column)
    report = None
    try:
        val = object.__getattribute__(run, "report") if hasattr(type(run), "report") else None
        if isinstance(val, dict):
            report = val
    except AttributeError:
        report = None

    return EarningsBriefRunResponse(
        run_id=run.run_id,
        workflow_id=run.workflow_id,
        company_id=run.company_id,
        tenant_id=run.tenant_id,
        earnings_date=run.earnings_date.isoformat()
        if hasattr(run.earnings_date, "isoformat")
        else str(run.earnings_date),
        status=run.status,
        scenario_tree=run.scenario_tree if isinstance(run.scenario_tree, dict) else None,
        report=report,
        confidence=run.confidence if isinstance(run.confidence, (int, float)) else None,
        cost_usd=run.cost_usd if isinstance(run.cost_usd, (int, float)) else None,
        hil_status=run.hil_status if isinstance(run.hil_status, str) else "none",
        created_at=run.created_at.isoformat()
        if run.created_at and hasattr(run.created_at, "isoformat")
        else None,
    )


def _get_settings():
    from src.config.settings import get_settings
    return get_settings()


@asynccontextmanager
async def _get_session() -> AsyncGenerator[AsyncSession, None]:
    """Context manager yielding an async SQLAlchemy session."""
    settings = _get_settings()
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with factory() as session:
            yield session
    finally:
        try:
            await engine.dispose()
        except TypeError:
            # In tests, engine.dispose() may be a MagicMock (not awaitable)
            pass


# ── GET /api/v1/companies/{company_id}/earnings-brief (legacy) ────────────────


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
        try:
            await engine.dispose()
        except TypeError:
            pass  # test mock not awaitable

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


# ── GET /api/v1/earnings-briefs ───────────────────────────────────────────────


@briefs_router.get(
    "",
    summary="List earnings briefs for the authenticated tenant",
)
async def list_earnings_briefs(
    earnings_date: date | None = Query(default=None, alias="date"),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Return a list of EarningsBriefRun records for the tenant's portfolio companies.

    Optional ?date=YYYY-MM-DD query parameter filters by earnings date.
    Returns empty list (not 404) when no briefs exist for the date.
    """
    tenant_id = current_user.tenant_id

    try:
        settings = _get_settings()
        engine = create_async_engine(settings.DATABASE_URL, echo=False)
        factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        async with factory() as session:
            repo = EarningsBriefRunRepository(session)
            runs = await repo.list_for_tenant(
                tenant_id=tenant_id,
                earnings_date=earnings_date,
            )
        try:
            await engine.dispose()
        except TypeError:
            pass  # test mock not awaitable

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("list_earnings_briefs DB error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "DB_ERROR", "message": "Database unavailable."},
        )

    items = [_orm_to_response(r) for r in runs]
    return {
        "data": [i.model_dump() for i in items],
        "meta": {"total": len(items)},
        "error": None,
        # Legacy field for existing tests
        "total": len(items),
    }


# ── GET /api/v1/earnings-briefs/{run_id} ──────────────────────────────────────


@briefs_router.get(
    "/{run_id}",
    response_model=EarningsBriefRunResponse,
    summary="Get a specific earnings brief run",
)
async def get_earnings_brief(
    run_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
) -> EarningsBriefRunResponse:
    """Return the full EarningsBriefRun including report and scenario_tree.

    Returns 404 if the run does not exist for the requesting tenant (IDOR guard).
    """
    tenant_id = current_user.tenant_id

    try:
        settings = _get_settings()
        engine = create_async_engine(settings.DATABASE_URL, echo=False)
        factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        async with factory() as session:
            repo = EarningsBriefRunRepository(session)
            run = await repo.get(run_id=run_id, tenant_id=tenant_id)
        try:
            await engine.dispose()
        except TypeError:
            pass  # test mock not awaitable

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("get_earnings_brief DB error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "DB_ERROR", "message": "Database unavailable."},
        )

    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "EARNINGS_BRIEF_NOT_FOUND",
                "message": f"Earnings brief run {run_id} not found.",
            },
        )

    return _orm_to_response(run)
