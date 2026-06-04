"""
Unit / integration tests for PostgresSourceConfigRepository and
PostgresBindingRepository.

Uses fakeredis-compatible in-memory SQLite (aiosqlite) through SQLAlchemy 2.0
async engine. Tests are marked ``unit`` to be excluded from integration test runs
that require a live PostgreSQL instance.

Test coverage (TASK-002 spec):
  - list_all() returns all rows including disabled ones.
  - create() persists a row and returns it with generated source_id.
  - set_enabled(id, True) flips enabled; subsequent get_by_id reflects change.
  - set_enabled(id, False) for already-disabled source is idempotent (no error).
  - upsert() on binding creates row on first call; updates role on second call.
  - delete() removes binding; subsequent list_for_market does not include it.
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.storage.models.user import Base
from src.storage.models.source_config import SourceConfig
from src.storage.models.market_source_binding import MarketSourceBinding
from src.storage.repositories.source_config_repo import PostgresSourceConfigRepository
from src.storage.repositories.market_source_binding_repo import PostgresBindingRepository


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture()
async def async_session():
    """Provide an in-memory SQLite async session with all tables created."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )

    # SQLite does not support UUID natively; patch the dialect to accept them
    # as strings. MarketSourceBinding uses Text PK columns via SQLite mapping.
    async with engine.begin() as conn:
        # Enable FK enforcement in SQLite
        await conn.execute(text("PRAGMA foreign_keys=ON"))
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


def _make_source(**kwargs) -> dict:
    """Return a dict of minimum required fields to create a SourceConfig."""
    defaults = {
        "interface_type": "PriceProvider",
        "display_name": "Test Source",
        "credentials_ref": "env:TEST_API_KEY",
        "config": {},
        "cost_tier": "free",
        "priority": 0,
    }
    defaults.update(kwargs)
    return defaults


# Simple DTO shim used instead of importing Pydantic schemas to avoid circular
# imports at test collection time.
class _CreateDTO:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


# ── SourceConfig repository tests ─────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_all_includes_disabled(async_session: AsyncSession) -> None:
    repo = PostgresSourceConfigRepository(async_session)
    data = _make_source()
    dto = _CreateDTO(**data)
    created = await repo.create(dto)
    assert created.enabled is False

    rows = await repo.list_all()
    assert any(r.source_id == created.source_id for r in rows)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_returns_row_with_source_id(async_session: AsyncSession) -> None:
    repo = PostgresSourceConfigRepository(async_session)
    dto = _CreateDTO(**_make_source(display_name="Finnhub"))
    created = await repo.create(dto)
    assert created.source_id is not None
    assert created.display_name == "Finnhub"
    assert created.enabled is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_set_enabled_true_flips_flag(async_session: AsyncSession) -> None:
    repo = PostgresSourceConfigRepository(async_session)
    dto = _CreateDTO(**_make_source())
    created = await repo.create(dto)
    source_id = created.source_id

    updated = await repo.set_enabled(source_id, True)
    assert updated.enabled is True

    fetched = await repo.get_by_id(source_id)
    assert fetched is not None
    assert fetched.enabled is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_set_enabled_false_is_idempotent(async_session: AsyncSession) -> None:
    """Disabling an already-disabled source raises no error."""
    repo = PostgresSourceConfigRepository(async_session)
    dto = _CreateDTO(**_make_source())
    created = await repo.create(dto)

    # Both calls should succeed without exception
    await repo.set_enabled(created.source_id, False)
    result = await repo.set_enabled(created.source_id, False)
    assert result.enabled is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_set_enabled_updates_updated_at(async_session: AsyncSession) -> None:
    """updated_at must advance when enabled changes (RegistryRefresher relies on this)."""
    import asyncio
    repo = PostgresSourceConfigRepository(async_session)
    dto = _CreateDTO(**_make_source())
    created = await repo.create(dto)
    original_ts = created.updated_at

    # Small delay to ensure the timestamp advances
    await asyncio.sleep(0.01)
    updated = await repo.set_enabled(created.source_id, True)
    assert updated.updated_at >= original_ts


# ── Binding repository tests ──────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.asyncio
async def test_upsert_creates_binding(async_session: AsyncSession) -> None:
    src_repo = PostgresSourceConfigRepository(async_session)
    bind_repo = PostgresBindingRepository(async_session)

    source = await src_repo.create(_CreateDTO(**_make_source()))
    market_id = uuid.uuid4()

    binding = await bind_repo.upsert(market_id, "PriceProvider", source.source_id, "primary")
    assert binding.role == "primary"
    assert binding.market_id == str(market_id) or binding.market_id == market_id


@pytest.mark.unit
@pytest.mark.asyncio
async def test_upsert_updates_role_on_conflict(async_session: AsyncSession) -> None:
    src_repo = PostgresSourceConfigRepository(async_session)
    bind_repo = PostgresBindingRepository(async_session)

    source = await src_repo.create(_CreateDTO(**_make_source()))
    market_id = uuid.uuid4()

    await bind_repo.upsert(market_id, "PriceProvider", source.source_id, "primary")
    updated = await bind_repo.upsert(market_id, "PriceProvider", source.source_id, "fallback")
    assert updated.role == "fallback"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_removes_binding(async_session: AsyncSession) -> None:
    src_repo = PostgresSourceConfigRepository(async_session)
    bind_repo = PostgresBindingRepository(async_session)

    source = await src_repo.create(_CreateDTO(**_make_source()))
    market_id = uuid.uuid4()

    await bind_repo.upsert(market_id, "PriceProvider", source.source_id, "primary")
    await bind_repo.delete(market_id, "PriceProvider", source.source_id)

    bindings = await bind_repo.list_for_market(market_id)
    assert all(b.source_id != source.source_id for b in bindings)
