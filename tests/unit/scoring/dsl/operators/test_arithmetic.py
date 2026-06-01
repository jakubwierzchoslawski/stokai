"""TDD tests for arithmetic DSL operators (PLAN-F-003 TASK-006).

Tests written before implementation.
AC-002: DSL indicator evaluates correctly.
"""
from __future__ import annotations

import pytest

from src.scoring.exceptions import DslEvalError


class TestArithmeticOperators:
    """Unit tests for the arithmetic operator registry."""

    @pytest.fixture
    def arith(self):
        from src.scoring.dsl.operators.arithmetic import ArithmeticOps
        return ArithmeticOps

    def test_add(self, arith):
        assert arith.add(3.0, 4.0) == pytest.approx(7.0)

    def test_subtract(self, arith):
        assert arith.subtract(10.0, 4.0) == pytest.approx(6.0)

    def test_multiply(self, arith):
        assert arith.multiply(3.0, 4.0) == pytest.approx(12.0)

    def test_divide(self, arith):
        assert arith.divide(10.0, 4.0) == pytest.approx(2.5)

    def test_power(self, arith):
        assert arith.power(2.0, 10.0) == pytest.approx(1024.0)

    def test_division_by_zero_raises_dsl_eval_error(self, arith):
        with pytest.raises(DslEvalError):
            arith.divide(5.0, 0.0)

    def test_comparison_gt_true(self, arith):
        assert arith.compare(">", 5.0, 3.0) == 1.0

    def test_comparison_gt_false(self, arith):
        assert arith.compare(">", 3.0, 5.0) == 0.0

    def test_comparison_lt_true(self, arith):
        assert arith.compare("<", 2.0, 5.0) == 1.0

    def test_comparison_gte(self, arith):
        assert arith.compare(">=", 5.0, 5.0) == 1.0

    def test_comparison_lte(self, arith):
        assert arith.compare("<=", 3.0, 5.0) == 1.0

    def test_comparison_eq(self, arith):
        assert arith.compare("==", 4.0, 4.0) == 1.0

    def test_comparison_neq(self, arith):
        assert arith.compare("!=", 4.0, 5.0) == 1.0

    def test_power_fractional_exponent(self, arith):
        """2^0.5 = sqrt(2)."""
        assert arith.power(2.0, 0.5) == pytest.approx(2.0 ** 0.5)
