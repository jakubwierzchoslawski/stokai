"""
api.routers.watchlist_router — FastAPI router for watchlist endpoints.

Endpoints:
  POST   /api/v1/watchlist               — add company to watchlist
  GET    /api/v1/watchlist               — list watchlist items
  DELETE /api/v1/watchlist/{company_id}  — remove from watchlist

Security: JWT auth required on all endpoints (get_current_user).
tenant_id: extracted from JWT claims only — never from request body.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status

from src.api.auth_deps import CurrentUser, get_current_user
from src.api.middleware.rate_limit import portfolio_write_limit
from src.api.schemas.portfolio_schemas import AddWatchlistRequest, WatchlistItemDTO
from src.portfolio.exceptions import NotFoundError
from src.portfolio.watchlist_service import WatchlistService

watchlist_router = APIRouter(prefix="/watchlist", tags=["watchlist"])


# ── Helpers ───────────────────────────────────────────────────────────────────


def _success(data, meta: dict | None = None) -> dict:
    return {"data": data, "meta": meta or {}, "error": None}


def _error(code: str, message: str) -> dict:
    return {"data": None, "error": {"code": code, "message": message}}


# ── Dependency (overridden in tests) ──────────────────────────────────────────


async def _get_watchlist_service() -> WatchlistService:
    """Build a WatchlistService. Overridden in tests via dependency_overrides."""
    raise NotImplementedError(
        "_get_watchlist_service must be overridden in the composition root or tests."
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────


@watchlist_router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Add a company to the watchlist",
)
@portfolio_write_limit
async def add_to_watchlist(
    request: Request,
    body: AddWatchlistRequest,
    current_user: CurrentUser = Depends(get_current_user),
    svc: WatchlistService = Depends(_get_watchlist_service),
) -> dict:
    """Add a company to the authenticated user's watchlist (idempotent)."""
    item = await svc.add_to_watchlist(
        tenant_id=current_user.tenant_id,
        user_id=current_user.user_id,
        company_id=body.company_id,
        ticker=body.ticker,
    )
    return _success(WatchlistItemDTO.model_validate(item).model_dump())


@watchlist_router.get(
    "",
    status_code=status.HTTP_200_OK,
    summary="List watchlist items for the current user",
)
async def list_watchlist(
    current_user: CurrentUser = Depends(get_current_user),
    svc: WatchlistService = Depends(_get_watchlist_service),
) -> dict:
    items = await svc.list_watchlist(
        tenant_id=current_user.tenant_id,
        user_id=current_user.user_id,
    )
    return _success([WatchlistItemDTO.model_validate(i).model_dump() for i in items])


@watchlist_router.delete(
    "/{company_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Remove a company from the watchlist",
)
@portfolio_write_limit
async def remove_from_watchlist(
    request: Request,
    company_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    svc: WatchlistService = Depends(_get_watchlist_service),
):
    await svc.remove_from_watchlist(
        tenant_id=current_user.tenant_id,
        user_id=current_user.user_id,
        company_id=company_id,
    )
