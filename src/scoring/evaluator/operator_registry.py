"""Operator and function registry for the AST evaluator.

Maps operator tokens and function names to Python callables.
"""
from __future__ import annotations

import math
import operator
from typing import Any, Callable


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class DslEvalError(Exception):
    """Raised when evaluation of a DSL formula fails at runtime."""


# ---------------------------------------------------------------------------
# Binary operator dispatch
# ---------------------------------------------------------------------------

_BINARY_OPS: dict[str, Callable[[Any, Any], Any]] = {
    "+": operator.add,
    "-": operator.sub,
    "*": operator.mul,
    "/": operator.truediv,
    "^": operator.pow,
    ">": operator.gt,
    "<": operator.lt,
    ">=": operator.ge,
    "<=": operator.le,
    "==": operator.eq,
    "!=": operator.ne,
    "AND": lambda a, b: bool(a) and bool(b),
    "OR": lambda a, b: bool(a) or bool(b),
}

# ---------------------------------------------------------------------------
# Built-in function implementations (synchronous — evaluated over pre-fetched data)
# ---------------------------------------------------------------------------

def _fn_if(args: list[Any], kwargs: dict[str, Any]) -> Any:
    """IF(condition, then_value, else_value)"""
    if len(args) != 3:
        raise DslEvalError("IF() requires exactly 3 arguments")
    return args[1] if args[0] else args[2]


def _fn_abs(args: list[Any], kwargs: dict[str, Any]) -> float:
    if len(args) != 1:
        raise DslEvalError("ABS() requires exactly 1 argument")
    return abs(args[0])


def _fn_log(args: list[Any], kwargs: dict[str, Any]) -> float:
    if len(args) not in (1, 2):
        raise DslEvalError("LOG() requires 1 or 2 arguments")
    if len(args) == 2:
        return math.log(args[0], args[1])
    return math.log(args[0])


def _fn_min(args: list[Any], kwargs: dict[str, Any]) -> float:
    if not args:
        raise DslEvalError("MIN() requires at least 1 argument")
    return min(args)


def _fn_max(args: list[Any], kwargs: dict[str, Any]) -> float:
    if not args:
        raise DslEvalError("MAX() requires at least 1 argument")
    return max(args)


def _fn_rank(args: list[Any], kwargs: dict[str, Any]) -> float:
    """RANK(value, peer_values=[...]) — returns percentile rank in peer set.

    In the evaluator context, peer_values are passed as a list via kwargs or
    pre-computed by the BenchmarkEngine. Here we handle the simple case where
    peer_values is provided directly.
    """
    if not args:
        raise DslEvalError("RANK() requires at least 1 argument (the value)")
    value = args[0]
    peer_values = kwargs.get("peer_values", [])
    if not peer_values:
        return 50.0  # no peers: return median
    sorted_peers = sorted(peer_values)
    below = sum(1 for p in sorted_peers if p < value)
    return (below / len(sorted_peers)) * 100.0


def _fn_zscore(args: list[Any], kwargs: dict[str, Any]) -> float:
    """ZSCORE(value, mean=..., std=...)"""
    if not args:
        raise DslEvalError("ZSCORE() requires at least 1 argument (the value)")
    value = args[0]
    mean = kwargs.get("mean", 0.0)
    std = kwargs.get("std", 1.0)
    if std == 0:
        return 0.0
    return (value - mean) / std


def _fn_percentile(args: list[Any], kwargs: dict[str, Any]) -> float:
    """PERCENTILE(value, peer_values=[...]) — alias of RANK."""
    return _fn_rank(args, kwargs)


_FUNCTIONS: dict[str, Callable[[list[Any], dict[str, Any]], Any]] = {
    "IF": _fn_if,
    "ABS": _fn_abs,
    "LOG": _fn_log,
    "MIN": _fn_min,
    "MAX": _fn_max,
    "RANK": _fn_rank,
    "ZSCORE": _fn_zscore,
    "PERCENTILE": _fn_percentile,
}


class OperatorRegistry:
    """Provides dispatch for binary operators and built-in functions."""

    def apply_binary(self, op: str, left: Any, right: Any) -> Any:
        fn = _BINARY_OPS.get(op)
        if fn is None:
            raise DslEvalError(f"Unknown binary operator: {op!r}")
        return fn(left, right)

    def apply_unary(self, op: str, operand: Any) -> Any:
        if op == "-":
            return -operand
        if op == "NOT":
            return not operand
        raise DslEvalError(f"Unknown unary operator: {op!r}")

    def call_function(self, name: str, args: list[Any], kwargs: dict[str, Any]) -> Any:
        fn = _FUNCTIONS.get(name.upper())
        if fn is None:
            raise DslEvalError(f"Unknown function: {name!r}")
        return fn(args, kwargs)
