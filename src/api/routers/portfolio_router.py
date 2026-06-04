"""
api.routers.portfolio_router — FastAPI router for portfolio and position endpoints.

Endpoints:
  POST   /api/v1/portfolios                                  — create portfolio
  GET    /api/v1/portfolios                                  — list portfolios
  GET    /api/v1/portfolios/{portfolio_id}                   — get portfolio
  DELETE /api/v1/portfolios/{portfolio_id}                   — delete portfolio
  POST   /api/v1/portfolios/{portfolio_id}/positions         — add position
  GET    /api/v1/portfolios/{portfolio_id}/positions         — list positions
  DELETE /api/v1/portfolios/{portfolio_id}/positions/{position_id} — delete position
  POST   /api/v1/portfolios/import                           — CSV import (multipart)

Security: JWT auth required on all endpoints (get_current_user).
Rate limiting: write endpoints via portfolio_write_limit.
tenant_id: extracted from JWT claims only — never from request body.
"""
from __future__ import annotations

import uuid
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.api.auth_deps import CurrentUser, get_current_user
from src.api.middleware.rate_limit import portfolio_write_limit
from src.api.schemas.portfolio_schemas import (
    AddPositionRequest,
    CreatePortfolioRequest,
    PortfolioDTO,
    PositionDTO,
)
from src.portfolio.csv_import_service import CsvImportResult, CsvImportService
from src.portfolio.exceptions import NotFoundError, ValidationError
from src.portfolio.portfolio_service import PortfolioService
from src.storage.portfolio_repository import PortfolioRepository
from src.storage.position_repository import PositionRepository
from src.config.settings import get_settings

portfolio_router = APIRouter(prefix="/portfolios", tags=["portfolios"])

MAX_CSV_BYTES = 1 * 1024 * 1024  # 1 MB


# ── Helpers ───────────────────────────────────────────────────────────────────


def _success(data, meta: dict | None = None) -> dict:
    return {"data": data, "meta": meta or {}, "error": None}


def _error(code: str, message: str) -> dict:
    return {"data": None, "error": {"code": code, "message": message}}


def _get_engine():
    settings = get_settings()
    return create_async_engine(settings.DATABASE_URL, echo=False)


async def _get_portfolio_service() -> PortfolioService:
    """Build a PortfolioService with real repositories.

    In tests this dependency is overridden via app.dependency_overrides.
    """
    raise NotImplementedError(
        "_get_portfolio_service must be overridden in the composition root or tests."
    )


async def _get_csv_import_service() -> CsvImportService:
    """Build a CsvImportService with real repositories.

    In tests this dependency is overridden via app.dependency_overrides.
    """
    raise NotImplementedError(
        "_get_csv_import_service must be overridden in the composition root or tests."
    )


# ── Portfolio endpoints ────────────────────────────────────────────────────────


@portfolio_router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Create a new portfolio",
)
@portfolio_write_limit
async def create_portfolio(
    request: Request,
    body: CreatePortfolioRequest,
    current_user: CurrentUser = Depends(get_current_user),
    svc: PortfolioService = Depends(_get_portfolio_service),
) -> dict:
    """Create a portfolio for the authenticated user."""
    portfolio = await svc.create_portfolio(
        tenant_id=current_user.tenant_id,
        user_id=current_user.user_id,
        name=body.name,
    )
    return _success(PortfolioDTO.model_validate(portfolio).model_dump())


@portfolio_router.get(
    "",
    status_code=status.HTTP_200_OK,
    summary="List portfolios for the current user",
)
async def list_portfolios(
    current_user: CurrentUser = Depends(get_current_user),
    svc: PortfolioService = Depends(_get_portfolio_service),
) -> dict:
    portfolios = await svc.list_portfolios(
        tenant_id=current_user.tenant_id,
        user_id=current_user.user_id,
    )
    return _success([PortfolioDTO.model_validate(p).model_dump() for p in portfolios])


