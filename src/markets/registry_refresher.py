"""
markets.registry_refresher — RegistryRefresher: background asyncio task that
polls for source_config changes and calls registry.refresh() when needed.

Polling interval: 30 seconds.
Change detection: queries MAX(updated_at) from source_config and compares with
registry.last_loaded_at. If any row is newer, triggers a full refresh.

Idempotency: if nothing has changed, refresh() is NOT called (zero DB writes,
minimal reads).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.markets.registry import MarketRegistry
from src.storage.models.source_config import SourceConfig

logger = logging.getLogger(__name__)

_DEFAULT_INTERVAL_SECONDS = 30


class RegistryRefresher:
    """Asyncio background task that keeps MarketRegistry up-to-date.

    Start via ``asyncio.create_task(refresher.run())``.
    Stop by calling ``refresher.stop()`` or cancelling the task.

    Design decisions:
      - Polls MAX(source_config.updated_at) only — single lightweight query.
      - Calls registry.refresh() only when the max timestamp has advanced.
      - A separate check for market_source_binding changes is unnecessary because
        set_enabled() always touches source_config.updated_at, and binding upserts
        trigger a synchronous refresh() in the admin service layer.
    """

    def __init__(
        self,
        registry: MarketRegistry,
        session_factory: async_sessionmaker[AsyncSession],
        interval_seconds: float = _DEFAULT_INTERVAL_SECONDS,
    ) -> None:
        self._registry = registry
        self._session_factory = session_factory
        self._interval = interval_seconds
        self._running = False

    async def run(self) -> None:
        """Run the polling loop until stop() is called or the task is cancelled."""
        self._running = True
        logger.info(
            "RegistryRefresher started (interval=%ss).", self._interval
        )
        while self._running:
            try:
                await self._tick()
            except Exception:  # noqa: BLE001
                logger.exception("RegistryRefresher tick failed — will retry.")
            await asyncio.sleep(self._interval)

    def stop(self) -> None:
        """Signal the run loop to exit after the current sleep completes."""
        self._running = False

    async def _tick(self) -> None:
        """Single poll: check if any source_config row is newer than last_loaded_at."""
        max_updated_at = await self._get_max_updated_at()
        if max_updated_at is None:
            # No rows in source_config — nothing to refresh.
            return

        last_loaded = self._registry.last_loaded_at
        if last_loaded is None or max_updated_at > last_loaded:
            logger.debug(
                "RegistryRefresher: detected change (max_updated_at=%s, "
                "last_loaded_at=%s) — refreshing.",
                max_updated_at,
                last_loaded,
            )
            await self._registry.refresh()
        # else: nothing changed, idempotent — do not call refresh()

    async def _get_max_updated_at(self) -> datetime | None:
        """Query MAX(updated_at) from source_config. Returns None if table is empty."""
        async with self._session_factory() as session:
            stmt = select(func.max(SourceConfig.updated_at))
            result = await session.execute(stmt)
            value = result.scalar_one_or_none()
        if value is None:
            return None
        # Ensure timezone-aware
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value
