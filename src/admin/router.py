"""
admin.router — FastAPI router for the admin data-source management plane.

All endpoints require role=admin (enforced via require_admin dependency).
Credentials are never returned in responses (credentials_ref is write-only).

Endpoints:
  GET    /api/v1/admin/sources                      — list all sources + health
  POST   /api/v1/admin/sources                      — create new source (enabled=False)
  GET    /api/v1/admin/sources/{source_id}          — get single source + health
  PATCH  /api/v1/admin/sources/{source_id}/enable   — toggle enable/disable
  GET    /api/v1/admin/sources/{source_id}/health   — health stats only
  GET    /api/v1/admin/bindings                     — list all bindings
  PUT    /api/v1/admin/bindings                     — upsert binding
  DELETE /api/v1/admin/bindings                     — delete binding

Registered on the FastAPI app with prefix /api/v1/admin.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse

from src.admin.dependencies import get_admin_source_service, require_admin
from src.admin.schemas import (
    BindingDeleteRequest,
    BindingResponse,
    BindingUpsertRequest,
    EnableToggleRequest,
    HealthStatsResponse,
    SourceConfigCreate,
    SourceConfigResponse,
    SourceConfigUpdate,
)
from src.admin.service import AdminSourceService
from src.storage.models.user import User

admin_router = APIRouter(prefix="/admin", tags=["admin"])


# ── Response envelope helpers ──────────────────────────────────────────────────

def _ok(data) -> dict:
    return {"data": data, "meta": {}, "error": None}


def _err(code: str, message: str) -> dict:
    return {"data": None, "error": {"code": code, "message": message}}


# ── Sources ────────────────────────────────────────────────────────────────────

@admin_router.get("/sources", summary="List all data sources")
async def list_sources(
    current_user: User = Depends(require_admin),
    service: AdminSourceService = Depends(get_admin_source_service),
) -> JSONResponse:
    """Return all source_config rows with today's health stats.

    Requires role=admin (HTTP 403 for other roles).
    credentials_ref is excluded from all responses.
    """
    sources = await service.list_sources()
    result = []
    for src in sources:
        health = await service.get_source_health(src.source_id, src.cost_tier)
        health_resp = HealthStatsResponse(
            calls_today=health.calls_today,
            errors_today=health.errors_today,
            rate_limit_pct_used=health.rate_limit_pct_used,
            estimated_cost_today=health.estimated_cost_today,
        )
        resp = SourceConfigResponse(
            source_id=src.source_id,
            interface_type=src.interface_type,
            display_name=src.display_name,
            enabled=src.enabled,
            config=src.config,
            cost_tier=src.cost_tier,
            priority=src.priority,
            health=health_resp,
        )
        result.append(resp.model_dump())
    return JSONResponse(status_code=status.HTTP_200_OK, content=_ok(result))


@admin_router.post("/sources", status_code=status.HTTP_201_CREATED, summary="Create a new source")
async def create_source(
    body: SourceConfigCreate,
    current_user: User = Depends(require_admin),
    service: AdminSourceService = Depends(get_admin_source_service),
) -> JSONResponse:
    """Create a new data source. The source starts with enabled=False (AC-002)."""
    created = await service.create_source(body)
    resp = SourceConfigResponse(
        source_id=created.source_id,
        interface_type=created.interface_type,
        display_name=created.display_name,
        enabled=created.enabled,
        config=created.config,
        cost_tier=created.cost_tier,
        priority=created.priority,
    )
    return JSONResponse(status_code=status.HTTP_201_CREATED, content=_ok(resp.model_dump()))


@admin_router.get("/sources/{source_id}", summary="Get a single data source")
async def get_source(
    source_id: uuid.UUID,
    current_user: User = Depends(require_admin),
    service: AdminSourceService = Depends(get_admin_source_service),
) -> JSONResponse:
    src = await service.get_source(source_id)
    if src is None:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=_err("NOT_FOUND", f"Source {source_id} not found"),
        )
    health = await service.get_source_health(src.source_id, src.cost_tier)
    health_resp = HealthStatsResponse(
        calls_today=health.calls_today,
        errors_today=health.errors_today,
        rate_limit_pct_used=health.rate_limit_pct_used,
        estimated_cost_today=health.estimated_cost_today,
    )
    resp = SourceConfigResponse(
        source_id=src.source_id,
        interface_type=src.interface_type,
        display_name=src.display_name,
        enabled=src.enabled,
        config=src.config,
        cost_tier=src.cost_tier,
        priority=src.priority,
        health=health_resp,
    )
    return JSONResponse(status_code=status.HTTP_200_OK, content=_ok(resp.model_dump()))


@admin_router.patch("/sources/{source_id}/enable", summary="Enable or disable a source")
async def toggle_enable(
    source_id: uuid.UUID,
    body: EnableToggleRequest,
    current_user: User = Depends(require_admin),
    service: AdminSourceService = Depends(get_admin_source_service),
) -> JSONResponse:
    """Toggle enabled flag and trigger a synchronous registry refresh (AC-001, AC-004)."""
    try:
        updated = await service.set_enabled(source_id, body.enabled)
    except ValueError as exc:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=_err("NOT_FOUND", str(exc)),
        )
    resp = SourceConfigResponse(
        source_id=updated.source_id,
        interface_type=updated.interface_type,
        display_name=updated.display_name,
        enabled=updated.enabled,
        config=updated.config,
        cost_tier=updated.cost_tier,
        priority=updated.priority,
    )
    return JSONResponse(status_code=status.HTTP_200_OK, content=_ok(resp.model_dump()))


@admin_router.get("/sources/{source_id}/health", summary="Health stats for a source")
async def get_source_health(
    source_id: uuid.UUID,
    current_user: User = Depends(require_admin),
    service: AdminSourceService = Depends(get_admin_source_service),
) -> JSONResponse:
    src = await service.get_source(source_id)
    if src is None:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=_err("NOT_FOUND", f"Source {source_id} not found"),
        )
    health = await service.get_source_health(source_id, src.cost_tier)
    resp = HealthStatsResponse(
        calls_today=health.calls_today,
        errors_today=health.errors_today,
        rate_limit_pct_used=health.rate_limit_pct_used,
        estimated_cost_today=health.estimated_cost_today,
    )
    return JSONResponse(status_code=status.HTTP_200_OK, content=_ok(resp.model_dump()))


# ── Bindings ───────────────────────────────────────────────────────────────────

@admin_router.get("/bindings", summary="List all market-source bindings")
async def list_bindings(
    current_user: User = Depends(require_admin),
    service: AdminSourceService = Depends(get_admin_source_service),
) -> JSONResponse:
    bindings = await service.list_bindings()
    result = [
        BindingResponse(
            market_id=b.market_id,
            interface_type=b.interface_type,
            source_id=b.source_id,
            role=b.role,
        ).model_dump()
        for b in bindings
    ]
    return JSONResponse(status_code=status.HTTP_200_OK, content=_ok(result))


@admin_router.put("/bindings", summary="Upsert a market-source binding")
async def upsert_binding(
    body: BindingUpsertRequest,
    current_user: User = Depends(require_admin),
    service: AdminSourceService = Depends(get_admin_source_service),
) -> JSONResponse:
    """Create or update a binding; triggers synchronous registry refresh."""
    binding = await service.upsert_binding(body)
    resp = BindingResponse(
        market_id=binding.market_id,
        interface_type=binding.interface_type,
        source_id=binding.source_id,
        role=binding.role,
    )
    return JSONResponse(status_code=status.HTTP_200_OK, content=_ok(resp.model_dump()))


@admin_router.delete("/bindings", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a binding")
async def delete_binding(
    body: BindingDeleteRequest,
    current_user: User = Depends(require_admin),
    service: AdminSourceService = Depends(get_admin_source_service),
) -> None:
    """Remove a binding and refresh the registry."""
    await service.delete_binding(body)