@portfolio_router.get(
    "/{portfolio_id}",
    status_code=status.HTTP_200_OK,
    summary="Get a single portfolio",
)
async def get_portfolio(
    portfolio_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    svc: PortfolioService = Depends(_get_portfolio_service),
) -> dict:
    try:
        portfolio = await svc.get_portfolio(current_user.tenant_id, portfolio_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=_error("NOT_FOUND", str(exc)))
    return _success(PortfolioDTO.model_validate(portfolio).model_dump())


@portfolio_router.delete(
    "/{portfolio_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a portfolio",
)
@portfolio_write_limit
async def delete_portfolio(
    request: Request,
    portfolio_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    svc: PortfolioService = Depends(_get_portfolio_service),
):
    try:
        await svc.delete_portfolio(current_user.tenant_id, portfolio_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=_error("NOT_FOUND", str(exc)))


# ── Position endpoints ─────────────────────────────────────────────────────────


@portfolio_router.post(
    "/{portfolio_id}/positions",
    status_code=status.HTTP_201_CREATED,
    summary="Add a position to a portfolio",
)
@portfolio_write_limit
async def add_position(
    request: Request,
    portfolio_id: UUID,
    body: AddPositionRequest,
    current_user: CurrentUser = Depends(get_current_user),
    svc: PortfolioService = Depends(_get_portfolio_service),
) -> dict:
    try:
        position = await svc.add_position(
            tenant_id=current_user.tenant_id,
            portfolio_id=portfolio_id,
            ticker=body.ticker,
            shares=body.shares,
            source=body.source,
            cost_basis=body.cost_basis,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=_error("NOT_FOUND", str(exc)))
    return _success(PositionDTO.model_validate(position).model_dump())


@portfolio_router.get(
    "/{portfolio_id}/positions",
    status_code=status.HTTP_200_OK,
    summary="List positions in a portfolio",
)
async def list_positions(
    portfolio_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    svc: PortfolioService = Depends(_get_portfolio_service),
) -> dict:
    try:
        await svc.get_portfolio(current_user.tenant_id, portfolio_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=_error("NOT_FOUND", str(exc)))
    from src.storage.position_repository import PositionRepository
    # Positions are returned via the service
    # Re-use the position_repo from the service's injected repo
    # For simplicity, call through service position list
    positions = await svc._position_repo.list_by_portfolio(current_user.tenant_id, portfolio_id)
    return _success([PositionDTO.model_validate(p).model_dump() for p in positions])


@portfolio_router.delete(
    "/{portfolio_id}/positions/{position_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a position",
)
@portfolio_write_limit
async def delete_position(
    request: Request,
    portfolio_id: UUID,
    position_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    svc: PortfolioService = Depends(_get_portfolio_service),
):
    try:
        await svc.delete_position(current_user.tenant_id, position_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=_error("NOT_FOUND", str(exc)))


# ── CSV import endpoint ────────────────────────────────────────────────────────


@portfolio_router.post(
    "/import",
    status_code=status.HTTP_200_OK,
    summary="Import positions from CSV file",
)
@portfolio_write_limit
async def csv_import(
    request: Request,
    portfolio_id: UUID,
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(get_current_user),
    svc: CsvImportService = Depends(_get_csv_import_service),
) -> dict:
    """Import positions from a CSV file (multipart/form-data).

    Max file size: 1 MB.
    Returns 200 with CsvImportResult — partial errors are included in the response body.
    """
    # Check file size
    content = await file.read()
    if len(content) > MAX_CSV_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=_error("FILE_TOO_LARGE", "CSV file must be 1 MB or smaller"),
        )

    try:
        result = await svc.import_csv(
            tenant_id=current_user.tenant_id,
            portfolio_id=portfolio_id,
            csv_bytes=content,
        )
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=_error("VALIDATION_ERROR", str(exc)),
        )

    return _success(result.model_dump())
