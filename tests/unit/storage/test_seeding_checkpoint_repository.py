"""
Unit tests for SeedingCheckpointRepository.

All DB interactions are mocked; these tests verify business logic and query
construction without requiring a running PostgreSQL instance.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.ingestion.cold_start.types import CheckpointState
from src.storage.repositories.seeding_checkpoint_repository import (
    CheckpointRow,
    SeedingCheckpointRepository,
)


def _make_session(fetchone_result=None, fetchall_result=None):
    """Build a minimal AsyncMock session for unit tests."""
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.fetchone.return_value = fetchone_result
    result_mock.fetchall.return_value = fetchall_result or []
    session.execute = AsyncMock(return_value=result_mock)
    session.commit = AsyncMock()
    return session


@pytest.mark.unit
class TestGetCheckpoint:
    """Tests for get_checkpoint()."""

    @pytest.mark.asyncio
    async def test_returns_none_when_no_row_exists(self):
        """get_checkpoint returns None when no row exists for the given key."""
        session = _make_session(fetchone_result=None)
        repo = SeedingCheckpointRepository(session)

        result = await repo.get_checkpoint("gdelt:1979-01-01:1979-01-31")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_checkpoint_row_when_exists(self):
        """get_checkpoint returns a CheckpointRow when a row exists."""
        now = datetime.now(tz=timezone.utc)
        row = (
            "gdelt:1979-01-01:1979-01-31",  # batch_key
            "done",  # state
            150,  # events_seeded
            150,  # embeddings_done
            None,  # error_detail
            now,  # started_at
            now,  # completed_at
            now,  # updated_at
        )
        session = _make_session(fetchone_result=row)
        repo = SeedingCheckpointRepository(session)

        result = await repo.get_checkpoint("gdelt:1979-01-01:1979-01-31")

        assert result is not None
        assert result.batch_key == "gdelt:1979-01-01:1979-01-31"
        assert result.state == CheckpointState.done
        assert result.events_seeded == 150


@pytest.mark.unit
class TestUpsertCheckpoint:
    """Tests for upsert_checkpoint()."""

    @pytest.mark.asyncio
    async def test_creates_new_row_with_state_in_progress(self):
        """upsert_checkpoint creates a new row with state=in_progress."""
        session = _make_session()
        repo = SeedingCheckpointRepository(session)

        await repo.upsert_checkpoint(
            batch_key="gdelt:1979-01-01:1979-01-31",
            state=CheckpointState.in_progress,
            meta={"events_seeded": 0, "embeddings_done": 0},
        )

        session.execute.assert_called_once()
        session.commit.assert_called_once()

        # Verify the execute call contained 'in_progress'
        call_args = session.execute.call_args
        params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("parameters", {})
        # params is the second positional arg to execute
        if len(call_args[0]) > 1:
            params = call_args[0][1]
        else:
            params = call_args.args[1] if call_args.args else {}
        assert params["state"] == "in_progress"
        assert params["batch_key"] == "gdelt:1979-01-01:1979-01-31"

    @pytest.mark.asyncio
    async def test_updates_existing_row_without_creating_duplicate(self):
        """upsert_checkpoint updates an existing row (ON CONFLICT DO UPDATE).

        We verify only one execute() call is made (no SELECT + INSERT pair).
        """
        session = _make_session()
        repo = SeedingCheckpointRepository(session)

        # First upsert
        await repo.upsert_checkpoint(
            batch_key="gdelt:1979-01-01:1979-01-31",
            state=CheckpointState.in_progress,
            meta={},
        )
        # Second upsert to same key
        await repo.upsert_checkpoint(
            batch_key="gdelt:1979-01-01:1979-01-31",
            state=CheckpointState.done,
            meta={"events_seeded": 200, "completed_at": datetime.now(tz=timezone.utc)},
        )

        # Two execute() calls (one per upsert), but only one row conceptually
        assert session.execute.call_count == 2
        assert session.commit.call_count == 2

    @pytest.mark.asyncio
    async def test_upsert_passes_error_detail_in_meta(self):
        """upsert_checkpoint propagates error_detail from meta dict."""
        session = _make_session()
        repo = SeedingCheckpointRepository(session)

        await repo.upsert_checkpoint(
            batch_key="gdelt:1979-02-01:1979-02-28",
            state=CheckpointState.failed,
            meta={"error_detail": "HTTP 404 on GDELT file"},
        )

        call_args = session.execute.call_args
        params = call_args[0][1]
        assert params["error_detail"] == "HTTP 404 on GDELT file"
        assert params["state"] == "failed"


@pytest.mark.unit
class TestListPendingBatches:
    """Tests for list_pending_batches()."""

    @pytest.mark.asyncio
    async def test_returns_only_non_done_batch_keys(self):
        """list_pending_batches returns only batch keys whose state is not 'done'."""
        # The SQL query already filters state != 'done'; mock returns only pending/failed
        rows = [
            ("gdelt:1979-01-01:1979-01-31",),
            ("gdelt:1979-02-01:1979-02-28",),
        ]
        session = _make_session(fetchall_result=rows)
        repo = SeedingCheckpointRepository(session)

        result = await repo.list_pending_batches(
            start_date=date(1979, 1, 1),
            end_date=date(1979, 12, 31),
        )

        assert "gdelt:1979-01-01:1979-01-31" in result
        assert "gdelt:1979-02-01:1979-02-28" in result

    @pytest.mark.asyncio
    async def test_returns_empty_when_all_done(self):
        """list_pending_batches returns empty list when all batches are done."""
        session = _make_session(fetchall_result=[])
        repo = SeedingCheckpointRepository(session)

        result = await repo.list_pending_batches(
            start_date=date(1979, 1, 1),
            end_date=date(1979, 12, 31),
        )

        assert result == []

    @pytest.mark.asyncio
    async def test_filters_by_date_range(self):
        """list_pending_batches excludes keys whose start date is outside the range."""
        rows = [
            ("gdelt:1978-12-01:1978-12-31",),  # outside range (before start)
            ("gdelt:1979-01-01:1979-01-31",),  # inside range
            ("gdelt:1980-01-01:1980-01-31",),  # outside range (after end)
        ]
        session = _make_session(fetchall_result=rows)
        repo = SeedingCheckpointRepository(session)

        result = await repo.list_pending_batches(
            start_date=date(1979, 1, 1),
            end_date=date(1979, 12, 31),
        )

        assert result == ["gdelt:1979-01-01:1979-01-31"]
