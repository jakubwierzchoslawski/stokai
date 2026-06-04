"""
api.v1.watchlist_scan_router — Watchlist scan brief endpoints.

GET /api/v1/briefs/watchlist   — return most recent watchlist_scan brief for tenant.

JWT authentication required (CurrentUser dependency).
Tenant-scoped: all queries include tenant_id for IDOR prevention (REQ-N-006).

PLAN-F-008 TASK-008
"""
from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from src.api.auth_deps import CurrentUser, get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/briefs", tags=["watchlist-scan"])


async def _get_latest_watchlist_brief(tenant_id: UUID) -> dict | None:
    """Fetch the most recent watchlist_scan brief for a tenant.

    Production: queries the brief table with type='watchlist_scan' and
    tenant_id filter, ordered by created_at DESC.

    Returns:
        Dict representation of the brief, or None if not found.
    """
    try:
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
        from src.config.settings import get_settings

        settings = get_settings()
        engine = create_async_engine(settings.DATABASE_URL, echo=False)
        factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

        async with factory() as session:
            stmt = text(
                """
                SELECT brief_id, type, tenant_id, content, confidence, cost_usd,
                       cost_limited, hil_reviewed, hil_approved, created_at
                FROM brief
                WHERE type = 'watchlist_scan'
                  AND tenant_id = :tenant_id
                ORDER BY created_at DESC
                LIMIT 1
                """
            )
            result = await session.execute(stmt, {"tenant_id": str(tenant_id)})
            row = result.mappings().first()

        await engine.dispose()

        if row is None:
            return None

        return dict(row)

    except Exception:
        logger.exception(
            "Failed to fetch watchlist brief for tenant_id=%s", tenant_id
        )
        return None


@router.get("/watchlist")
async def get_watchlist_brief(
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Return the most recent watchlist_scan brief for the authenticated tenant.

    Returns:
        JSON response with data containing the brief, or 404 if none found.

    Raises:
        HTTPException 404: No watchlist scan brief found for this tenant.
        HTTPException 401: Missing or invalid JWT.
    """
    tenant_id: UUID = current_user.tenant_id

    brief = await _get_latest_watchlist_brief(tenant_id=tenant_id)

    if brief is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "WATCHLIST_BRIEF_NOT_FOUND",
                "message": "No watchlist scan brief found for this tenant.",
            },
        )

    logger.info(
        "get_watchlist_brief: returning brief_id=%s for tenant=%s",
        brief.get("brief_id"),
        tenant_id,
    )

    return {
        "data": {
            "brief_id": str(brief.get("brief_id", "")),
            "type": brief.get("type", "watchlist_scan"),
            "content": brief.get("content", {}),
            "confidence": brief.get("confidence", 0.0),
            "cost_usd": brief.get("cost_usd", 0.0),
            "hil_reviewed": brief.get("hil_reviewed", False),
            "created_at": str(brief.get("created_at", "")),
        },
        "meta": {},
        "error": None,
    }
