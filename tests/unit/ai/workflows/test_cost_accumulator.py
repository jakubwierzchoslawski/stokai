"""
Unit tests for CostAccumulator (PLAN-F-010 TASK-003).

TDD: written before implementation.
"""
from __future__ import annotations

import pytest

from src.ai.workflows.event_deep_dive.cost_accumulator import CostAccumulator
from src.ai.workflows.event_deep_dive.exceptions import CostCeilingExceededError


class TestCostAccumulator:
    def test_add_accumulates_correctly(self):
        """add() increments total_usd."""
        acc = CostAccumulator(ceiling_usd=1.0)
        acc.add(0.10)
        acc.add(0.20)
        assert acc.total_usd == pytest.approx(0.30)

    def test_add_raises_before_adding_when_ceiling_exceeded(self):
        """add() raises CostCeilingExceededError BEFORE adding when total + amount >= ceiling."""
        acc = CostAccumulator(ceiling_usd=0.50)
        acc.add(0.40)
        # Next add would push total to 0.90 >= 0.50 → must raise before adding
        with pytest.raises(CostCeilingExceededError) as exc_info:
            acc.add(0.15)
        # total must NOT have changed
        assert acc.total_usd == pytest.approx(0.40)
        err = exc_info.value
        assert err.cost_accumulated == pytest.approx(0.40)

    def test_add_raises_exactly_at_ceiling(self):
        """add() raises when total + amount == ceiling exactly."""
        acc = CostAccumulator(ceiling_usd=0.50)
        acc.add(0.25)
        with pytest.raises(CostCeilingExceededError):
            acc.add(0.25)

    def test_error_has_to_dict(self):
        """CostCeilingExceededError.to_dict() returns a JSON-serializable dict."""
        acc = CostAccumulator(ceiling_usd=1.0)
        acc.add(0.80)
        try:
            acc.add(0.30)
        except CostCeilingExceededError as exc:
            d = exc.to_dict()
            assert "error" in d
            assert "cost_accumulated" in d
            assert "ceiling_usd" in d

    def test_zero_add_is_allowed(self):
        """Adding 0.0 is valid and does not raise."""
        acc = CostAccumulator(ceiling_usd=1.0)
        acc.add(0.0)
        assert acc.total_usd == pytest.approx(0.0)
