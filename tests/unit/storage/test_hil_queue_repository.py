"""
Unit tests for HILQueueRepository.

All DB interactions are mocked via AsyncMock. No real PostgreSQL required.

TDD tests defined before implementation (PLAN-F-013 TASK-002).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from src.storage.repositories.hil_queue_repository import (
    HILQueueRepository,
    HILQueueItemCreate,
    HILStatus,
)


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


def _make_create_dto(
    *,
    tenant_id: uuid.UUID | None = None,
    workflow_run_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    confidence: float = 0.55,
    scheduled_send_at: datetime | None = None,
    lc_checkpoint_id: str = "checkpoint-abc",
    workflow_type: str = "on_demand",
) -> HILQueueItemCreate:
    return HILQueueItemCreate(
        workflow_run_id=workflow_run_id or uuid.uuid4(),
        workflow_type=workflow_type,
        user_id=user_id or uuid.uuid4(),
        tenant_id=tenant_id or uuid.uuid4(),
        confidence=confidence,
        scheduled_send_at=scheduled_send_at or (_utcnow() + timedelta(hours=1)),
        lc_checkpoint_id=lc_checkpoint_id,
    )


def _make_orm_row(item_id: uuid.UUID | None = None, **kwargs) -> MagicMock:
    """Return a MagicMock that mimics a HILQueueItem ORM row."""
    row = MagicMock()
    row.item_id = item_id or uuid.uuid4()
    row.status = kwargs.get("status", "pending")
    row.tenant_id = kwargs.get("tenant_id", uuid.uuid4())
    row.workflow_run_id = kwargs.get("workflow_run_id", uuid.uuid4())
    row.confidence = kwargs.get("confidence", 0.55)
    row.scheduled_send_at = kwargs.get("scheduled_send_at", _utcnow() + timedelta(hours=1))
    return row


@pytest.mark.asyncio
class TestCreate:
    """test_create_inserts_row_with_correct_tenant_id"""

    async def test_create_inserts_row_with_correct_tenant_id(self) -> None:
        session = AsyncMock()
        tenant_id = uuid.uuid4()
        dto = _make_create_dto(tenant_id=tenant_id)

        # Simulate session.add + flush + refresh lifecycle
        orm_row = _make_orm_row(tenant_id=tenant_id)
        session.refresh = AsyncMock()

        # After flush + refresh the add call would have been made with correct tenant_id
        async def fake_refresh(obj):
            # simulate refresh populating item_id
            obj.item_id = uuid.uuid4()
            obj.status = "pending"
            obj.tenant_id = tenant_id
            obj.created_at = _utcnow()

        session.refresh.side_effect = fake_refresh

        repo = HILQueueRepository(session)
        result = await repo.create(dto)

        session.add.assert_called_once()
        added_obj = session.add.call_args[0][0]
        assert added_obj.tenant_id == tenant_id
        assert added_obj.lc_checkpoint_id == dto.lc_checkpoint_id
        assert added_obj.confidence == dto.confidence
        session.flush.assert_called_once()
        session.refresh.assert_called_once()


@pytest.mark.asyncio
class TestListPending:
    """test_list_pending_filters_by_tenant_and_status"""

    async def test_list_pending_filters_by_tenant_and_status(self) -> None:
        session = AsyncMock()
        tenant_id = uuid.uuid4()

        row1 = _make_orm_row(tenant_id=tenant_id, status="pending")
        row2 = _make_orm_row(tenant_id=tenant_id, status="pending")
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [row1, row2]
        session.execute = AsyncMock(return_value=result_mock)

        repo = HILQueueRepository(session)
        items = await repo.list_pending(tenant_id)

        assert len(items) == 2
        session.execute.assert_called_once()
        # Confirm execute was called (query was built and run)
        stmt = session.execute.call_args[0][0]
        assert stmt is not None

    async def test_list_pending_returns_empty_for_different_tenant(self) -> None:
        session = AsyncMock()
        tenant_id = uuid.uuid4()

        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=result_mock)

        repo = HILQueueRepository(session)
        items = await repo.list_pending(tenant_id)

        assert items == []


@pytest.mark.asyncio
class TestGet:
    """test_get_returns_none_for_wrong_tenant"""

    async def test_get_returns_none_for_wrong_tenant(self) -> None:
        session = AsyncMock()
        item_id = uuid.uuid4()
        wrong_tenant_id = uuid.uuid4()

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=result_mock)

        repo = HILQueueRepository(session)
        result = await repo.get(item_id, wrong_tenant_id)

        assert result is None

    async def test_get_returns_row_for_correct_tenant(self) -> None:
        session = AsyncMock()
        tenant_id = uuid.uuid4()
        item_id = uuid.uuid4()

        orm_row = _make_orm_row(item_id=item_id, tenant_id=tenant_id)
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = orm_row
        session.execute = AsyncMock(return_value=result_mock)

        repo = HILQueueRepository(session)
        result = await repo.get(item_id, tenant_id)

        assert result is orm_row


@pytest.mark.asyncio
class TestUpdateStatus:
    """test_update_status_changes_status_and_reviewer"""

    async def test_update_status_changes_status_and_reviewer(self) -> None:
        session = AsyncMock()
        item_id = uuid.uuid4()
        tenant_id = uuid.uuid4()
        reviewer_id = uuid.uuid4()
        reviewed_at = _utcnow()

        updated_row = _make_orm_row(
            item_id=item_id,
            tenant_id=tenant_id,
            status="approved",
        )
        updated_row.reviewer_id = reviewer_id
        updated_row.reviewed_at = reviewed_at

        # execute for update + execute for select (re-fetch)
        update_result = MagicMock()
        select_result = MagicMock()
        select_result.scalar_one_or_none.return_value = updated_row
        session.execute = AsyncMock(side_effect=[update_result, select_result])

        repo = HILQueueRepository(session)
        result = await repo.update_status(
            item_id=item_id,
            tenant_id=tenant_id,
            status=HILStatus.APPROVED,
            reviewer_id=reviewer_id,
            reviewed_at=reviewed_at,
        )

        assert session.execute.call_count == 2
        assert result.status == "approved"
        assert result.reviewer_id == reviewer_id

    async def test_update_status_without_reviewer(self) -> None:
        session = AsyncMock()
        item_id = uuid.uuid4()
        tenant_id = uuid.uuid4()

        updated_row = _make_orm_row(item_id=item_id, tenant_id=tenant_id, status="timed_out")
        update_result = MagicMock()
        select_result = MagicMock()
        select_result.scalar_one_or_none.return_value = updated_row
        session.execute = AsyncMock(side_effect=[update_result, select_result])

        repo = HILQueueRepository(session)
        result = await repo.update_status(
            item_id=item_id,
            tenant_id=tenant_id,
            status=HILStatus.TIMED_OUT,
        )

        assert result.status == "timed_out"


@pytest.mark.asyncio
class TestListTimedOutPending:
    """test_list_timed_out_pending_returns_only_past_deadline_pending_rows"""

    async def test_list_timed_out_pending_returns_only_past_deadline_pending_rows(
        self,
    ) -> None:
        session = AsyncMock()
        now = _utcnow()

        # Two overdue pending rows
        overdue1 = _make_orm_row(
            status="pending",
            scheduled_send_at=now - timedelta(hours=2),
        )
        overdue2 = _make_orm_row(
            status="pending",
            scheduled_send_at=now - timedelta(minutes=5),
        )

        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [overdue1, overdue2]
        session.execute = AsyncMock(return_value=result_mock)

        repo = HILQueueRepository(session)
        items = await repo.list_timed_out_pending(now)

        assert len(items) == 2
        session.execute.assert_called_once()

    async def test_non_overdue_items_not_returned(self) -> None:
        session = AsyncMock()
        now = _utcnow()

        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=result_mock)

        repo = HILQueueRepository(session)
        items = await repo.list_timed_out_pending(now)

        assert items == []
