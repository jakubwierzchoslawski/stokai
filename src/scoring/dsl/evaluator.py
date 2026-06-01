"""Recursive AST interpreter for the scoring DSL (PLAN-F-003 TASK-007).

Implements ``ConcreteDslEvaluator`` satisfying the ``DslEvaluator`` Protocol.

Design
------
- ``evaluate(dsl_expression, context)`` parses the expression via ``DslParser``
  and then recursively evaluates the resulting AST via ``_eval(node, context)``.
- Each call is fully stateless: no shared mutable state between invocations,
  making the evaluator thread-safe (verified by test_evaluate_is_thread_safe).
- Operator dispatch uses the module-level ``OPERATOR_REGISTRY`` dict (read-only
  after import) — adding a new operator requires only a new registry entry, not
  a change to this file (OCP).
- Binary arithmetic and comparison operators (+, -, *, /, ^, >, <, etc.) are
  dispatched through ``ArithmeticOps`` rather than the function registry.

Function call argument convention
----------------------------------
Most DSL functions receive their arguments as flat floats:
    IF(cond, then, else)  → if_op(cond_float, then_float, else_float)
    AND(a, b, c)          → and_op(a, b, c)

Variadic sequence functions (RANK_SECTOR, PERCENTILE, CHANGE, CAGR, CORR, ZSCORE)
receive arguments that may be interpreted as a value + peer list or a series:
    RANK_SECTOR(value, peer1, peer2, ...) → rank_sector(value, [peer1, peer2, ...])
    PERCENTILE(value, peer1, ...)         → percentile(value, [peer1, ...])
    ZSCORE(s1, s2, ..., sN)               → zscore([s1, s2, ..., sN])
    CHANGE(s1, ..., sN, periods)          → change([s1..sN-1], int(periods))
    CAGR(s1, ..., sN, years)              → cagr([s1..sN-1], years)
    CORR(a1,..,aN, b1,..,bN)             → corr(first_half, second_half)

See ``_dispatch_function`` for the full argument-unwrapping logic.
"""
from __future__ import annotations

from src.scoring.dsl.ast_nodes import BinaryOp, Expr, FunctionCall, IdentifierRef, Literal_
from src.scoring.dsl.operators import OPERATOR_REGISTRY
from src.scoring.dsl.operators.arithmetic import ArithmeticOps
from src.scoring.dsl.parser import DslParser
from src.scoring.exceptions import DslEvalError

# Binary operator dispatch map: op string → ArithmeticOps method
_BINARY_OPS: dict[str, object] = {
    "+":  ArithmeticOps.add,
    "-":  ArithmeticOps.subtract,
    "*":  ArithmeticOps.multiply,
    "/":  ArithmeticOps.divide,
    "^":  ArithmeticOps.power,
    ">":  lambda a, b: ArithmeticOps.compare(">", a, b),
    "<":  lambda a, b: ArithmeticOps.compare("<", a, b),
    ">=": lambda a, b: ArithmeticOps.compare(">=", a, b),
    "<=": lambda a, b: ArithmeticOps.compare("<=", a, b),
    "==": lambda a, b: ArithmeticOps.compare("==", a, b),
    "!=": lambda a, b: ArithmeticOps.compare("!=", a, b),
}

# Functions that receive a flat arg list (value + peers unpacked into list)
_VALUE_PEER_FUNCS = frozenset({"RANK_SECTOR", "PERCENTILE"})

# Functions that receive all args as a series list
_SERIES_FUNCS = frozenset({"ZSCORE"})

# Functions that receive series + terminal scalar (last arg is scalar)
_SERIES_SCALAR_FUNCS = frozenset({"CHANGE", "CAGR"})

# CORR: two equal-length series; args split in half
_DUAL_SERIES_FUNCS = frozenset({"CORR"})

# Flat variadic functions (each arg passed as individual positional float)
_FLAT_VARIADIC_FUNCS = frozenset({"AND", "OR", "IF"})


