"""
Unit tests for WorkflowCostGuard.

TDD: written before implementation — PLAN-F-008 TASK-011.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from src.ai.workflows.watchlist_scan.cost_guard import (
    WorkflowBudgetExceededError,
    WorkflowCostGuard,
)
from src.ai.workflows.watchlist_scan.state import WatchlistScanState
from src.ai.workflows.state import WorkflowType


def _make_state(**kwargs) -> WatchlistScanState:
    defaults = {
        "workflow_id": uuid.uuid4(),
        "tenant_id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "started_at": datetime.now(tz=timezone.utc),
        "workflow_type": WorkflowType.WATCHLIST_SCAN,
    }
    defaults.update(kwargs)
    return WatchlistScanState(**defaults)


class TestWorkflowCostGuard:
    def test_cost_guard_accumulates_cost_on_state(self):
        """Assert state.cost_usd incremented after each call."""
        guard = WorkflowCostGuard(ceiling_usd=1.00)
        state = _make_state(cost_usd=0.0)

        guard.check_and_accumulate(state, 0.10)
        assert abs(state.cost_usd - 0.10) < 1e-9

        guard.check_and_accumulate(state, 0.20)
        assert abs(state.cost_usd - 0.30) < 1e-9

    def test_cost_guard_raises_when_ceiling_exceeded(self):
        """Cumulative cost exceeds ceiling; assert WorkflowBudgetExceededError raised."""
        guard = WorkflowCostGuard(ceiling_usd=0.50)
        state = _make_state(cost_usd=0.45)

        with pytest.raises(WorkflowBudgetExceededError) as exc_info:
            guard.check_and_accumulate(state, 0.10)  # 0.45 + 0.10 = 0.55 > 0.50

        assert exc_info.value.current_cost_usd > 0.50
        assert exc_info.value.ceiling_usd == 0.50

    def test_cost_guard_does_not_raise_at_exactly_ceiling(self):
        """No exception when cost_usd == ceiling_usd (ceiling is inclusive)."""
        guard = WorkflowCostGuard(ceiling_usd=1.00)
        state = _make_state(cost_usd=0.90)

        # This brings cost exactly to 1.00, which should NOT raise
        guard.check_and_accumulate(state, 0.10)

        assert abs(state.cost_usd - 1.00) < 1e-9

    def test_cost_guard_error_carries_workflow_id(self):
        """Assert exception workflow_id matches state.workflow_id."""
        wf_id = uuid.uuid4()
        guard = WorkflowCostGuard(ceiling_usd=0.10)
        state = _make_state(workflow_id=wf_id, cost_usd=0.05)

        with pytest.raises(WorkflowBudgetExceededError) as exc_info:
            guard.check_and_accumulate(state, 0.10)  # 0.15 > 0.10

        assert exc_info.value.workflow_id == wf_id

    def test_cost_guard_raises_on_non_positive_ceiling(self):
        """Constructor raises ValueError when ceiling_usd <= 0."""
        with pytest.raises(ValueError):
            WorkflowCostGuard(ceiling_usd=0.0)

        with pytest.raises(ValueError):
            WorkflowCostGuard(ceiling_usd=-1.0)

    def test_cost_guard_error_has_current_cost_usd(self):
        """Error carries the actual accumulated cost."""
        guard = WorkflowCostGuard(ceiling_usd=0.50)
        state = _make_state(cost_usd=0.40)

        with pytest.raises(WorkflowBudgetExceededError) as exc_info:
            guard.check_and_accumulate(state, 0.20)  # 0.60 > 0.50

        assert abs(exc_info.value.current_cost_usd - 0.60) < 1e-9
