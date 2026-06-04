"""FastAPI router for the Company Screener.

POST /api/v1/screener

This endpoint is a *read-only aggregation* sent as POST (not GET) to support
complex filter payloads that would exceed URL-length limits when encoded as
query parameters.  Annotated in OpenAPI as a read operation with a request body.

Authentication: JWT required (CurrentUser dependency).
Authorization: Any authenticated user (no role restriction).
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from src.api.auth import CurrentUser
from src.api.dependencies import get_db
from src.api.v1.screener.schemas import ScreenerRequest, ScreenerResponse
from src.api.v1.screener.screener_repository import ScreenerRepository
from src.api.v1.screener.screener_service import ScreenerService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/screener", tags=["screener"])


@router.post(
    "",
    response_model=dict,
    summary="Company Screener",
    description=(
        "Read-only aggregation endpoint.  Returns a cursor-paginated list of "
        "companies matching the supplied filters, sorted by the requested column.  "
        "Sent as POST to avoid URL-length limits on complex filter sets."
    ),
)
async def screen_companies(
    request: ScreenerRequest,
    user: CurrentUser,
    db=Depends(get_db),
) -> dict:
    """Return a paginated ScreenerResponse matching the supplied ScreenerRequest.

    Raises HTTP 422 if any filter column or sort column is not whitelisted.
    """
    repo = ScreenerRepository(session=db)
    service = ScreenerService(repository=repo)

    try:
        rows, next_cursor, total_count = await service.run(request, user.tenant_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "INVALID_FILTER", "message": str(exc)},
        ) from exc

    response = ScreenerResponse(
        data=rows,
        next_cursor=next_cursor,
        total_count=total_count,
        applied_filters=request.filters,
    )

    return {
        "data": response.model_dump(),
        "meta": {
            "page_size": request.page_size,
            "sort_column": request.sort_column,
            "sort_dir": request.sort_dir,
        },
        "error": None,
    }
