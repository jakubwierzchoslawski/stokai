"""
Unit tests for MarketRegistry and RegistryRefresher (TASK-003).

Uses in-memory SQLite via aiosqlite + SQLAlchemy 2.0 async.

Tests cover:
  - After refresh(), get_source() returns primary source for known binding.
  - Disabled source is absent from registry after refresh().
  - set_enabled(False) then refresh() removes source; get_source() returns fallback.
  - RegistryRefresher calls refresh() when updated_at advances.
  - RegistryRefresher does NOT call refresh() when nothing has changed (idempotency).
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.storage.models.user import Base
from src.storage.models.source_config import SourceConfig
from src.storage.models.market_source_binding import MarketSourceBinding
from src.markets.registry import MarketRegistry
from src.markets.registry_refresher import RegistryRefresher
from src.storage.repositories.source_config_repo import PostgresSourceConfigRepository
from src.storage.repositories.market_source_binding_repo import PostgresBindingRepository


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture()
async def engine():
    eng = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with eng.begin() as conn:
        await conn.execute(text("PRAGMA foreign_keys=ON"))
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await eng.dispose()


@pytest_asyncio.fixture()
def session_factory(engine):
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


@pytest_asyncio.fixture()
async def registry(session_factory):
    reg = MarketRegistry(session_factory)
    return reg


class _CreateDTO:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


async def _seed_source(session_factory, enabled: bool = True) -> SourceConfig:
    async with session_factory() as session:
        repo = PostgresSourceConfigRepository(session)
        source = await repo.create(
            _CreateDTO(
                interface_type="PriceProvider",
                display_name="Test Source",
                credentials_ref="env:TEST_KEY",
                config={},
                cost_tier="free",
                priority=0,
            )
        )
        if enabled:
            source = await repo.set_enabled(source.source_id, True)
        await session.commit()
    return source


async def _seed_binding(session_factory, market_id, source_id, role="primary"):
    async with session_factory() as session:
        repo = PostgresBindingRepository(session)
        binding = await repo.upsert(market_id, "PriceProvider", source_id, role)
        await session.commit()
    return binding


# ── MarketRegistry tests ──────────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.asyncio
async def test_refresh_loads_primary_source(registry, session_factory):
    """After refresh(), get_source() returns the primary source for a known binding."""
    market_id = uuid.uuid4()
    source = await _seed_source(session_factory, enabled=True)
    await _seed_binding(session_factory, market_id, source.source_id, role="primary")

    await registry.refresh()
    result = registry.get_source(market_id, "PriceProvider", role="primary")
    assert result is not None
    assert result.source_id == source.source_id


@pytest.mark.unit
@pytest.mark.asyncio
async def test_disabled_source_absent_after_refresh(registry, session_factory):
    """Disabled source must not appear in the registry routing dict."""
    market_id = uuid.uuid4()
    source = await _seed_source(session_factory, enabled=False)
    await _seed_binding(session_factory, market_id, source.source_id, role="primary")

    await registry.refresh()
    result = registry.get_source(market_id, "PriceProvider", role="primary")
    assert result is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_disable_then_refresh_removes_from_registry(registry, session_factory):
    """Disabling a source and refreshing removes it; fallback returned instead."""
    market_id = uuid.uuid4()
    # Create primary source (enabled) and fallback source (enabled)
    primary_src = await _seed_source(session_factory, enabled=True)
    fallback_src = await _seed_source(session_factory, enabled=True)

    await _seed_binding(session_factory, market_id, primary_src.source_id, role="primary")
    await _seed_binding(session_factory, market_id, fallback_src.source_id, role="fallback")

    # Initial refresh — both visible
    await registry.refresh()
    assert registry.get_source(market_id, "PriceProvider", "primary") is not None
    assert registry.get_source(market_id, "PriceProvider", "fallback") is not None

    # Disable primary source
    async with session_factory() as session:
        repo = PostgresSourceConfigRepository(session)
        await repo.set_enabled(primary_src.source_id, False)
        await session.commit()

    # Refresh — primary gone, fallback still present
    await registry.refresh()
    assert registry.get_source(market_id, "PriceProvider", "primary") is None
    fallback_result = registry.get_source(market_id, "PriceProvider", "fallback")
    assert fallback_result is not None
    assert fallback_result.source_id == fallback_src.source_id


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_source_returns_none_for_unknown_market(registry, session_factory):
    """get_source() returns None (not raises) for unknown binding."""
    await registry.refresh()
    result = registry.get_source(uuid.uuid4(), "PriceProvider")
    assert result is None


# ── RegistryRefresher tests ───────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.asyncio
async def test_refresher_calls_refresh_when_updated_at_advances(session_factory):
    """RegistryRefresher calls registry.refresh() when updated_at is newer."""
    registry = MarketRegistry(session_factory)
    source = await _seed_source(session_factory, enabled=True)

    # Record initial state
    await registry.refresh()
    original_loaded_at = registry.last_loaded_at

    # Simulate a small delay and update a source
    await asyncio.sleep(0.01)
    async with session_factory() as session:
        repo = PostgresSourceConfigRepository(session)
        await repo.set_enabled(source.source_id, False)  # touches updated_at
        await session.commit()

    refresher = RegistryRefresher(registry, session_factory, interval_seconds=0.01)
    # Single tick
    await refresher._tick()

    assert registry.last_loaded_at is not None
    assert registry.last_loaded_at > original_loaded_at  # type: ignore[operator]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_refresher_does_not_refresh_when_nothing_changed(session_factory):
    """RegistryRefresher is idempotent — no extra refresh() call if nothing changed."""
    registry = MarketRegistry(session_factory)
    await _seed_source(session_factory, enabled=True)
    await registry.refresh()

    original_loaded_at = registry.last_loaded_at

    # Mock refresh to count calls
    call_count = 0
    original_refresh = registry.refresh

    async def counting_refresh():
        nonlocal call_count
        call_count += 1
        await original_refresh()

    registry.refresh = counting_refresh  # type: ignore[method-assign]

    refresher = RegistryRefresher(registry, session_factory, interval_seconds=0.01)
    # Nothing changed — tick should NOT call refresh
    await refresher._tick()
    assert call_count == 0
