"""
admin.system.router — FastAPI router for the System Operations panel.

All endpoints require require_admin() dependency.
Response envelope: {"data": ..., "meta": {}, "error": null}

Endpoints:
  GET    /api/v1/admin/system/jobs
  POST   /api/v1/admin/system/jobs/{job_id}/trigger
  GET    /api/v1/admin/system/cost
  PATCH  /api/v1/admin/system/cost/threshold
  GET    /api/v1/admin/system/companies
  POST   /api/v1/admin/system/companies/{company_id}/track
  DELETE /api/v1/admin/system/companies/{company_id}/track
  GET    /api/v1/admin/system/companies/search?q=...
  GET    /api/v1/admin/system/cache
  POST   /api/v1/admin/system/cache/refresh
  GET    /api/v1/admin/system/flags
  PATCH  /api/v1/admin/system/flags/{flag_id}

PLAN-F-030 TASK-008
"""
from __future__ import annotations

import os
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.admin.dependencies import require_admin
from src.admin.system.cache_service import CacheService, InvalidDataTypeError
from src.admin.system.feature_flag_service import FeatureFlagService
from src.admin.system.schemas import (
    CacheRefreshRequest,
    FeatureFlagUpdateRequest,
    ThresholdUpdateRequest,
)
from src.admin.system.service import SystemOpsService
from src.ai.budget_guard import BudgetGuard
from src.ingestion.job_registry import JobNotFoundError, JobRegistry
from src.storage.models.user import User
from src.storage.repositories.company_repo import CompanyRepository
from src.storage.repositories.cost_record_repo import PostgresCostRecordRepository
from src.storage.repositories.feature_flag_repo import PostgresFeatureFlagRepository
from src.storage.repositories.ingestion_job_repo import PostgresIngestionJobRepository

system_ops_router = APIRouter(prefix="/system", tags=["admin-system"])


# ── Response helpers ───────────────────────────────────────────────────────────

def _ok(data) -> dict:
    return {"data": data, "meta": {}, "error": None}


def _err(code: str, message: str) -> dict:
    return {"data": None, "error": {"code": code, "message": message}}


# ── Dependency builder ─────────────────────────────────────────────────────────

async def _get_db_from_request(request: Request) -> AsyncSession:
    """Extract DB session from request state (set in lifespan)."""
    from src.api.auth.dependencies import get_db
    async for session in get_db():
        return session


async def _get_service(
    request: Request,
    current_user: User = Depends(require_admin),
) -> SystemOpsService:
    """Build SystemOpsService with all dependencies injected."""
    from src.api.auth.dependencies import get_db

    # Get DB session
    db: AsyncSession | None = None
    async for session in get_db():
        db = session
        break

    environment = os.environ.get("ENVIRONMENT", "production")

    job_repo = PostgresIngestionJobRepository(db)
    cost_repo = PostgresCostRecordRepository(db)
    flag_repo = PostgresFeatureFlagRepository(db)
    company_repo = CompanyRepository(db)

    job_registry = JobRegistry.instance()

    budget_guard = BudgetGuard(cost_repo=cost_repo)

    redis = getattr(request.app.state, "redis", None)
    if redis is None:
        import redis.asyncio as aioredis
        from src.config.settings import get_settings
        settings = get_settings()
        redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)

    cache_service = CacheService(redis)
    flag_service = FeatureFlagService(flag_repo, redis, environment)

    return SystemOpsService(
        job_repo=job_repo,
        cost_repo=cost_repo,
        flag_repo=flag_repo,
        company_repo=company_repo,
        job_registry=job_registry,
        budget_guard=budget_guard,
        cache_service=cache_service,
        flag_service=flag_service,
        tenant_id=current_user.tenant_id,
        environment=environment,
    )


# ── Ingestion Jobs ─────────────────────────────────────────────────────────────

@system_ops_router.get("/jobs", summary="List all ingestion jobs")
async def list_jobs(
    current_user: User = Depends(require_admin),
    service: SystemOpsService = Depends(_get_service),
) -> JSONResponse:
    jobs = await service.list_jobs()
    result = [
        {
            "job_id": str(j.job_id),
            "name": j.name,
            "schedule": j.schedule,
            "last_run": j.last_run.isoformat() if j.last_run else None,
            "next_run": j.next_run.isoformat() if j.next_run else None,
            "status": j.status,
            "error_count": j.error_count,
            "last_error_trace": j.last_error_trace,
            "updated_at": j.updated_at.isoformat(),
        }
        for j in jobs
    ]
    return JSONResponse(status_code=status.HTTP_200_OK, content=_ok(result))


@system_ops_router.post("/jobs/{job_id}/trigger", summary="Manually trigger an ingestion job")
async def trigger_job(
    job_id: uuid.UUID,
    current_user: User = Depends(require_admin),
    service: SystemOpsService = Depends(_get_service),
) -> JSONResponse:
    try:
        result = await service.trigger_job(job_id)
    except JobNotFoundError as exc:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=_err("NOT_FOUND", str(exc)),
        )
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=_ok({"job_id": result.job_id, "task_id": result.task_id, "status": result.status}),
    )


