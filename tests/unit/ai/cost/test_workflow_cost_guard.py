"""
Unit tests for WorkflowCostGuard (PLAN-N-004 TASK-002).

TDD: tests were written before the implementation.
All tests use a minimal WorkflowState stub to isolate guard logic from
LangGraph state machinery.

Seed: deterministic — no randomness.
"""
from __future__ import annotations

import logging
from decimal import Decimal
from uuid import uuid4

import pytest

from src.ai.cost.workflow_cost_guard import WorkflowCostGuard
from src.ai.cost.errors import WorkflowBudgetExceededError


# ── Minimal state stub ────────────────────────────────────────────────────────

class _State:
    """Minimal mutable workflow state stub for guard tests."""

    def __init__(self, cost_usd: float = 0.0) -> None:
        self.cost_usd = cost_usd
        self.workflow_id = uuid4()


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_guard_allows_cost_below_ceiling(caplog) -> None:
    """Accumulated $0.50 against $2.00 ceiling; no exception and no warning."""
    guard = WorkflowCostGuard("morning_brief", 2.00, uuid4())
    state = _State(cost_usd=0.0)

    with caplog.at_level(logging.WARNING):
        guard.check_and_accumulate(state, 0.50)

    assert state.cost_usd == pytest.approx(0.50)
    assert "WARNING" not in caplog.text
    assert "ceiling" not in caplog.text.lower()


def test_guard_warns_at_80_pct_threshold(caplog) -> None:
    """Accumulated $1.61 against $2.00 crosses 80%; WARNING logged, no exception."""
    guard = WorkflowCostGuard("morning_brief", 2.00, uuid4())
    state = _State(cost_usd=0.0)

    with caplog.at_level(logging.WARNING):
        guard.check_and_accumulate(state, 1.61)

    assert state.cost_usd == pytest.approx(1.61)
    # WARNING should have been emitted
    warning_records = [r for r in caplog.records if r.levelname == "WARNING"]
    assert len(warning_records) >= 1
    assert "80" in warning_records[0].message or "80.5" in warning_records[0].message or "pct" in warning_records[0].message.lower() or "%" in warning_records[0].message


def test_guard_warns_only_once_per_run(caplog) -> None:
    """WARNING is emitted exactly once even if 80% is crossed on two consecutive calls."""
    guard = WorkflowCostGuard("morning_brief", 2.00, uuid4())
    state = _State(cost_usd=0.0)

    with caplog.at_level(logging.WARNING):
        guard.check_and_accumulate(state, 1.61)  # first crossing
        guard.check_and_accumulate(state, 0.10)  # still above 80%

    warning_records = [r for r in caplog.records if r.levelname == "WARNING"]
    assert len(warning_records) == 1


def test_guard_raises_at_ceiling() -> None:
    """Accumulated exactly $2.00 against a $2.00 ceiling; WorkflowBudgetExceededError raised."""
    workflow_id = uuid4()
    guard = WorkflowCostGuard("morning_brief", 2.00, workflow_id)
    state = _State(cost_usd=0.0)

    with pytest.raises(WorkflowBudgetExceededError) as exc_info:
        guard.check_and_accumulate(state, 2.00)

    err = exc_info.value
    assert err.ceiling_usd == pytest.approx(2.00)
    assert err.accumulated_usd == pytest.approx(2.00)
    assert err.workflow_id == workflow_id
    assert err.workflow_type == "morning_brief"


def test_guard_raises_when_single_agent_exceeds_ceiling() -> None:
    """Single agent call costing $2.50 against $2.00 ceiling raises immediately."""
    guard = WorkflowCostGuard("event_deep_dive", 2.00, uuid4())
    state = _State(cost_usd=0.0)

    with pytest.raises(WorkflowBudgetExceededError) as exc_info:
        guard.check_and_accumulate(state, 2.50)

    assert exc_info.value.accumulated_usd == pytest.approx(2.50)
    assert exc_info.value.ceiling_usd == pytest.approx(2.00)


def test_guard_uses_decimal_for_accumulation() -> None:
    """7 calls each adding $0.285714 against $2.00 ceiling; no floating-point false positive.

    In pure float arithmetic, 7 * 0.285714 = 1.999998 which is < 2.00 so this
    should NOT raise.  The guard uses Decimal internally to prevent drift.
    """
    guard = WorkflowCostGuard("morning_brief", 2.00, uuid4())
    state = _State(cost_usd=0.0)

    # 7 * 0.285714 = 1.999998 — must NOT exceed $2.00 ceiling
    for _ in range(7):
        guard.check_and_accumulate(state, 0.285714)

    # Should be fine — no exception raised
    assert state.cost_usd == pytest.approx(7 * 0.285714)


def test_guard_updates_state_cost_usd() -> None:
    """After check_and_accumulate(state, 0.10), state.cost_usd is prior + 0.10."""
    guard = WorkflowCostGuard("watchlist_scan", 1.00, uuid4())
    state = _State(cost_usd=0.30)

    guard.check_and_accumulate(state, 0.10)

    assert state.cost_usd == pytest.approx(0.40)
