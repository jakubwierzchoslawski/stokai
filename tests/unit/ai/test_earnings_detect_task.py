"""
Unit tests for detect_t1_earnings Celery task.

TDD — PLAN-F-009 TASK-004.

Tests cover:
- Skips companies with existing brief run (idempotency)
- Dispatches earnings_brief_task for new events
- Handles no events gracefully (returns 0 dispatched)
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_earnings_event(
    company_id: uuid.UUID | None = None,
    tenant_id: uuid.UUID | None = None,
    earnings_date: date | None = None,
) -> MagicMock:
    """Return a mock EarningsEvent ORM row."""
    m = MagicMock()
    m.company_id = company_id or uuid.uuid4()
    m.tenant_id = tenant_id or uuid.uuid4()
    m.earnings_date = earnings_date or (date.today() + timedelta(days=1))
    return m


class TestDetectT1EarningsAsync:
    """_detect_t1_earnings_async — core async logic."""

    @pytest.mark.asyncio
    async def test_no_events_returns_zero_dispatched(self):
        """When there are no upcoming events, dispatched=0 and skipped=0."""
        from src.ai.tasks.earnings_brief_task import _detect_t1_earnings_async

        mock_session = AsyncMock()
        mock_event_repo = AsyncMock()
        mock_run_repo = AsyncMock()
        mock_event_repo.get_upcoming = AsyncMock(return_value=[])

        with patch(
            "src.ai.tasks.earnings_brief_task._get_db_session"
        ) as mock_ctx, patch(
            "src.ai.tasks.earnings_brief_task.EarningsEventRepository",
            return_value=mock_event_repo,
        ), patch(
            "src.ai.tasks.earnings_brief_task.EarningsBriefRunRepository",
            return_value=mock_run_repo,
        ):
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            # tenant_id_str=None → tenant_ids=[] → no iterations → 0 dispatched
            result = await _detect_t1_earnings_async(tenant_id_str=None)

        assert result["dispatched"] == 0
        assert result["skipped"] == 0

    @pytest.mark.asyncio
    async def test_skips_company_with_existing_brief_run(self):
        """Skips events where a brief run already exists (idempotency)."""
        from src.ai.tasks.earnings_brief_task import _detect_t1_earnings_async

        tenant_id = uuid.uuid4()
        event = _make_earnings_event(tenant_id=tenant_id)

        mock_session = AsyncMock()
        mock_event_repo = AsyncMock()
        mock_run_repo = AsyncMock()
        mock_event_repo.get_upcoming = AsyncMock(return_value=[event])
        mock_run_repo.exists = AsyncMock(return_value=True)  # already exists

        with patch(
            "src.ai.tasks.earnings_brief_task._get_db_session"
        ) as mock_ctx, patch(
            "src.ai.tasks.earnings_brief_task.EarningsEventRepository",
            return_value=mock_event_repo,
        ), patch(
            "src.ai.tasks.earnings_brief_task.EarningsBriefRunRepository",
            return_value=mock_run_repo,
        ):
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await _detect_t1_earnings_async(
                tenant_id_str=str(tenant_id),
            )

        assert result["dispatched"] == 0
        assert result["skipped"] == 1

    @pytest.mark.asyncio
    async def test_dispatches_for_new_events(self):
        """Dispatches earnings_brief_task when no brief run exists."""
        from src.ai.tasks.earnings_brief_task import _detect_t1_earnings_async

        tenant_id = uuid.uuid4()
        event = _make_earnings_event(tenant_id=tenant_id)

        mock_session = AsyncMock()
        mock_event_repo = AsyncMock()
        mock_run_repo = AsyncMock()
        mock_event_repo.get_upcoming = AsyncMock(return_value=[event])
        mock_run_repo.exists = AsyncMock(return_value=False)  # does not exist

        mock_brief_task = MagicMock()

        with patch(
            "src.ai.tasks.earnings_brief_task._get_db_session"
        ) as mock_ctx, patch(
            "src.ai.tasks.earnings_brief_task.EarningsEventRepository",
            return_value=mock_event_repo,
        ), patch(
            "src.ai.tasks.earnings_brief_task.EarningsBriefRunRepository",
            return_value=mock_run_repo,
        ), patch(
            "src.ai.tasks.earnings_brief_task.earnings_brief_task",
            mock_brief_task,
        ):
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_brief_task.apply_async = MagicMock()

            result = await _detect_t1_earnings_async(
                tenant_id_str=str(tenant_id),
            )

        assert result["dispatched"] == 1
        assert result["skipped"] == 0
        mock_brief_task.apply_async.assert_called_once()

    @pytest.mark.asyncio
    async def test_mixed_events_dispatches_only_new(self):
        """With 2 events — one existing, one new — dispatches only the new one."""
        from src.ai.tasks.earnings_brief_task import _detect_t1_earnings_async

        tenant_id = uuid.uuid4()
        event1 = _make_earnings_event(tenant_id=tenant_id)
        event2 = _make_earnings_event(tenant_id=tenant_id)

        mock_session = AsyncMock()
        mock_event_repo = AsyncMock()
        mock_run_repo = AsyncMock()
        mock_event_repo.get_upcoming = AsyncMock(return_value=[event1, event2])
        # event1 exists; event2 is new
        mock_run_repo.exists = AsyncMock(side_effect=[True, False])

        mock_brief_task = MagicMock()

        with patch(
            "src.ai.tasks.earnings_brief_task._get_db_session"
        ) as mock_ctx, patch(
            "src.ai.tasks.earnings_brief_task.EarningsEventRepository",
            return_value=mock_event_repo,
        ), patch(
            "src.ai.tasks.earnings_brief_task.EarningsBriefRunRepository",
            return_value=mock_run_repo,
        ), patch(
            "src.ai.tasks.earnings_brief_task.earnings_brief_task",
            mock_brief_task,
        ):
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_brief_task.apply_async = MagicMock()

            result = await _detect_t1_earnings_async(
                tenant_id_str=str(tenant_id),
            )

        assert result["dispatched"] == 1
        assert result["skipped"] == 1
