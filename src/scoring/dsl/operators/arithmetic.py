"""Arithmetic operator implementations for the scoring DSL (PLAN-F-003 TASK-006).

Provides ArithmeticOps — a namespace class of pure static methods for the
five binary arithmetic operators (+, -, *, /, ^) and comparison operators.

All methods are pure functions: no I/O, no DB, no mutable state.
Division by zero and invalid comparisons raise ``DslEvalError``.
"""
from __future__ import annotations

from src.scoring.exceptions import DslEvalError

# Comparison operator dispatch table (keeps if-chain out of the hot path)
_CMP_TABLE: dict[str, object] = {
    ">":  lambda a, b: 1.0 if a > b else 0.0,
    "<":  lambda a, b: 1.0 if a < b else 0.0,
    ">=": lambda a, b: 1.0 if a >= b else 0.0,
    "<=": lambda a, b: 1.0 if a <= b else 0.0,
    "==": lambda a, b: 1.0 if a == b else 0.0,
    "!=": lambda a, b: 1.0 if a != b else 0.0,
}


class ArithmeticOps:
    """Pure static arithmetic operator registry.

    Each method corresponds to one binary operator in the DSL grammar.
    All methods return ``float``.
    """

    @staticmethod
    def add(a: float, b: float) -> float:
        """Return a + b."""
        return a + b

    @staticmethod
    def subtract(a: float, b: float) -> float:
        """Return a - b."""
        return a - b

    @staticmethod
    def multiply(a: float, b: float) -> float:
        """Return a * b."""
        return a * b

    @staticmethod
    def divide(a: float, b: float) -> float:
        """Return a / b.

        Raises
        ------
        DslEvalError
            When *b* is zero.
        """
        if b == 0.0:
            raise DslEvalError(
                f"Division by zero: attempted to divide {a!r} by 0.0 in DSL expression."
            )
        return a / b

    @staticmethod
    def power(a: float, b: float) -> float:
        """Return a ^ b (exponentiation)."""
        return a ** b

    @staticmethod
    def compare(op: str, a: float, b: float) -> float:
        """Evaluate a comparison operator.

        Parameters
        ----------
        op:
            One of: ``>``, ``<``, ``>=``, ``<=``, ``==``, ``!=``.

        Returns
        -------
        float
            1.0 if the comparison is True, 0.0 if False.

        Raises
        ------
        DslEvalError
            If *op* is not a recognised comparison operator.
        """
        fn = _CMP_TABLE.get(op)
        if fn is None:
            raise DslEvalError(
                f"Unknown comparison operator {op!r}. "
                f"Expected one of: {list(_CMP_TABLE)}"
            )
        return fn(a, b)  # type: ignore[call-arg]
