"""
Unit tests for CostAccumulator.add_from_tokens and CostCeilingExceededError
attributes (TDD — written before implementation).
"""
from __future__ import annotations

import pytest

from src.events.cost_accumulator import CostAccumulator
from src.events.exceptions import CostCeilingExceededError


class TestAddFromTokensReturnsComputedCost:
    def test_add_from_tokens_returns_computed_cost(self) -> None:
        """add_from_tokens returns the exact cost computed by LLMPricingTable."""
        acc = CostAccumulator()
        # Haiku: 1000 in, 100 out → 1000*0.00025/1000 + 100*0.00125/1000 = 0.00025 + 0.000125 = 0.000375
        returned = acc.add_from_tokens("claude-haiku-4-5", 1000, 100)
        assert abs(returned - 0.000375) < 1e-9


class TestAddFromTokensIncrementsTotal:
    def test_add_from_tokens_increments_total(self) -> None:
        """add_from_tokens accumulates the computed cost into self.total."""
        acc = CostAccumulator()
        acc.add_from_tokens("claude-haiku-4-5", 1000, 100)  # 0.000375
        acc.add_from_tokens("claude-haiku-4-5", 1000, 100)  # 0.000375
        assert abs(acc.total - 0.00075) < 1e-9


class TestCheckCeilingRaisesWhenExceeded:
    def test_check_ceiling_raises_when_exceeded(self) -> None:
        """check_ceiling raises CostCeilingExceededError when total > ceiling."""
        acc = CostAccumulator()
        acc.add(0.06)
        with pytest.raises(CostCeilingExceededError):
            acc.check_ceiling(0.05)


class TestCheckCeilingPassesAtExactLimit:
    def test_check_ceiling_passes_at_exact_limit(self) -> None:
        """check_ceiling does NOT raise when total == ceiling (exclusive upper bound)."""
        acc = CostAccumulator()
        acc.add(0.05)
        # Must not raise
        acc.check_ceiling(0.05)


class TestCheckCeilingNotRaisedBelowLimit:
    def test_check_ceiling_not_raised_below_limit(self) -> None:
        """check_ceiling does not raise when total < ceiling."""
        acc = CostAccumulator()
        acc.add(0.04)
        acc.check_ceiling(0.05)  # Should not raise


class TestCostCeilingExceededErrorCarriesAttributes:
    def test_cost_ceiling_exceeded_error_carries_attributes(self) -> None:
        """CostCeilingExceededError must carry accumulated_usd and ceiling_usd."""
        acc = CostAccumulator()
        acc.add(0.06)
        with pytest.raises(CostCeilingExceededError) as exc_info:
            acc.check_ceiling(0.05)
        err = exc_info.value
        assert hasattr(err, "accumulated_usd"), "CostCeilingExceededError must have accumulated_usd"
        assert hasattr(err, "ceiling_usd"), "CostCeilingExceededError must have ceiling_usd"
        assert abs(err.accumulated_usd - 0.06) < 1e-9
        assert abs(err.ceiling_usd - 0.05) < 1e-9


class TestAddFromTokensUnknownModelPropagatesValueError:
    def test_add_from_tokens_unknown_model_propagates_value_error(self) -> None:
        """add_from_tokens propagates ValueError from LLMPricingTable for unknown model."""
        acc = CostAccumulator()
        with pytest.raises(ValueError, match="unknown model"):
            acc.add_from_tokens("gpt-4-turbo", 100, 10)
