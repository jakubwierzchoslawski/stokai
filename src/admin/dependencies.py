"""
admin.dependencies — FastAPI dependency functions for the admin sources router.

Provides:
  - get_admin_source_service(): builds AdminSourceService with all required
    collaborators wired via constructor injection.
  - require_admin: re-exported from api.auth.dependencies for convenience.

The registry and health_counter are app-scoped singletons accessed from
app.state (set during FastAPI lifespan startup).
"""
from __future__ import annotations

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

# Re-export require_admin for use in the admin router
from src.api.auth.dependencies import get_db, require_admin
from src.admin.health.counter import HealthCounter
from src.admin.service import AdminSourceService
from src.markets.registry import MarketRegistry
from src.storage.repositories.market_source_binding_repo import PostgresBindingRepository
from src.storage.repositories.source_config_repo import PostgresSourceConfigRepository


def get_registry(request: Request) -> MarketRegistry:
    """Extract the MarketRegistry singleton from app.state."""
    return request.app.state.market_registry


def get_health_counter(request: Request) -> HealthCounter:
    """Extract the HealthCounter singleton from app.state."""
    return request.app.state.health_counter


async def get_admin_source_service(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> AdminSourceService:
    """Build an AdminSourceService with all collaborators injected."""
    source_repo = PostgresSourceConfigRepository(db)
    binding_repo = PostgresBindingRepository(db)
    registry: MarketRegistry = get_registry(request)
    health_counter: HealthCounter = get_health_counter(request)
    return AdminSourceService(
        source_repo=source_repo,
        binding_repo=binding_repo,
        registry=registry,
        health_counter=health_counter,
    )


__all__ = ["get_admin_source_service", "require_admin"]
