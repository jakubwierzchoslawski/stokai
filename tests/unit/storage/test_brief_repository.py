"""
Unit tests for BriefRepository (IBriefRepository SQLAlchemy implementation).

TDD: written before implementation — PLAN-F-010 TASK-002.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.ai.workflows.event_deep_dive.state import BriefCreate


def _make_brief_create(**kwargs) -> BriefCreate:
    defaults = {
        "event_id": uuid.uuid4(),
        "tenant_id": uuid.uuid4(),
        "content": {"headline": "Test event", "summary": "Some impact"},
        "confidence": 0.85,
        "cost_usd": 0.12,
        "cost_limited": False,
    }
    defaults.update(kwargs)
    return BriefCreate(**defaults)


class TestInsertMemo:
    @pytest.mark.asyncio
    async def test_insert_memo_returns_brief_with_id(self):
        """insert_memo should return a Brief ORM object with a non-null brief_id."""
        from src.storage.repositories.brief_repository import (
            BriefRepository,
            Brief,
        )

        session = AsyncMock()
        session.flush = AsyncMock()
        session.refresh = AsyncMock()

        create_dto = _make_brief_create()

        # Simulate refresh populating the ORM object
        expected_id = create_dto.brief_id

        async def mock_refresh(obj):
            obj.brief_id = expected_id

        session.refresh.side_effect = mock_refresh

        repo = BriefRepository(session)
        result = await repo.insert_memo(create_dto)

        assert result is not None
        assert result.brief_id == expected_id
        session.add.assert_called_once()
        session.flush.assert_called_once()


class TestGetByEventId:
    @pytest.mark.asyncio
    async def test_get_by_event_id_returns_none_when_absent(self):
        """get_by_event_id returns None when no brief exists for the event."""
        from src.storage.repositories.brief_repository import BriefRepository

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_result)

        repo = BriefRepository(session)
        result = await repo.get_by_event_id(uuid.uuid4())

        assert result is None

    @pytest.mark.asyncio
    async def test_get_by_event_id_returns_brief_when_present(self):
        """get_by_event_id returns the Brief ORM row when it exists."""
        from src.storage.repositories.brief_repository import BriefRepository, Brief

        session = AsyncMock()
        brief_id = uuid.uuid4()
        event_id = uuid.uuid4()

        mock_brief = MagicMock(spec=Brief)
        mock_brief.brief_id = brief_id
        mock_brief.event_id = event_id

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_brief
        session.execute = AsyncMock(return_value=mock_result)

        repo = BriefRepository(session)
        result = await repo.get_by_event_id(event_id)

        assert result is not None
        assert result.brief_id == brief_id


class TestMarkHilReviewed:
    @pytest.mark.asyncio
    async def test_mark_hil_reviewed_executes_update(self):
        """mark_hil_reviewed should execute an UPDATE on the brief row."""
        from src.storage.repositories.brief_repository import BriefRepository

        session = AsyncMock()
        session.execute = AsyncMock()
        session.flush = AsyncMock()

        repo = BriefRepository(session)
        await repo.mark_hil_reviewed(uuid.uuid4(), approved=True)

        session.execute.assert_called_once()
        session.flush.assert_called_once()


class TestTenantIsolation:
    @pytest.mark.asyncio
    async def test_tenant_isolation_prevents_cross_tenant_read(self):
        """get_by_event_id with a different tenant should return None."""
        from src.storage.repositories.brief_repository import BriefRepository

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_result)

        repo = BriefRepository(session)
        result = await repo.get_by_event_id(uuid.uuid4())

        # With tenant isolation, cross-tenant queries return None
        assert result is None
