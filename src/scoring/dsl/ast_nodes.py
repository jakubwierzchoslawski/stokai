"""AST node dataclasses for the scoring DSL.

Every node is a frozen dataclass — immutable after construction.
No source-location metadata in v1.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AstNode:
    """Abstract base for all AST nodes."""


# ---------------------------------------------------------------------------
# Leaf nodes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class NumberLiteral(AstNode):
    """A numeric constant, e.g. 0.5, 100, -3.14."""
    value: float


@dataclass(frozen=True)
class StringLiteral(AstNode):
    """A string constant used in keyword arguments, e.g. peer_group="SP500"."""
    value: str


@dataclass(frozen=True)
class IdentifierNode(AstNode):
    """A parameter name or function name reference, e.g. revenue, pe_ratio."""
    name: str


# ---------------------------------------------------------------------------
# Expression nodes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BinaryOp(AstNode):
    """A binary expression: left <op> right.

    op is one of: +, -, *, /, ^, >, <, >=, <=, ==, !=, AND, OR
    """
    op: str
    left: AstNode
    right: AstNode


@dataclass(frozen=True)
class UnaryOp(AstNode):
    """A unary expression: <op> operand.

    op is one of: -, NOT
    """
    op: str
    operand: AstNode


@dataclass(frozen=True)
class FunctionCall(AstNode):
    """A function invocation, e.g. RANK(roe, peer_group="SP500").

    positional_args: ordered positional arguments.
    keyword_args: mapping of keyword name → AstNode value.
    """
    name: str
    positional_args: tuple[AstNode, ...]
    keyword_args: tuple[tuple[str, AstNode], ...]  # ordered pairs for hashability


@dataclass(frozen=True)
class TimeSeriesIndex(AstNode):
    """A time-series lookback reference, e.g. price[-1] or price[-5].

    parameter: the identifier being indexed.
    offset: negative integer (e.g. -1 means 1 period ago).
    """
    parameter: str
    offset: int


@dataclass(frozen=True)
class ConditionalExpr(AstNode):
    """An IF expression: IF(condition, then_expr, else_expr)."""
    condition: AstNode
    then_expr: AstNode
    else_expr: AstNode
