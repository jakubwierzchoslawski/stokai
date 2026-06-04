"""
Integration tests for SeedingCheckpointRepository.

These tests run against a real PostgreSQL test database. They are marked with
@pytest.mark.integration and are excluded from the default test run
(use: pytest -m integration).

Prerequisites:
    - TEST_DATABASE_URL env var pointing at a test PostgreSQL instance
    - seeding_checkpoint table created via Alembic migration 0031
"""
from __future__ import annotations

import os
from datetime import date, datetime, timezone

import pytest
import pytest_asyncio

from src.ingestion.cold_start.types import CheckpointState
from src.storage.repositories.seeding_checkpoint_repository import (
    SeedingCheckpointRepository,
)

# Skip entire module if no test DB configured
pytestmark = pytest.mark.integration

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "")


@pytest.fixture
def requires_test_db():
    """Skip this test if TEST_DATABASE_URL is not configured."""
    if not TEST_DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL not set — skipping integration test")


@pytest.mark.asyncio
async def test_round_trip_upsert(requires_test_db):
    """Integration: upsert then get_checkpoint returns consistent data."""
    try:
        from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
        from sqlalchemy.orm import sessionmaker

        engine = create_async_engine(TEST_DATABASE_URL, echo=False)
        AsyncSessionFactory = sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        async with AsyncSessionFactory() as session:
            repo = SeedingCheckpointRepository(session)
            batch_key = "gdelt:1979-01-01:1979-01-31"

            # Insert new row
            await repo.upsert_checkpoint(
                batch_key=batch_key,
                state=CheckpointState.in_progress,
                meta={"events_seeded": 0, "started_at": datetime.now(tz=timezone.utc)},
            )

            # Verify it was inserted
            row = await repo.get_checkpoint(batch_key)
            assert row is not None
            assert row.batch_key == batch_key
            assert row.state == CheckpointState.in_progress
            assert row.events_seeded == 0

            # Update to done
            now = datetime.now(tz=timezone.utc)
            await repo.upsert_checkpoint(
                batch_key=batch_key,
                state=CheckpointState.done,
                meta={"events_seeded": 100, "embeddings_done": 100, "completed_at": now},
            )

            # Verify update without duplicate
            row_updated = await repo.get_checkpoint(batch_key)
            assert row_updated is not None
            assert row_updated.state == CheckpointState.done
            assert row_updated.events_seeded == 100
            assert row_updated.embeddings_done == 100

            # list_pending_batches should NOT include this batch (state=done)
            pending = await repo.list_pending_batches(
                start_date=date(1979, 1, 1),
                end_date=date(1979, 12, 31),
            )
            assert batch_key not in pending

            # Cleanup
            await session.execute(
                __import__("sqlalchemy").text(
                    "DELETE FROM seeding_checkpoint WHERE batch_key = :k"
                ),
                {"k": batch_key},
            )
            await session.commit()

        await engine.dispose()
    except ImportError as exc:
        pytest.skip(f"SQLAlchemy async deps not available: {exc}")


@pytest.mark.asyncio
async def test_list_pending_batches_excludes_done(requires_test_db):
    """Integration: list_pending_batches returns pending/failed but not done rows."""
    try:
        from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
        from sqlalchemy.orm import sessionmaker

        engine = create_async_engine(TEST_DATABASE_URL, echo=False)
        AsyncSessionFactory = sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        async with AsyncSessionFactory() as session:
            repo = SeedingCheckpointRepository(session)
            done_key = "gdelt:1979-03-01:1979-03-31"
            pending_key = "gdelt:1979-04-01:1979-04-30"

            await repo.upsert_checkpoint(done_key, CheckpointState.done, {})
            await repo.upsert_checkpoint(pending_key, CheckpointState.pending, {})

            pending = await repo.list_pending_batches(
                start_date=date(1979, 1, 1),
                end_date=date(1979, 12, 31),
            )
            assert pending_key in pending
            assert done_key not in pending

            # Cleanup
            import sqlalchemy
            for key in (done_key, pending_key):
                await session.execute(
                    sqlalchemy.text("DELETE FROM seeding_checkpoint WHERE batch_key = :k"),
                    {"k": key},
                )
            await session.commit()

        await engine.dispose()
    except ImportError as exc:
        pytest.skip(f"SQLAlchemy async deps not available: {exc}")