# ── Cost Monitor ───────────────────────────────────────────────────────────────

@system_ops_router.get("/cost", summary="Get monthly cost summary")
async def get_cost(
    current_user: User = Depends(require_admin),
    service: SystemOpsService = Depends(_get_service),
) -> JSONResponse:
    data = await service.get_cost_data()
    return JSONResponse(status_code=status.HTTP_200_OK, content=_ok(data))


@system_ops_router.patch("/cost/threshold", summary="Update monthly budget threshold")
async def update_threshold(
    body: ThresholdUpdateRequest,
    current_user: User = Depends(require_admin),
    service: SystemOpsService = Depends(_get_service),
) -> JSONResponse:
    try:
        result = await service.update_threshold(body.threshold_usd)
    except ValueError as exc:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=_err("INVALID_THRESHOLD", str(exc)),
        )
    return JSONResponse(status_code=status.HTTP_200_OK, content=_ok(result))


# ── Company Universe ───────────────────────────────────────────────────────────

@system_ops_router.get("/companies", summary="List tracked companies (paginated)")
async def list_companies(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_user: User = Depends(require_admin),
    service: SystemOpsService = Depends(_get_service),
) -> JSONResponse:
    result = await service.list_companies(page=page, page_size=page_size)
    return JSONResponse(status_code=status.HTTP_200_OK, content=_ok(result))


@system_ops_router.get("/companies/search", summary="Search companies by name or ticker")
async def search_companies(
    q: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(require_admin),
    service: SystemOpsService = Depends(_get_service),
) -> JSONResponse:
    results = await service.search_companies(query=q, limit=limit)
    return JSONResponse(status_code=status.HTTP_200_OK, content=_ok(results))


@system_ops_router.post(
    "/companies/{company_id}/track",
    summary="Mark a company as tracked",
)
async def track_company(
    company_id: uuid.UUID,
    current_user: User = Depends(require_admin),
    service: SystemOpsService = Depends(_get_service),
) -> JSONResponse:
    result = await service.set_tracked(company_id, is_tracked=True)
    if result is None:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=_err("NOT_FOUND", f"Company {company_id} not found"),
        )
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=_ok({"company_id": str(company_id), "is_tracked": result["is_tracked"]}),
    )


@system_ops_router.delete(
    "/companies/{company_id}/track",
    summary="Untrack a company",
)
async def untrack_company(
    company_id: uuid.UUID,
    current_user: User = Depends(require_admin),
    service: SystemOpsService = Depends(_get_service),
) -> JSONResponse:
    result = await service.set_tracked(company_id, is_tracked=False)
    if result is None:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=_err("NOT_FOUND", f"Company {company_id} not found"),
        )
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=_ok({"company_id": str(company_id), "is_tracked": result["is_tracked"]}),
    )


# ── Cache Inspection ───────────────────────────────────────────────────────────

@system_ops_router.get("/cache", summary="Get Redis cache statistics")
async def get_cache_stats(
    current_user: User = Depends(require_admin),
    service: SystemOpsService = Depends(_get_service),
) -> JSONResponse:
    stats = await service.get_cache_stats()
    return JSONResponse(status_code=status.HTTP_200_OK, content=_ok(stats))


@system_ops_router.post("/cache/refresh", summary="Force-refresh cached data")
async def refresh_cache(
    body: CacheRefreshRequest,
    current_user: User = Depends(require_admin),
    service: SystemOpsService = Depends(_get_service),
) -> JSONResponse:
    try:
        result = await service.force_refresh_cache(body.data_type, body.company_id)
    except InvalidDataTypeError as exc:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=_err("INVALID_DATA_TYPE", str(exc)),
        )
    return JSONResponse(status_code=status.HTTP_200_OK, content=_ok(result))


# ── Feature Flags ──────────────────────────────────────────────────────────────

@system_ops_router.get("/flags", summary="List all feature flags for current environment")
async def list_flags(
    current_user: User = Depends(require_admin),
    service: SystemOpsService = Depends(_get_service),
) -> JSONResponse:
    flags = await service.list_flags()
    return JSONResponse(status_code=status.HTTP_200_OK, content=_ok(flags))


@system_ops_router.patch("/flags/{flag_id}", summary="Enable or disable a feature flag")
async def set_flag(
    flag_id: str,
    body: FeatureFlagUpdateRequest,
    current_user: User = Depends(require_admin),
    service: SystemOpsService = Depends(_get_service),
) -> JSONResponse:
    try:
        result = await service.set_flag(flag_id, body.enabled, current_user.user_id)
    except ValueError as exc:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=_err("NOT_FOUND", str(exc)),
        )
    return JSONResponse(status_code=status.HTTP_200_OK, content=_ok(result))
