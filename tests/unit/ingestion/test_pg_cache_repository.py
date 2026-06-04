"""Unit tests for CacheEntryRepository.

Uses SQLAlchemy with an in-memory SQLite engine (async) to avoid needing
a running PostgreSQL instance. The repository uses generic SQL that works
on both dialects for the get/delete paths.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from ingestion.pg_cache_repository import CacheEntryRepository, cache_entry_table


@pytest_asyncio.fixture
async def async_session():
    """Provide a fresh SQLite in-memory session with the cache_entry table."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(cache_entry_table.metadata.create_all)

    async_session_factory = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with async_session_factory() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_get_returns_none_on_miss(async_session):
    repo = CacheEntryRepository(async_session)
    result = await repo.get("nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_set_and_get_roundtrip(async_session):
    repo = CacheEntryRepository(async_session)
    await repo.set("key1", "price_bar", b"payload", ttl_seconds=900)
    result = await repo.get("key1")
    assert result == b"payload"


@pytest.mark.asyncio
async def test_pg_get_excludes_expired_rows(async_session):
    """Rows past their expires_at must not be returned."""
    now = datetime.now(tz=timezone.utc)
    past = now - timedelta(seconds=1)

    # Insert an already-expired row directly
    stmt = cache_entry_table.insert().values(
        cache_key="expired_key",
        data_type="price_bar",
        value=b"stale",
        fetched_at=now - timedelta(seconds=1000),
        expires_at=past,
    )
    await async_session.execute(stmt)
    await async_session.commit()

    repo = CacheEntryRepository(async_session)
    result = await repo.get("expired_key")
    assert result is None, "Expired rows must not be returned"


@pytest.mark.asyncio
async def test_set_with_none_ttl_stores_infinite_entry(async_session):
    """None TTL must result in NULL expires_at (infinite lifetime)."""
    repo = CacheEntryRepository(async_session)
    await repo.set("immutable_key", "event_embedding", b"embed", ttl_seconds=None)

    # Verify directly in the table
    stmt = sa.select(cache_entry_table.c.expires_at).where(
        cache_entry_table.c.cache_key == "immutable_key"
    )
    result = await async_session.execute(stmt)
    row = result.fetchone()
    assert row is not None
    assert row[0] is None, "expires_at must be NULL for infinite TTL"


@pytest.mark.asyncio
async def test_delete_removes_entry(async_session):
    repo = CacheEntryRepository(async_session)
    await repo.set("del_key", "price_bar", b"data", ttl_seconds=900)
    await repo.delete("del_key")
    result = await repo.get("del_key")
    assert result is None


@pytest.mark.asyncio
async def test_delete_by_prefix_removes_matching_keys(async_session):
    repo = CacheEntryRepository(async_session)
    await repo.set("score:AAPL:latest", "company_score", b"s1", ttl_seconds=None)
    await repo.set("score:MSFT:latest", "company_score", b"s2", ttl_seconds=None)
    await repo.set("price_bar:AAPL:x", "price_bar", b"p1", ttl_seconds=900)

    count = await repo.delete_by_prefix("score:")
    assert count == 2

    assert await repo.get("price_bar:AAPL:x") == b"p1"
    assert await repo.get("score:AAPL:latest") is None


@pytest.mark.asyncio
async def test_set_upserts_existing_entry(async_session):
    repo = CacheEntryRepository(async_session)
    await repo.set("upsert_key", "price_bar", b"original", ttl_seconds=900)
    await repo.set("upsert_key", "price_bar", b"updated", ttl_seconds=900)
    result = await repo.get("upsert_key")
    assert result == b"updated"
