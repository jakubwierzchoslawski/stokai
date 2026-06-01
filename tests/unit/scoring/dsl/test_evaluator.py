"""TDD tests for ConcreteDslEvaluator (PLAN-F-003 TASK-007).

Tests written before implementation (red phase).
AC-002: DSL indicator with RANK_SECTOR and ZSCORE evaluates correctly.
"""
from __future__ import annotations

import concurrent.futures
import uuid

import pytest

from src.scoring.exceptions import DslEvalError, DslParseError


class TestDslEvaluatorConstants:
    """Tests for constant/literal evaluation."""

    @pytest.fixture
    def evaluator(self):
        from src.scoring.dsl.evaluator import ConcreteDslEvaluator
        return ConcreteDslEvaluator()

    def test_evaluate_constant_expression(self, evaluator):
        """'42' with empty context → 42.0."""
        result = evaluator.evaluate("42", {})
        assert result == pytest.approx(42.0)

    def test_evaluate_float_constant(self, evaluator):
        """'3.14' → 3.14."""
        result = evaluator.evaluate("3.14", {})
        assert result == pytest.approx(3.14)


class TestDslEvaluatorIdentifiers:
    """Tests for identifier lookup."""

    @pytest.fixture
    def evaluator(self):
        from src.scoring.dsl.evaluator import ConcreteDslEvaluator
        return ConcreteDslEvaluator()

    def test_evaluate_identifier_lookup(self, evaluator):
        """'revenue_growth' with context {"revenue_growth": 0.15} → 0.15."""
        result = evaluator.evaluate("revenue_growth", {"revenue_growth": 0.15})
        assert result == pytest.approx(0.15)

    def test_evaluate_unknown_identifier_raises_dsl_eval_error(self, evaluator):
        """Missing context key raises DslEvalError."""
        with pytest.raises(DslEvalError):
            evaluator.evaluate("missing_key", {})


class TestDslEvaluatorArithmetic:
    """Tests for arithmetic expression evaluation."""

    @pytest.fixture
    def evaluator(self):
        from src.scoring.dsl.evaluator import ConcreteDslEvaluator
        return ConcreteDslEvaluator()

    def test_evaluate_arithmetic_expression(self, evaluator):
        """'price * pe_ratio' → correct product."""
        ctx = {"price": 50.0, "pe_ratio": 20.0}
        result = evaluator.evaluate("price * pe_ratio", ctx)
        assert result == pytest.approx(1000.0)

    def test_evaluate_addition(self, evaluator):
        result = evaluator.evaluate("2 + 3", {})
        assert result == pytest.approx(5.0)

    def test_evaluate_precedence(self, evaluator):
        """'2 + 3 * 4' = 14."""
        result = evaluator.evaluate("2 + 3 * 4", {})
        assert result == pytest.approx(14.0)

    def test_evaluate_power(self, evaluator):
        """'2 ^ 8' = 256."""
        result = evaluator.evaluate("2 ^ 8", {})
        assert result == pytest.approx(256.0)

    def test_evaluate_division_by_zero_raises(self, evaluator):
        with pytest.raises(DslEvalError):
            evaluator.evaluate("10 / 0", {})

    def test_evaluate_comparison_produces_float(self, evaluator):
        """'x > 0' → 1.0 when x=5."""
        result = evaluator.evaluate("x > 0", {"x": 5.0})
        assert result == pytest.approx(1.0)


