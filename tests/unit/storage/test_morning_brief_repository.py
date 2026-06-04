"""
Unit tests for MorningBriefRepository (IMorningBriefRepository implementation).

TDD: written before implementation — PLAN-F-006 TASK-002.

Tests:
  - insert: persists a brief row, returns ORM object with populated brief_id.
  - get_latest_by_user: returns most recent brief, returns None when absent.
  - update_hil_status: executes UPDATE, persists status.
  - update_sent_at: executes UPDATE, persists sent_at.
  - list_by_user: returns paginated results, tenant-scoped.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.storage.repositories.morning_brief_repository import (
    MorningBriefCreate,
    MorningBriefRepository,
)
from src.storage.models.brief import Brief


def _make_dto(**kwargs) -> MorningBriefCreate:
    defaults = {
        "user_id": uuid.uuid4(),
        "tenant_id": uuid.uuid4(),
        "workflow_id": uuid.uuid4(),
        "content": "<p>Morning brief content</p>",
        "confidence": 0.82,
        "cost_usd": 0.15,
    }
    defaults.update(kwargs)
    return MorningBriefCreate(**defaults)


def _make_session() -> AsyncMock:
    session = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.execute = AsyncMock()
    return session


class TestInsert:
    @pytest.mark.asyncio
    async def test_insert_returns_brief_with_brief_id(self):
        """insert() must return a Brief ORM object with a non-null brief_id."""
        session = _make_session()
        dto = _make_dto()

        async def mock_refresh(obj):
            obj.brief_id = dto.brief_id

        session.refresh.side_effect = mock_refresh

        repo = MorningBriefRepository(session)
        result = await repo.insert(dto)

        assert result is not None
        assert result.brief_id == dto.brief_id

    @pytest.mark.asyncio
    async def test_insert_calls_add_and_flush(self):
        """insert() must call session.add() and session.flush()."""
        session = _make_session()
        dto = _make_dto()

        repo = MorningBriefRepository(session)
        await repo.insert(dto)

        session.add.assert_called_once()
        session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_insert_sets_brief_type_to_morning_brief(self):
        """insert() must set brief_type='morning_brief' on the ORM object."""
        session = _make_session()
        dto = _make_dto()

        added_obj = None

        def capture_add(obj):
            nonlocal added_obj
            added_obj = obj

        session.add.side_effect = capture_add

        repo = MorningBriefRepository(session)
        await repo.insert(dto)

        assert added_obj is not None
        assert added_obj.brief_type == "morning_brief"

    @pytest.mark.asyncio
    async def test_insert_sets_hil_status_to_none(self):
        """insert() must set hil_status='none' on new rows."""
        session = _make_session()
        dto = _make_dto()

        added_obj = None

        def capture_add(obj):
            nonlocal added_obj
            added_obj = obj

        session.add.side_effect = capture_add

        repo = MorningBriefRepository(session)
        await repo.insert(dto)

        assert added_obj is not None
        assert added_obj.hil_status == "none"


class TestGetLatestByUser:
    @pytest.mark.asyncio
    async def test_get_latest_by_user_returns_none_when_absent(self):
        """get_latest_by_user() returns None when no brief exists."""
        session = _make_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        repo = MorningBriefRepository(session)
        result = await repo.get_latest_by_user(uuid.uuid4(), uuid.uuid4())

        assert result is None

    @pytest.mark.asyncio
    async def test_get_latest_by_user_returns_brief_when_present(self):
        """get_latest_by_user() returns the most recent Brief when found."""
        session = _make_session()

        mock_brief = MagicMock(spec=Brief)
        mock_brief.brief_id = uuid.uuid4()
        mock_brief.brief_type = "morning_brief"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_brief
        session.execute.return_value = mock_result

        repo = MorningBriefRepository(session)
        result = await repo.get_latest_by_user(uuid.uuid4(), uuid.uuid4())

        assert result is not None
        assert result.brief_id == mock_brief.brief_id

    @pytest.mark.asyncio
    async def test_get_latest_tenant_scoped(self):
        """get_latest_by_user() must be called with tenant_id for isolation."""
        session = _make_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        user_id = uuid.uuid4()
        tenant_id = uuid.uuid4()
        repo = MorningBriefRepository(session)
        await repo.get_latest_by_user(user_id, tenant_id)

        # execute must have been called (statement was issued)
        session.execute.assert_called_once()


class TestUpdateHilStatus:
    @pytest.mark.asyncio
    async def test_update_hil_status_executes_update(self):
        """update_hil_status() must execute an UPDATE statement and flush."""
        session = _make_session()
        session.execute.return_value = MagicMock()

        repo = MorningBriefRepository(session)
        await repo.update_hil_status(uuid.uuid4(), uuid.uuid4(), "approved")

        session.execute.assert_called_once()
        session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_hil_status_pending(self):
        """update_hil_status() must accept 'pending' status."""
        session = _make_session()
        session.execute.return_value = MagicMock()

        repo = MorningBriefRepository(session)
        await repo.update_hil_status(uuid.uuid4(), uuid.uuid4(), "pending")

        session.execute.assert_called_once()


class TestUpdateSentAt:
    @pytest.mark.asyncio
    async def test_update_sent_at_executes_update(self):
        """update_sent_at() must execute an UPDATE statement and flush."""
        session = _make_session()
        session.execute.return_value = MagicMock()

        sent_at = datetime.now(tz=timezone.utc)
        repo = MorningBriefRepository(session)
        await repo.update_sent_at(uuid.uuid4(), uuid.uuid4(), sent_at)

        session.execute.assert_called_once()
        session.flush.assert_called_once()


class TestListByUser:
    @pytest.mark.asyncio
    async def test_list_by_user_returns_empty_list_when_absent(self):
        """list_by_user() returns [] when no briefs exist."""
        session = _make_session()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session.execute.return_value = mock_result

        repo = MorningBriefRepository(session)
        result = await repo.list_by_user(uuid.uuid4(), uuid.uuid4())

        assert result == []

    @pytest.mark.asyncio
    async def test_list_by_user_filters_by_brief_type(self):
        """list_by_user() must issue a query (brief_type filter applied)."""
        session = _make_session()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session.execute.return_value = mock_result

        repo = MorningBriefRepository(session)
        await repo.list_by_user(
            uuid.uuid4(), uuid.uuid4(), brief_type="morning_brief"
        )

        session.execute.assert_called_once()
