"""
Unit tests for MorningBrief CostGuard.

TDD: PLAN-F-006 TASK-014

AC covered: AC-001 (cost <= $2.00 enforced at runtime), REQ-N-004
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
import logging

import pytest

from src.ai.workflows.morning_brief_state import MorningBriefState
from src.ai.workflows.morning_brief.cost_guard import CostGuard
from src.ai.workflows.morning_brief_nodes import WorkflowCostCeilingExceeded


def _make_state(cost_usd: float = 0.0, **kwargs) -> MorningBriefState:
    defaults = {
        "workflow_id": uuid.uuid4(),
        "tenant_id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "started_at": datetime.now(tz=timezone.utc),
        "cost_usd": cost_usd,
    }
    defaults.update(kwargs)
    return MorningBriefState(**defaults)


class TestCostGuard:
    def test_cost_guard_allows_below_ceiling(self):
        """check() must pass without warning when cost < 80% of ceiling."""
        guard = CostGuard(cost_ceiling_usd=2.00)
        state = _make_state(cost_usd=0.50)
        result = guard.check(state)
        # Must not raise; state returned unchanged
        assert result.cost_usd == pytest.approx(0.50)

    def test_cost_guard_warns_at_80_pct(self, caplog):
        """check() must log WARNING and call reduce_token_budgets at >= 80%."""
        guard = CostGuard(cost_ceiling_usd=2.00)
        state = _make_state(cost_usd=1.62)  # 81% of $2.00

        with caplog.at_level(logging.WARNING):
            result = guard.check(state)

        assert any(
            "cost_ceiling_approach" in r.message or "ceiling" in r.message.lower()
            for r in caplog.records
        )
        # token_budget_override must be injected
        assert "token_budget_override" in result.inputs

    def test_cost_guard_raises_at_ceiling(self):
        """check() must raise WorkflowCostCeilingExceeded when cost >= ceiling."""
        guard = CostGuard(cost_ceiling_usd=2.00)
        state = _make_state(cost_usd=2.01)

        with pytest.raises(WorkflowCostCeilingExceeded):
            guard.check(state)

    def test_cost_guard_raises_exactly_at_ceiling(self):
        """check() must raise WorkflowCostCeilingExceeded at exactly the ceiling."""
        guard = CostGuard(cost_ceiling_usd=2.00)
        state = _make_state(cost_usd=2.00)

        with pytest.raises(WorkflowCostCeilingExceeded):
            guard.check(state)

    def test_cost_guard_reduce_token_budgets_injects_override(self):
        """reduce_token_budgets() must inject token_budget_override into state.inputs."""
        guard = CostGuard(cost_ceiling_usd=2.00)
        state = _make_state()

        result = guard.reduce_token_budgets(state)

        assert "token_budget_override" in result.inputs
        override = result.inputs["token_budget_override"]
        assert isinstance(override, dict)
        assert len(override) > 0
        # All values should be positive integers (halved budgets)
        for agent, budget in override.items():
            assert isinstance(budget, int)
            assert budget > 0

    def test_cost_guard_rejects_non_positive_ceiling(self):
        """CostGuard must raise ValueError for non-positive ceiling."""
        with pytest.raises(ValueError):
            CostGuard(cost_ceiling_usd=0.0)

    def test_cost_guard_below_80_pct_no_warning(self, caplog):
        """check() must not log a warning when cost < 80% of ceiling."""
        guard = CostGuard(cost_ceiling_usd=2.00)
        state = _make_state(cost_usd=1.59)  # 79.5% — below threshold

        with caplog.at_level(logging.WARNING):
            guard.check(state)

        warning_records = [
            r for r in caplog.records
            if r.levelno >= logging.WARNING
            and ("ceiling" in r.message.lower() or "cost" in r.message.lower())
        ]
        assert len(warning_records) == 0

    def test_cost_guard_warn_only_once(self, caplog):
        """check() must log WARNING at 80% only once, not on subsequent calls."""
        guard = CostGuard(cost_ceiling_usd=2.00)
        state = _make_state(cost_usd=1.65)

        with caplog.at_level(logging.WARNING):
            guard.check(state)
            guard.check(state)  # second call should not log another WARNING

        warning_records = [
            r for r in caplog.records
            if "ceiling" in r.message.lower() or "approach" in r.message.lower()
        ]
        assert len(warning_records) == 1
