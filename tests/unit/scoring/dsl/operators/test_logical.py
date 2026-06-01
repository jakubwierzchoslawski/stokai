"""TDD tests for logical DSL operators (PLAN-F-003 TASK-006).

Tests written before implementation.
AC-002: DSL indicator evaluates correctly.
"""
from __future__ import annotations

import pytest


class TestLogicalOperators:
    """Unit tests for the logical operator functions."""

    @pytest.fixture
    def logical(self):
        from src.scoring.dsl.operators.logical import LogicalOps
        return LogicalOps

    def test_and_all_truthy(self, logical):
        assert logical.and_op(1.0, 1.0, 1.0) == 1.0

    def test_and_one_falsy(self, logical):
        assert logical.and_op(1.0, 0.0, 1.0) == 0.0

    def test_and_all_falsy(self, logical):
        assert logical.and_op(0.0, 0.0) == 0.0

    def test_and_single_truthy(self, logical):
        assert logical.and_op(5.0) == 1.0

    def test_or_all_truthy(self, logical):
        assert logical.or_op(1.0, 1.0) == 1.0

    def test_or_one_truthy(self, logical):
        assert logical.or_op(0.0, 1.0, 0.0) == 1.0

    def test_or_all_falsy(self, logical):
        assert logical.or_op(0.0, 0.0) == 0.0

    def test_if_truthy_branch(self, logical):
        """IF(condition != 0, then_val, else_val) → then_val when condition != 0."""
        result = logical.if_op(1.0, 42.0, 0.0)
        assert result == pytest.approx(42.0)

    def test_if_falsy_branch(self, logical):
        """IF(condition == 0, then_val, else_val) → else_val when condition == 0."""
        result = logical.if_op(0.0, 42.0, -1.0)
        assert result == pytest.approx(-1.0)

    def test_if_nonzero_negative_condition_is_truthy(self, logical):
        """Negative non-zero values are truthy."""
        result = logical.if_op(-3.5, 10.0, 20.0)
        assert result == pytest.approx(10.0)
