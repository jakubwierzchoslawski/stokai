"""
markets.registry — MarketRegistry: runtime routing view of source_config
+ market_source_binding.

MarketRegistry is an in-process singleton (managed via FastAPI lifespan) that
holds a dict keyed by (market_id, interface_type, role) -> SourceConfig. It is
the single authoritative answer to the question "which source should I use for
market X and interface Y?".

Design decisions:
  - Only enabled=true sources are included in the routing dict.
  - get_source() returns None (not raises) when no binding or source is disabled.
  - Callers are expected to fall back to role="fallback" then None.
  - refresh() replaces the entire dict atomically; no partial state is visible
    to concurrent coroutines during a refresh.
  - The registry is global; tests replace it via dependency_overrides or
    by creating a new instance with a stub repository.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Protocol

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.storage.models.market_source_binding import MarketSourceBinding
from src.storage.models.source_config import SourceConfig

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

_RoutingKey = tuple[str, str, str]  # (market_id_str, interface_type, role)


class IMarketRegistry(Protocol):
    """Structural typing protocol for MarketRegistry consumers."""

    def get_source(
        self,
        market_id: uuid.UUID,
        interface_type: str,
        role: str = "primary",
    ) -> "SourceConfig | None": ...

    async def refresh(self) -> None: ...


class MarketRegistry:
    """Runtime routing view of source_config + market_source_binding.

    Thread-safety: Python's GIL makes dict replacement atomic at the Python
    level. For async code this is equivalent — no partial dict state is visible.

    Usage::

        registry = MarketRegistry(session_factory)
        await registry.refresh()
        source = registry.get_source(market_id, "PriceProvider")
        if source is None:
            source = registry.get_source(market_id, "PriceProvider", role="fallback")
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._routing: dict[_RoutingKey, SourceConfig] = {}
        self._last_loaded_at: datetime | None = None

    def get_source(
        self,
        market_id: uuid.UUID,
        interface_type: str,
        role: str = "primary",
    ) -> SourceConfig | None:
        """Return the SourceConfig for the given (market_id, interface_type, role).

        Returns None if no enabled binding exists. Never raises.
        """
        key = (str(market_id), interface_type, role)
        return self._routing.get(key)

    async def refresh(self) -> None:
        """Reload the routing dict from DB.

        Queries source_config JOIN market_source_binding WHERE enabled=true.
        Replaces _routing atomically (single assignment).
        """
        async with self._session_factory() as session:
            stmt = (
                select(MarketSourceBinding, SourceConfig)
                .join(
                    SourceConfig,
                    MarketSourceBinding.source_id == SourceConfig.source_id,
                )
                .where(SourceConfig.enabled.is_(True))
            )
            result = await session.execute(stmt)
            rows = result.all()

        new_routing: dict[_RoutingKey, SourceConfig] = {}
        for binding, source in rows:
            key: _RoutingKey = (str(binding.market_id), binding.interface_type, binding.role)
            # Lower priority value = lower priority; higher priority wins.
            # If two sources have the same key (shouldn't happen with composite PK),
            # keep the one with higher priority.
            existing = new_routing.get(key)
            if existing is None or source.priority > existing.priority:
                new_routing[key] = source

        self._routing = new_routing
        self._last_loaded_at = datetime.now(timezone.utc)
        logger.debug(
            "MarketRegistry refreshed: %d routing entries loaded.", len(new_routing)
        )

    @property
    def last_loaded_at(self) -> datetime | None:
        """Timestamp of the last successful refresh (UTC). None if never loaded."""
        return self._last_loaded_at

    @property
    def entry_count(self) -> int:
        """Number of routing entries currently in memory."""
        return len(self._routing)
