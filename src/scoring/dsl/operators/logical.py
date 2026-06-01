"""Logical operator implementations for the scoring DSL (PLAN-F-003 TASK-006).

Provides LogicalOps — pure static methods for AND, OR, and IF.

Truthiness convention: any non-zero float is truthy; 0.0 is falsy.
All methods return ``float`` (1.0 for true, 0.0 for false, or the selected branch).
No I/O, no DB, no mutable state.
"""
from __future__ import annotations


class LogicalOps:
    """Pure static logical operator registry."""

    @staticmethod
    def and_op(*args: float) -> float:
        """Return 1.0 if all *args* are non-zero, else 0.0.

        ``AND(*args)`` — variadic; at least one argument expected.
        """
        return 1.0 if all(a != 0.0 for a in args) else 0.0

    @staticmethod
    def or_op(*args: float) -> float:
        """Return 1.0 if any *args* is non-zero, else 0.0.

        ``OR(*args)`` — variadic; at least one argument expected.
        """
        return 1.0 if any(a != 0.0 for a in args) else 0.0

    @staticmethod
    def if_op(condition: float, then_val: float, else_val: float) -> float:
        """Return *then_val* if *condition* != 0.0, else *else_val*.

        ``IF(condition, then_val, else_val)`` — ternary.
        """
        return then_val if condition != 0.0 else else_val