def _dispatch_function(name: str, evaluated_args: list[float]) -> float:
    """Dispatch a named function call with pre-evaluated float arguments.

    Translates the flat list of evaluated float arguments into the specific
    calling convention expected by each operator family.

    Raises
    ------
    DslEvalError
        When the function name is unknown or argument counts are invalid.
    """
    fn = OPERATOR_REGISTRY.get(name)
    if fn is None:
        raise DslEvalError(
            f"Unknown DSL function {name!r}. "
            f"Registered functions: {sorted(OPERATOR_REGISTRY)}"
        )

    if name in _FLAT_VARIADIC_FUNCS:
        # AND, OR, IF — pass all args as positional floats
        return fn(*evaluated_args)  # type: ignore[call-arg]

    if name in _VALUE_PEER_FUNCS:
        # RANK_SECTOR(value, peer1, peer2, ...) / PERCENTILE(value, peer1, ...)
        if len(evaluated_args) < 2:
            raise DslEvalError(
                f"{name} requires at least 2 arguments (value + at least one peer)."
            )
        value = evaluated_args[0]
        peers = evaluated_args[1:]
        return fn(value, peers)  # type: ignore[call-arg]

    if name in _SERIES_FUNCS:
        # ZSCORE(s1, s2, ..., sN)
        if len(evaluated_args) < 2:
            raise DslEvalError(
                f"{name} requires at least 2 series elements."
            )
        return fn(evaluated_args)  # type: ignore[call-arg]

    if name in _SERIES_SCALAR_FUNCS:
        # CHANGE(s1,...,sN, periods) or CAGR(s1,...,sN, years)
        # Last arg is the scalar; preceding args are the series
        if len(evaluated_args) < 3:
            raise DslEvalError(
                f"{name} requires at least 2 series elements plus the periods/years scalar."
            )
        scalar = evaluated_args[-1]
        series = evaluated_args[:-1]
        if name == "CHANGE":
            periods = int(scalar)
            return fn(series, periods)  # type: ignore[call-arg]
        else:  # CAGR
            return fn(series, scalar)  # type: ignore[call-arg]

    if name in _DUAL_SERIES_FUNCS:
        # CORR(a1,...,aN, b1,...,bN) — args split in half
        if len(evaluated_args) < 4 or len(evaluated_args) % 2 != 0:
            raise DslEvalError(
                f"CORR requires an even number of arguments >= 4 (two equal-length series)."
            )
        mid = len(evaluated_args) // 2
        series_a = evaluated_args[:mid]
        series_b = evaluated_args[mid:]
        return fn(series_a, series_b)  # type: ignore[call-arg]

    # Fallback: pass as flat positional args
    return fn(*evaluated_args)  # type: ignore[call-arg]


class ConcreteDslEvaluator:
    """Recursive AST interpreter satisfying the ``DslEvaluator`` Protocol.

    Thread-safe: ``evaluate()`` creates a fresh parser and context snapshot
    on each call.  No shared mutable instance state.
    """

    def __init__(self) -> None:
        self._parser = DslParser()

    def evaluate(self, dsl_expression: str, context: dict[str, float]) -> float:
        """Parse *dsl_expression* and evaluate it using *context*.

        Parameters
        ----------
        dsl_expression:
            A valid DSL expression string (will be parsed fresh each call).
        context:
            A mapping from identifier names to their float values.

        Returns
        -------
        float
            The result of evaluating the expression.

        Raises
        ------
        DslParseError
            If the expression has invalid syntax.
        DslEvalError
            If evaluation fails (missing key, division by zero, etc.).
        """
        ast = self._parser.parse(dsl_expression)
        return self._eval(ast, context)

    def _eval(self, node: Expr, context: dict[str, float]) -> float:
        """Recursively evaluate an AST node."""
        if isinstance(node, Literal_):
            return node.value

        if isinstance(node, IdentifierRef):
            key = node.name
            if key not in context:
                raise DslEvalError(
                    f"Identifier {key!r} not found in evaluation context. "
                    f"Available keys: {sorted(context)}"
                )
            return float(context[key])

        if isinstance(node, BinaryOp):
            left = self._eval(node.left, context)
            right = self._eval(node.right, context)
            op_fn = _BINARY_OPS.get(node.op)
            if op_fn is None:
                raise DslEvalError(
                    f"Unknown binary operator {node.op!r} in AST."
                )
            return op_fn(left, right)  # type: ignore[call-arg]

        if isinstance(node, FunctionCall):
            evaluated_args = [self._eval(arg, context) for arg in node.args]
            return _dispatch_function(node.name, evaluated_args)

        raise DslEvalError(
            f"Unknown AST node type {type(node).__name__!r}. "
            "This is an internal error in the DSL evaluator."
        )
