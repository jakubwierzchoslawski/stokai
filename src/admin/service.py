"""
admin.service — AdminSourceService: orchestrates source_config + market_source_binding
operations and triggers registry refresh.

This is the business-logic layer (Layer 2 in the Controller→Service→Repository stack).
All DB side-effects are delegated to repositories; no SQLAlchemy usage lives here.

After any mutation that affects routing (set_enabled, upsert_binding), the service
calls registry.refresh() synchronously so the routing dict is fresh before the
HTTP response is returned.
"""
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from src.admin.health.counter import HealthCounter
from src.admin.schemas import (
    BindingDeleteRequest,
    BindingUpsertRequest,
    SourceConfigCreate,
    SourceConfigUpdate,
)
from src.storage.models.market_source_binding import MarketSourceBinding
from src.storage.models.source_config import SourceConfig
from src.storage.repositories.market_source_binding_repo import IBindingRepository
from src.storage.repositories.source_config_repo import ISourceConfigRepository

if TYPE_CHECKING:
    from src.markets.registry import MarketRegistry


class AdminSourceService:
    """Business-logic service for admin data-source management.

    Constructor-injected dependencies (DIP):
        source_repo   — ISourceConfigRepository
        binding_repo  — IBindingRepository
        registry      — MarketRegistry
        health_counter — HealthCounter
    """

    def __init__(
        self,
        source_repo: ISourceConfigRepository,
        binding_repo: IBindingRepository,
        registry: "MarketRegistry",
        health_counter: HealthCounter,
    ) -> None:
        self._source_repo = source_repo
        self._binding_repo = binding_repo
        self._registry = registry
        self._health_counter = health_counter

    # ── Source operations ──────────────────────────────────────────────────────

    async def list_sources(self) -> list[SourceConfig]:
        """Return all source_config rows (including disabled)."""
        return await self._source_repo.list_all()

    async def get_source(self, source_id: uuid.UUID) -> SourceConfig | None:
        return await self._source_repo.get_by_id(source_id)

    async def create_source(self, data: SourceConfigCreate) -> SourceConfig:
        """Create a new source (enabled=False). Does NOT trigger registry refresh."""
        return await self._source_repo.create(data)

    async def set_enabled(self, source_id: uuid.UUID, enabled: bool) -> SourceConfig:
        """Toggle a source's enabled flag and refresh the registry synchronously.

        After this call returns, the registry routing dict reflects the change.
        Satisfies AC-001 (immediate routing update) and AC-004 (<60s without restart).
        """
        updated = await self._source_repo.set_enabled(source_id, enabled)
        # Synchronous refresh — routing is fresh before HTTP response is sent
        await self._registry.refresh()
        return updated

    async def update_source(
        self, source_id: uuid.UUID, data: SourceConfigUpdate
    ) -> SourceConfig:
        return await self._source_repo.update(source_id, data)

    # ── Binding operations ─────────────────────────────────────────────────────

    async def list_bindings(self) -> list[MarketSourceBinding]:
        return await self._binding_repo.list_all()

    async def upsert_binding(self, data: BindingUpsertRequest) -> MarketSourceBinding:
        """Create or update a market-to-source binding; refresh registry."""
        binding = await self._binding_repo.upsert(
            market_id=data.market_id,
            interface_type=data.interface_type,
            source_id=data.source_id,
            role=data.role,
        )
        await self._registry.refresh()
        return binding

    async def delete_binding(self, data: BindingDeleteRequest) -> None:
        """Remove a binding; refresh registry."""
        await self._binding_repo.delete(
            market_id=data.market_id,
            interface_type=data.interface_type,
            source_id=data.source_id,
        )
        await self._registry.refresh()

    # ── Health operations ──────────────────────────────────────────────────────

    async def get_source_health(self, source_id: uuid.UUID, cost_tier: str = "free"):
        """Return today's health stats for a source."""
        return await self._health_counter.get_stats(str(source_id), cost_tier)
