"""
Unit tests for high-anomaly deep-dive dispatch.

TDD: written before implementation — PLAN-F-008 TASK-016.

Tests:
  - High anomaly triggers dispatch_high_anomalies
  - No dispatch when high_anomaly_company_ids is empty
  - Dispatch is non-blocking (fire-and-forget)
  - dispatch_high_anomalies calls celery_app.send_task per company
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.ai.workflows.watchlist_scan_nodes import dispatch_high_anomalies
from src.ai.workflows.watchlist_scan_state import WatchlistScanState


def _make_state(**kwargs) -> WatchlistScanState:
    defaults = {
        "workflow_id": uuid.uuid4(),
        "tenant_id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "started_at": datetime.now(tz=timezone.utc),
    }
    defaults.update(kwargs)
    return WatchlistScanState(**defaults)


class TestDispatchHighAnomalies:
    @pytest.mark.asyncio
    async def test_no_dispatch_when_high_anomaly_ids_empty(self):
        """dispatch_high_anomalies does nothing when list is empty."""
        celery_app = MagicMock()
        celery_app.send_task = MagicMock()

        state = _make_state(high_anomaly_company_ids=[])
        result = await dispatch_high_anomalies(state, celery_app=celery_app)

        celery_app.send_task.assert_not_called()
        assert result is state  # state unchanged

    @pytest.mark.asyncio
    async def test_dispatches_one_task_per_high_anomaly_company(self):
        """One event_deep_dive task is dispatched per high-anomaly company."""
        c1, c2 = uuid.uuid4(), uuid.uuid4()
        celery_app = MagicMock()
        celery_app.send_task = MagicMock()

        state = _make_state(high_anomaly_company_ids=[c1, c2])
        await dispatch_high_anomalies(state, celery_app=celery_app)

        assert celery_app.send_task.call_count == 2

    @pytest.mark.asyncio
    async def test_dispatches_correct_task_name(self):
        """Dispatched task name must be 'ai.event_deep_dive'."""
        c1 = uuid.uuid4()
        celery_app = MagicMock()
        celery_app.send_task = MagicMock()

        state = _make_state(high_anomaly_company_ids=[c1])
        await dispatch_high_anomalies(state, celery_app=celery_app)

        task_name = celery_app.send_task.call_args[0][0]
        assert task_name == "ai.event_deep_dive"

    @pytest.mark.asyncio
    async def test_dispatch_is_non_blocking(self):
        """dispatch_high_anomalies returns immediately (fire-and-forget)."""
        c1 = uuid.uuid4()
        celery_app = MagicMock()
        celery_app.send_task = MagicMock()

        state = _make_state(high_anomaly_company_ids=[c1])
        # Must return without awaiting task completion
        result = await dispatch_high_anomalies(state, celery_app=celery_app)

        assert result is not None

    @pytest.mark.asyncio
    async def test_dispatch_includes_company_id_in_kwargs(self):
        """Each dispatched task must include company_id in kwargs."""
        c1 = uuid.uuid4()
        celery_app = MagicMock()
        celery_app.send_task = MagicMock()

        state = _make_state(high_anomaly_company_ids=[c1])
        await dispatch_high_anomalies(state, celery_app=celery_app)

        call_kwargs = celery_app.send_task.call_args[1].get(
            "kwargs", celery_app.send_task.call_args.kwargs.get("kwargs", {})
        )
        assert "company_id" in call_kwargs
        assert call_kwargs["company_id"] == str(c1)

    @pytest.mark.asyncio
    async def test_dispatch_includes_tenant_id_in_kwargs(self):
        """Each dispatched task must include tenant_id in kwargs."""
        c1 = uuid.uuid4()
        tenant_id = uuid.uuid4()
        celery_app = MagicMock()
        celery_app.send_task = MagicMock()

        state = _make_state(high_anomaly_company_ids=[c1], tenant_id=tenant_id)
        await dispatch_high_anomalies(state, celery_app=celery_app)

        call_kwargs = celery_app.send_task.call_args[1].get(
            "kwargs", celery_app.send_task.call_args.kwargs.get("kwargs", {})
        )
        assert "tenant_id" in call_kwargs
        assert call_kwargs["tenant_id"] == str(tenant_id)

    @pytest.mark.asyncio
    async def test_send_task_failure_is_swallowed(self):
        """If send_task raises, dispatch_high_anomalies must not re-raise."""
        c1 = uuid.uuid4()
        celery_app = MagicMock()
        celery_app.send_task = MagicMock(side_effect=RuntimeError("connection refused"))

        state = _make_state(high_anomaly_company_ids=[c1])
        # Must not raise
        result = await dispatch_high_anomalies(state, celery_app=celery_app)
        assert result is state

    @pytest.mark.asyncio
    async def test_state_is_returned_unchanged(self):
        """dispatch_high_anomalies returns the same state object."""
        c1 = uuid.uuid4()
        celery_app = MagicMock()
        celery_app.send_task = MagicMock()

        state = _make_state(high_anomaly_company_ids=[c1])
        result = await dispatch_high_anomalies(state, celery_app=celery_app)

        # State should be effectively the same (no meaningful mutations)
        assert result.workflow_id == state.workflow_id
        assert result.high_anomaly_company_ids == state.high_anomaly_company_ids
