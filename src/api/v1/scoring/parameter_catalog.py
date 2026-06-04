"""Admin REST API endpoints for DSL parameter catalog.

All endpoints are admin-only. Located under /api/v1/admin/scoring/parameters.

Endpoints:
  GET    /api/v1/admin/scoring/parameters — list all
  POST   /api/v1/admin/scoring/parameters — add
  PATCH  /api/v1/admin/scoring/parameters/{name}/enable
  PATCH  /api/v1/admin/scoring/parameters/{name}/disable
"""
from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from src.api.auth import AdminUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/scoring/parameters", tags=["parameter-catalog"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class AddParameterRequest(BaseModel):
    name: str
    description: str | None = None
    source_field: str | None = None


class ParameterResponse(BaseModel):
    parameter_id: str
    name: str
    description: str | None
    source_field: str | None
    enabled: bool
    tenant_id: str


# ---------------------------------------------------------------------------
# Endpoints (admin-only)
# ---------------------------------------------------------------------------

@router.get("", response_model=dict)
async def list_parameters(user: AdminUser) -> dict:
    """List all parameters in the catalog for the current tenant."""
    # In production: inject ParameterCatalogRepository via DB session
    return {
        "data": {"parameters": []},
        "meta": {"tenant_id": str(user.tenant_id)},
        "error": None,
    }


@router.post("", status_code=status.HTTP_201_CREATED, response_model=dict)
async def add_parameter(
    request: AddParameterRequest,
    user: AdminUser,
) -> dict:
    """Add a new parameter to the catalog."""
    from uuid import uuid4
    from datetime import datetime

    param = {
        "parameter_id": str(uuid4()),
        "name": request.name,
        "description": request.description,
        "source_field": request.source_field,
        "enabled": True,
        "tenant_id": str(user.tenant_id),
        "created_at": datetime.utcnow().isoformat(),
    }
    return {
        "data": param,
        "meta": {},
        "error": None,
    }


@router.patch("/{name}/enable", response_model=dict)
async def enable_parameter(
    name: str,
    user: AdminUser,
) -> dict:
    """Enable a parameter in the catalog."""
    return {
        "data": {"name": name, "enabled": True},
        "meta": {},
        "error": None,
    }


@router.patch("/{name}/disable", response_model=dict)
async def disable_parameter(
    name: str,
    user: AdminUser,
) -> dict:
    """Disable a parameter in the catalog."""
    return {
        "data": {"name": name, "enabled": False},
        "meta": {},
        "error": None,
    }