class TestDslEvaluatorFunctions:
    """Tests for built-in function evaluation."""

    @pytest.fixture
    def evaluator(self):
        from src.scoring.dsl.evaluator import ConcreteDslEvaluator
        return ConcreteDslEvaluator()

    def test_evaluate_if_truthy(self, evaluator):
        result = evaluator.evaluate("IF(1, 42, 0)", {})
        assert result == pytest.approx(42.0)

    def test_evaluate_if_with_comparison(self, evaluator):
        """'IF(x > 0, x, 0)' with x=5 → 5."""
        result = evaluator.evaluate("IF(x > 0, x, 0)", {"x": 5.0})
        assert result == pytest.approx(5.0)

    def test_evaluate_if_falsy(self, evaluator):
        result = evaluator.evaluate("IF(0, 42, 99)", {})
        assert result == pytest.approx(99.0)

    def test_evaluate_and_operator(self, evaluator):
        result = evaluator.evaluate("AND(1, 1)", {})
        assert result == pytest.approx(1.0)

    def test_evaluate_or_operator(self, evaluator):
        result = evaluator.evaluate("OR(0, 0)", {})
        assert result == pytest.approx(0.0)

    def test_evaluate_unknown_function_raises_dsl_eval_error(self, evaluator):
        """Unknown function name raises DslEvalError."""
        with pytest.raises(DslEvalError):
            evaluator.evaluate("UNKNOWN_FUNC(1)", {})

    def test_evaluate_rank_sector_in_expression(self, evaluator):
        """DSL mixing RANK_SECTOR with arithmetic resolves correctly.

        RANK_SECTOR(3, 1, 2, 3, 4, 5) = rank 3, then * 2 = 6.

        Note: the evaluator passes the first argument as value, rest as peers.
        """
        ctx = {
            "val": 3.0,
            "p1": 1.0, "p2": 2.0, "p3": 3.0, "p4": 4.0, "p5": 5.0,
        }
        result = evaluator.evaluate("RANK_SECTOR(val, p1, p2, p3, p4, p5) * 2", ctx)
        # rank=3, *2 = 6
        assert result == pytest.approx(6.0)

    def test_evaluate_zscore_known(self, evaluator):
        """ZSCORE of a series passed via context list variable.

        series=[1,2,3,4,5], last=5, mean=3, pop_std=sqrt(2)≈1.414
        z = (5-3)/sqrt(2) ≈ 1.414
        """
        ctx = {
            "s1": 1.0, "s2": 2.0, "s3": 3.0, "s4": 4.0, "s5": 5.0,
        }
        result = evaluator.evaluate("ZSCORE(s1, s2, s3, s4, s5)", ctx)
        import math
        expected = (5.0 - 3.0) / math.sqrt(2)
        assert result == pytest.approx(expected, rel=1e-6)


class TestDslEvaluatorComplex:
    """Tests for complex nested DSL expressions."""

    @pytest.fixture
    def evaluator(self):
        from src.scoring.dsl.evaluator import ConcreteDslEvaluator
        return ConcreteDslEvaluator()

    def test_evaluate_matches_reference_implementation(self, evaluator):
        """Reference implementation test: RANK_SECTOR + ZSCORE combination.

        DSL: RANK_SECTOR(pe_ratio, p1, p2, p3, p4, p5) + ZSCORE(r1, r2, r3, r4, r5)

        Context:
            pe_ratio=3.0, peers=[1,2,3,4,5] → RANK=3
            returns series=[2,4,4,4,5,5,7,9]
            mean=5, pop_std=2, last=9, z=(9-5)/2=2.0

        Expected: 3.0 + 2.0 = 5.0
        """
        ctx = {
            "pe_ratio": 3.0,
            "p1": 1.0, "p2": 2.0, "p3": 3.0, "p4": 4.0, "p5": 5.0,
            "r1": 2.0, "r2": 4.0, "r3": 4.0, "r4": 4.0,
            "r5": 5.0, "r6": 5.0, "r7": 7.0, "r8": 9.0,
        }
        dsl = (
            "RANK_SECTOR(pe_ratio, p1, p2, p3, p4, p5) + "
            "ZSCORE(r1, r2, r3, r4, r5, r6, r7, r8)"
        )
        result = evaluator.evaluate(dsl, ctx)
        assert result == pytest.approx(5.0, rel=1e-6)

    def test_evaluate_nested_operators(self, evaluator):
        """IF(RANK_SECTOR(val, a, b, c) > 2, val * 2, val) where val=3 among [1,2,3]."""
        ctx = {"val": 3.0, "a": 1.0, "b": 2.0, "c": 3.0}
        result = evaluator.evaluate("IF(RANK_SECTOR(val, a, b, c) > 2, val * 2, val)", ctx)
        # RANK_SECTOR(3, [1,2,3]) = 3 > 2 → True → 3*2=6
        assert result == pytest.approx(6.0)

    def test_evaluate_is_thread_safe(self, evaluator):
        """Concurrent calls with different contexts produce independent correct results."""
        def compute(x_val: float) -> float:
            return evaluator.evaluate("x * 2 + 1", {"x": x_val})

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            futures = {pool.submit(compute, float(i)): i for i in range(50)}
            for future, i in futures.items():
                expected = float(i) * 2.0 + 1.0
                assert future.result() == pytest.approx(expected)


class TestDslEvaluatorErrors:
    """Tests for error propagation."""

    @pytest.fixture
    def evaluator(self):
        from src.scoring.dsl.evaluator import ConcreteDslEvaluator
        return ConcreteDslEvaluator()

    def test_bad_syntax_raises_dsl_parse_error(self, evaluator):
        """Malformed DSL propagates DslParseError."""
        with pytest.raises(DslParseError):
            evaluator.evaluate("1 +", {})

    def test_empty_expression_raises_dsl_parse_error(self, evaluator):
        with pytest.raises(DslParseError):
            evaluator.evaluate("", {})
