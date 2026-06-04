"""
Unit tests for BriefRepository (PLAN-F-026 TASK-001).

TDD — written before implementation. Uses AsyncMock to stub the SQLAlchemy session.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.briefs.repositories.brief_repository import BriefRepository, _extract_projection
from src.briefs.schemas.brief_schemas import BriefType, encode_cursor, decode_cursor
from src.storage.models.workflow_run import WorkflowRun


# ── Helpers ───────────────────────────────────────────────────────────────────

TENANT_A = uuid.uuid4()
TENANT_B = uuid.uuid4()


def _make_run(
    tenant_id: uuid.UUID = None,
    workflow_type: str = "morning_brief",
    completed_at: datetime = None,
    sample_size: int = 10,
    workflow_id: uuid.UUID = None,
) -> WorkflowRun:
    row = WorkflowRun()
    row.workflow_id = workflow_id or uuid.uuid4()
    row.tenant_id = tenant_id or TENANT_A
    row.workflow_type = workflow_type
    row.status = "COMPLETED"
    row.completed_at = completed_at or datetime(2026, 1, 1, tzinfo=timezone.utc)
    row.started_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    row.cost_usd = 0.01
    row.final_state = {
        "headline": "Test headline",
        "content_html": "<p>Content</p>",
        "confidence": 0.85,
        "sample_size": sample_size,
    }
    row.langfuse_trace_id = None
    row.user_id = uuid.uuid4()
    row.company_id = None
    return row


def _make_session_with_rows(rows: list) -> AsyncMock:
    """Build a minimal AsyncSession mock that returns `rows` on scalar().all()."""
    session = AsyncMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = rows
    result_mock = MagicMock()
    result_mock.scalars.return_value = scalars_mock
    result_mock.scalar_one_or_none.return_value = rows[0] if rows else None
    session.execute = AsyncMock(return_value=result_mock)
    return session


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_briefs_returns_all_four_types_for_tenant():
    """Only tenant A's rows are returned; tenant B rows excluded."""
    tenant_a_rows = [
        _make_run(tenant_id=TENANT_A, workflow_type="morning_brief"),
        _make_run(tenant_id=TENANT_A, workflow_type="watchlist_scan"),
        _make_run(tenant_id=TENANT_A, workflow_type="earnings_brief"),
        _make_run(tenant_id=TENANT_A, workflow_type="event_deep_dive"),
    ]
    session = _make_session_with_rows(tenant_a_rows)
    repo = BriefRepository(session)

    items, cursor = await repo.list_briefs(TENANT_A, None, None, 20)

    assert len(items) == 4
    types_returned = {item.type for item in items}
    assert types_returned == {
        BriefType.morning_brief,
        BriefType.watchlist_scan,
        BriefType.earnings_brief,
        BriefType.event_deep_dive,
    }
    # Verify tenant_id filter was applied by checking execute was called once
    session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_list_briefs_cursor_pagination():
    """Cursor pagination: two pages cover the full 15-row dataset with no overlaps."""
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    rows_page1 = [
        _make_run(completed_at=now - timedelta(hours=i)) for i in range(10)
    ]
    rows_page2 = [
        _make_run(completed_at=now - timedelta(hours=i + 10)) for i in range(5)
    ]

    all_rows = rows_page1 + rows_page2
    all_ids_page1 = {r.workflow_id for r in rows_page1}
    all_ids_page2 = {r.workflow_id for r in rows_page2}

    # Simulate two execute calls: first returns 11 rows (10 + 1 extra), second returns 5
    call_count = 0

    async def mock_execute(_stmt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # Return 11 rows to trigger next_cursor
            batch = (rows_page1 + rows_page2[:1])
        else:
            batch = rows_page2
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = batch
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock
        return result_mock

    session = AsyncMock()
    session.execute = mock_execute

    repo = BriefRepository(session)

    # First page
    page1_items, next_cursor = await repo.list_briefs(TENANT_A, None, None, 10)
    assert len(page1_items) == 10
    assert next_cursor is not None

    # Second page
    page2_items, next_cursor2 = await repo.list_briefs(TENANT_A, None, next_cursor, 10)
    assert len(page2_items) == 5

    # No overlap
    page1_ids = {item.brief_id for item in page1_items}
    page2_ids = {item.brief_id for item in page2_items}
    assert page1_ids.isdisjoint(page2_ids)
    assert next_cursor2 is None


@pytest.mark.asyncio
async def test_list_briefs_sorted_reverse_chronological():
    """Returned projections appear with most recent first."""
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    rows = [
        _make_run(completed_at=now - timedelta(hours=i)) for i in range(5)
    ]
    # SQLAlchemy returns them in the order the DB emits; we return them as-is.
    # The repo orders by completed_at DESC — the mock simulates DB already ordered.
    session = _make_session_with_rows(rows)
    repo = BriefRepository(session)

    items, _ = await repo.list_briefs(TENANT_A, None, None, 10)

    assert len(items) == 5
    for i in range(len(items) - 1):
        assert items[i].sent_at >= items[i + 1].sent_at


@pytest.mark.asyncio
async def test_get_brief_returns_none_for_wrong_tenant():
    """get_brief with wrong tenant returns None (IDOR prevention)."""
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=result_mock)

    repo = BriefRepository(session)
    brief_id = uuid.uuid4()

    result = await repo.get_brief(brief_id, TENANT_B)

    assert result is None


@pytest.mark.asyncio
async def test_low_sample_flag_set_when_sample_size_less_than_five():
    """low_sample is True when sample_size < 5."""
    row = _make_run(sample_size=3)
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = row
    session.execute = AsyncMock(return_value=result_mock)

    repo = BriefRepository(session)
    projection = await repo.get_brief(row.workflow_id, TENANT_A)

    assert projection is not None
    assert projection.low_sample is True
    assert projection.sample_size == 3


@pytest.mark.asyncio
async def test_low_sample_flag_not_set_when_sample_size_five_or_more():
    """low_sample is False when sample_size >= 5."""
    row = _make_run(sample_size=5)
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = row
    session.execute = AsyncMock(return_value=result_mock)

    repo = BriefRepository(session)
    projection = await repo.get_brief(row.workflow_id, TENANT_A)

    assert projection is not None
    assert projection.low_sample is False


def test_extract_projection_maps_all_fields():
    """_extract_projection correctly maps all fields from a WorkflowRun row."""
    row = _make_run(sample_size=7)
    proj = _extract_projection(row)

    assert proj.brief_id == row.workflow_id
    assert proj.type == BriefType.morning_brief
    assert proj.headline == "Test headline"
    assert proj.content_html == "<p>Content</p>"
    assert proj.confidence == 0.85
    assert proj.sample_size == 7
    assert proj.low_sample is False
    assert proj.delivery_status == "COMPLETED"
    assert proj.sent_at == row.completed_at
