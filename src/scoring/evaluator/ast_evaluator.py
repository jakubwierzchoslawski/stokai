"""AST evaluator for the scoring DSL.

Walks an AstNode tree and produces a float (or None on null-propagation).
All company data access goes through injected provider interfaces.
"""
from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

from src.scoring.dsl.ast_nodes import (
    AstNode,
    BinaryOp,
    ConditionalExpr,
    FunctionCall,
    IdentifierNode,
    NumberLiteral,
    StringLiteral,
    TimeSeriesIndex,
    UnaryOp,
)
from src.scoring.evaluator.interfaces import IFundamentalsProvider, IParameterCatalog
from src.scoring.evaluator.operator_registry import DslEvalError, OperatorRegistry


class AstEvaluator:
    """Evaluates a DSL AST for a specific company.

    Constructor parameters are injected — no direct DB access.
    """

    def __init__(
        self,
        fundamentals_provider: IFundamentalsProvider,
        parameter_catalog: IParameterCatalog,
        null_propagates: bool = True,
    ) -> None:
        self._provider = fundamentals_provider
        self._catalog = parameter_catalog
        self._null_propagates = null_propagates
        self._ops = OperatorRegistry()

    async def evaluate(
        self,
        ast: AstNode,
        company_id: UUID,
        tenant_id: UUID,
    ) -> float | None:
        """Evaluate *ast* for the given company.

        Returns a float, or None if any required leaf value is None and
        null_propagates=True.

        Raises:
            DslEvalError: on runtime evaluation errors (division by zero, etc.)
        """
        # Collect all parameter names referenced so we can batch-fetch
        param_names = _collect_identifiers(ast)
        ts_params = _collect_time_series_params(ast)

        # Batch-fetch fundamentals
        fundamentals: dict[str, float | None] = {}
        if param_names:
            fundamentals = await self._provider.get_company_fundamentals(
                company_id, list(param_names)
            )

        # Batch-fetch time-series data
        time_series_cache: dict[str, list[float | None]] = {}
        for param, max_lookback in ts_params.items():
            time_series_cache[param] = await self._provider.get_time_series(
                company_id, param, abs(max_lookback) + 1
            )

        ctx = _EvalContext(
            fundamentals=fundamentals,
            time_series=time_series_cache,
            null_propagates=self._null_propagates,
            ops=self._ops,
        )
        return ctx.eval(ast)


# ---------------------------------------------------------------------------
# Identifier collection helpers
# ---------------------------------------------------------------------------

def _collect_identifiers(node: AstNode) -> set[str]:
    """Return all IdentifierNode names in the AST (not in function-call position)."""
    result: set[str] = set()
    _visit_identifiers(node, result)
    return result


def _visit_identifiers(node: AstNode, result: set[str]) -> None:
    if isinstance(node, IdentifierNode):
        result.add(node.name)
    elif isinstance(node, BinaryOp):
        _visit_identifiers(node.left, result)
        _visit_identifiers(node.right, result)
    elif isinstance(node, UnaryOp):
        _visit_identifiers(node.operand, result)
    elif isinstance(node, FunctionCall):
        for arg in node.positional_args:
            _visit_identifiers(arg, result)
        for _, kw_val in node.keyword_args:
            _visit_identifiers(kw_val, result)
    elif isinstance(node, ConditionalExpr):
        _visit_identifiers(node.condition, result)
        _visit_identifiers(node.then_expr, result)
        _visit_identifiers(node.else_expr, result)
    # NumberLiteral, StringLiteral, TimeSeriesIndex handled elsewhere


def _collect_time_series_params(node: AstNode) -> dict[str, int]:
    """Return {param_name: most_negative_offset} for TimeSeriesIndex nodes."""
    result: dict[str, int] = {}
    _visit_ts(node, result)
    return result


def _visit_ts(node: AstNode, result: dict[str, int]) -> None:
    if isinstance(node, TimeSeriesIndex):
        existing = result.get(node.parameter, 0)
        result[node.parameter] = min(existing, node.offset)
    elif isinstance(node, BinaryOp):
        _visit_ts(node.left, result)
        _visit_ts(node.right, result)
    elif isinstance(node, UnaryOp):
        _visit_ts(node.operand, result)
    elif isinstance(node, FunctionCall):
        for arg in node.positional_args:
            _visit_ts(arg, result)
        for _, kw_val in node.keyword_args:
            _visit_ts(kw_val, result)
    elif isinstance(node, ConditionalExpr):
        _visit_ts(node.condition, result)
        _visit_ts(node.then_expr, result)
        _visit_ts(node.else_expr, result)


# ---------------------------------------------------------------------------
# Synchronous evaluation context (runs after async data fetch)
# ---------------------------------------------------------------------------

class _EvalContext:
    def __init__(
        self,
        fundamentals: dict[str, float | None],
        time_series: dict[str, list[float | None]],
        null_propagates: bool,
        ops: OperatorRegistry,
    ) -> None:
        self._fundamentals = fundamentals
        self._time_series = time_series
        self._null_propagates = null_propagates
        self._ops = ops

    def eval(self, node: AstNode) -> float | None:
        if isinstance(node, NumberLiteral):
            return node.value

        if isinstance(node, StringLiteral):
            # Strip surrounding quotes
            return node.value.strip('"').strip("'")  # type: ignore[return-value]

        if isinstance(node, IdentifierNode):
            val = self._fundamentals.get(node.name)
            if val is None:
                if self._null_propagates:
                    return None
                raise DslEvalError(
                    f"Required parameter {node.name!r} is None and null_propagates=False"
                )
            return val

        if isinstance(node, TimeSeriesIndex):
            series = self._time_series.get(node.parameter, [])
            # offset is negative: -1 means index -1 from the list end
            try:
                val = series[node.offset]
            except IndexError:
                val = None
            if val is None and self._null_propagates:
                return None
            if val is None:
                raise DslEvalError(
                    f"Time-series value at offset {node.offset} for "
                    f"{node.parameter!r} is None and null_propagates=False"
                )
            return val

        if isinstance(node, BinaryOp):
            left = self.eval(node.left)
            right = self.eval(node.right)
            if left is None or right is None:
                return None
            return self._ops.apply_binary(node.op, left, right)

        if isinstance(node, UnaryOp):
            operand = self.eval(node.operand)
            if operand is None:
                return None
            return self._ops.apply_unary(node.op, operand)

        if isinstance(node, FunctionCall):
            positional_vals = [self.eval(arg) for arg in node.positional_args]
            if any(v is None for v in positional_vals) and self._null_propagates:
                return None
            keyword_vals = {k: self.eval(v) for k, v in node.keyword_args}
            return self._ops.call_function(node.name, positional_vals, keyword_vals)

        if isinstance(node, ConditionalExpr):
            # ConditionalExpr is IF — we need to eval condition first; branches may short-circuit
            cond = self.eval(node.condition)
            if cond is None:
                return None
            if cond:
                return self.eval(node.then_expr)
            return self.eval(node.else_expr)

        raise DslEvalError(f"Unknown AST node type: {type(node).__name__}")
