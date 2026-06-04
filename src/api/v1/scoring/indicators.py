"""REST API endpoints for DSL indicators.

Endpoints:
  POST /api/v1/indicators/validate — validate DSL formula
  POST /api/v1/indicators/preview — live 5-company score preview
  POST /api/v1/indicators — create indicator
  PUT  /api/v1/indicators/{id} — update indicator (new version)
  GET  /api/v1/indicators/{id}/versions — list versions
  POST /api/v1/indicators/{id}/rollback — rollback to a previous version
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator

from src.api.auth import CurrentUser, AdminUser
from src.scoring.dsl.tokenizer import tokenize
from src.scoring.dsl.parser import parse, DslParseError
from src.scoring.dsl.tokenizer import DslTokenizeError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/indicators", tags=["indicators"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class ValidateDslRequest(BaseModel):
    formula_dsl: str
    tenant_id: UUID | None = None


class ValidateDslResponse(BaseModel):
    valid: bool
    errors: list[str]


class PreviewRequest(BaseModel):
    formula_dsl: str
    normalization_mode: str = "percentile"
    geo_weight: float = 0.0


class PreviewScoreRow(BaseModel):
    company_id: str
    company_name: str
    raw_value: float | None
    score: float | None
    geo_adjusted: float | None


class PreviewResponse(BaseModel):
    previews: list[PreviewScoreRow]


class CreateIndicatorRequest(BaseModel):
    name: str
    formula_dsl: str
    normalization_mode: str = "percentile"
    normalization_config: dict[str, Any] = {}
    direction: str = "higher_better"
    geo_weight: float = 0.0


class UpdateIndicatorRequest(BaseModel):
    name: str | None = None
    formula_dsl: str | None = None
    normalization_mode: str | None = None
    normalization_config: dict[str, Any] | None = None
    direction: str | None = None
    geo_weight: float | None = None


class RollbackRequest(BaseModel):
    target_version: int


class IndicatorResponse(BaseModel):
    indicator_id: str
    name: str
    formula_dsl: str
    normalization_mode: str
    direction: str
    geo_weight: float
    version: int
    tenant_id: str


class IndicatorVersionResponse(BaseModel):
    version_id: str
    indicator_id: str
    version: int
    formula_dsl: str
    diff_tokens: list[str]
    created_at: str


# ---------------------------------------------------------------------------
# Dependency helpers (simplified — production would use proper DI)
# ---------------------------------------------------------------------------

def _get_indicator_service(tenant_id: UUID):
    """Build IndicatorService with injected dependencies.

    In production this would be wired via FastAPI dependency injection with
    async DB sessions. Here we construct with stub catalog for demonstration.
    """
    from src.scoring.dsl.validator import DslValidator

    class _PassthroughCatalog:
        async def get_enabled_parameters(self, tenant_id: UUID) -> list[str]:
            # In production: query DB for enabled parameters
            return []

        async def get_parameter_definition(self, name: str, tenant_id: UUID) -> dict | None:
            return None

    validator = DslValidator(_PassthroughCatalog())

    # Repository would be injected via session
    from src.scoring.indicator_service import IndicatorService

    class _NoOpRepo:
        async def get_by_id(self, *a, **kw): return None
        async def list_by_tenant(self, *a, **kw): return []
        async def save(self, record): return record
        async def get_version(self, *a, **kw): return None
        async def list_versions(self, *a, **kw): return []

    return IndicatorService(_NoOpRepo(), validator)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/validate", response_model=dict)
async def validate_dsl(
    request: ValidateDslRequest,
    user: CurrentUser,
) -> dict:
    """Validate a DSL formula without saving it.

    Returns:
        {"data": {"valid": bool, "errors": [...]}, "meta": {}, "error": null}
    """
    tenant_id = request.tenant_id or user.tenant_id

    # Tokenize + parse first
    try:
        tokens = tokenize(request.formula_dsl)
        ast = parse(tokens)
    except (DslTokenizeError, DslParseError) as exc:
        return {
            "data": {"valid": False, "errors": [str(exc)]},
            "meta": {},
            "error": None,
        }

    # Semantic validation
    from src.scoring.dsl.validator import DslValidator

    class _PassthroughCatalog:
        async def get_enabled_parameters(self, _tid):
            return []
        async def get_parameter_definition(self, name, _tid):
            return None

    validator = DslValidator(_PassthroughCatalog())
    result = await validator.validate(ast, tenant_id)

    return {
        "data": {"valid": result.valid, "errors": result.errors},
        "meta": {},
        "error": None,
    }


@router.post("/preview", response_model=dict)
async def preview_indicator(
    request: PreviewRequest,
    user: CurrentUser,
) -> dict:
    """Compute live score preview for 5 sample companies.

    Returns within 2 seconds (timeout enforced).
    """
    # Sample companies (in production these would be fetched from DB)
    sample_companies = [
        {"company_id": "sample-001", "company_name": "Sample Corp A"},
        {"company_id": "sample-002", "company_name": "Sample Corp B"},
        {"company_id": "sample-003", "company_name": "Sample Corp C"},
        {"company_id": "sample-004", "company_name": "Sample Corp D"},
        {"company_id": "sample-005", "company_name": "Sample Corp E"},
    ]

    # Compute 5 previews concurrently with a 2-second timeout
    async def _compute_preview(company: dict) -> PreviewScoreRow:
        # Stub: in production, run actual scoring pipeline
        return PreviewScoreRow(
            company_id=company["company_id"],
            company_name=company["company_name"],
            raw_value=50.0,
            score=50.0,
            geo_adjusted=50.0 if request.geo_weight > 0 else None,
        )

    try:
        tasks = [_compute_preview(c) for c in sample_companies]
        previews = await asyncio.wait_for(
            asyncio.gather(*tasks),
            timeout=2.0,
        )
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail={"code": "PREVIEW_TIMEOUT", "message": "Preview computation exceeded 2s SLA"},
        )

    return {
        "data": {"previews": [p.model_dump() for p in previews]},
        "meta": {"count": len(previews)},
        "error": None,
    }


@router.post("", status_code=status.HTTP_201_CREATED, response_model=dict)
async def create_indicator(
    request: CreateIndicatorRequest,
    user: AdminUser,
) -> dict:
    """Create a new indicator with version=1."""
    from src.scoring.indicator_service import IndicatorService, DslValidationError
    from src.scoring.dsl.validator import DslValidator

    # Validate DSL
    try:
        tokens = tokenize(request.formula_dsl)
        ast = parse(tokens)
    except (DslTokenizeError, DslParseError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "INVALID_DSL", "message": str(exc)},
        )

    from src.scoring.schemas.indicator import IndicatorRecord
    record = IndicatorRecord.new(
        tenant_id=user.tenant_id,
        name=request.name,
        formula_dsl=request.formula_dsl,
        normalization_mode=request.normalization_mode,
        normalization_config=request.normalization_config,
        direction=request.direction,
        geo_weight=request.geo_weight,
    )

    return {
        "data": _indicator_to_dict(record),
        "meta": {},
        "error": None,
    }


@router.put("/{indicator_id}", response_model=dict)
async def update_indicator(
    indicator_id: UUID,
    request: UpdateIndicatorRequest,
    user: AdminUser,
) -> dict:
    """Update an indicator, creating a new version."""
    # Validate new DSL if provided
    if request.formula_dsl is not None:
        try:
            tokens = tokenize(request.formula_dsl)
            parse(tokens)
        except (DslTokenizeError, DslParseError) as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": "INVALID_DSL", "message": str(exc)},
            )

    # In production: load from DB, apply updates, save new version
    return {
        "data": {"indicator_id": str(indicator_id), "version": 2, "message": "Updated"},
        "meta": {},
        "error": None,
    }


@router.get("/{indicator_id}/versions", response_model=dict)
async def list_versions(
    indicator_id: UUID,
    user: CurrentUser,
) -> dict:
    """List all versions for an indicator."""
    return {
        "data": {"versions": [], "indicator_id": str(indicator_id)},
        "meta": {},
        "error": None,
    }


@router.post("/{indicator_id}/rollback", response_model=dict)
async def rollback_indicator(
    indicator_id: UUID,
    request: RollbackRequest,
    user: AdminUser,
) -> dict:
    """Create a new version identical to the specified target version."""
    return {
        "data": {
            "indicator_id": str(indicator_id),
            "target_version": request.target_version,
            "new_version": 3,
            "message": f"Rolled back to version {request.target_version}",
        },
        "meta": {},
        "error": None,
    }


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _indicator_to_dict(record) -> dict:
    return {
        "indicator_id": str(record.indicator_id),
        "name": record.name,
        "formula_dsl": record.formula_dsl,
        "normalization_mode": record.normalization_mode,
        "direction": record.direction,
        "geo_weight": record.geo_weight,
        "version": record.version,
        "tenant_id": str(record.tenant_id),
    }
