"""Tests for the DSL recursive-descent parser (TDD — tests written first)."""
from __future__ import annotations

import pytest

from src.scoring.dsl.tokenizer import tokenize
from src.scoring.dsl.parser import parse, DslParseError
from src.scoring.dsl.ast_nodes import (
    BinaryOp,
    ConditionalExpr,
    FunctionCall,
    IdentifierNode,
    NumberLiteral,
    StringLiteral,
    TimeSeriesIndex,
    UnaryOp,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse_formula(formula: str):
    return parse(tokenize(formula))


# ---------------------------------------------------------------------------
# Operator precedence
# ---------------------------------------------------------------------------

class TestPrecedence:
    def test_revenue_times_half_plus_net_income(self):
        """revenue * 0.5 + net_income → (+, (*, revenue, 0.5), net_income)"""
        tree = parse_formula("revenue * 0.5 + net_income")
        assert isinstance(tree, BinaryOp)
        assert tree.op == "+"
        assert isinstance(tree.left, BinaryOp)
        assert tree.left.op == "*"
        assert isinstance(tree.left.left, IdentifierNode)
        assert tree.left.left.name == "revenue"
        assert isinstance(tree.left.right, NumberLiteral)
        assert tree.left.right.value == 0.5
        assert isinstance(tree.right, IdentifierNode)
        assert tree.right.name == "net_income"

    def test_additive_left_associative(self):
        """a + b + c → (+, (+, a, b), c)"""
        tree = parse_formula("a + b + c")
        assert isinstance(tree, BinaryOp)
        assert tree.op == "+"
        assert isinstance(tree.left, BinaryOp)
        assert tree.left.op == "+"

    def test_multiplicative_higher_than_additive(self):
        """a + b * c → (+, a, (*, b, c))"""
        tree = parse_formula("a + b * c")
        assert isinstance(tree, BinaryOp)
        assert tree.op == "+"
        assert isinstance(tree.right, BinaryOp)
        assert tree.right.op == "*"


# ---------------------------------------------------------------------------
# ConditionalExpr
# ---------------------------------------------------------------------------

class TestConditionalExpr:
    def test_if_pe_ratio_lt_15(self):
        """IF(pe_ratio < 15, 1, 0) → ConditionalExpr"""
        tree = parse_formula("IF(pe_ratio < 15, 1, 0)")
        assert isinstance(tree, ConditionalExpr)
        # condition
        assert isinstance(tree.condition, BinaryOp)
        assert tree.condition.op == "<"
        assert isinstance(tree.condition.left, IdentifierNode)
        assert tree.condition.left.name == "pe_ratio"
        assert isinstance(tree.condition.right, NumberLiteral)
        assert tree.condition.right.value == 15.0
        # branches
        assert isinstance(tree.then_expr, NumberLiteral)
        assert tree.then_expr.value == 1.0
        assert isinstance(tree.else_expr, NumberLiteral)
        assert tree.else_expr.value == 0.0


# ---------------------------------------------------------------------------
# TimeSeriesIndex
# ---------------------------------------------------------------------------

class TestTimeSeriesIndex:
    def test_price_minus_one_div_price_minus_five(self):
        """price[-1] / price[-5] → BinaryOp(/, TimeSeriesIndex, TimeSeriesIndex)"""
        tree = parse_formula("price[-1] / price[-5]")
        assert isinstance(tree, BinaryOp)
        assert tree.op == "/"
        left = tree.left
        right = tree.right
        assert isinstance(left, TimeSeriesIndex)
        assert left.parameter == "price"
        assert left.offset == -1
        assert isinstance(right, TimeSeriesIndex)
        assert right.parameter == "price"
        assert right.offset == -5


# ---------------------------------------------------------------------------
# FunctionCall with keyword argument
# ---------------------------------------------------------------------------

class TestFunctionCall:
    def test_rank_with_keyword_arg(self):
        """RANK(roe, peer_group="SP500") → FunctionCall with keyword arg"""
        tree = parse_formula('RANK(roe, peer_group="SP500")')
        assert isinstance(tree, FunctionCall)
        assert tree.name == "RANK"
        assert len(tree.positional_args) == 1
        assert isinstance(tree.positional_args[0], IdentifierNode)
        assert tree.positional_args[0].name == "roe"
        assert len(tree.keyword_args) == 1
        kw_name, kw_val = tree.keyword_args[0]
        assert kw_name == "peer_group"
        assert isinstance(kw_val, StringLiteral)
        assert kw_val.value == '"SP500"'

    def test_function_no_args(self):
        """ABS() → FunctionCall with empty args"""
        tree = parse_formula("ABS(x)")
        assert isinstance(tree, FunctionCall)
        assert tree.name == "ABS"
        assert len(tree.positional_args) == 1


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------

class TestParseErrors:
    def test_unbalanced_left_paren(self):
        with pytest.raises(DslParseError):
            parse_formula("(a + b")

    def test_unbalanced_right_paren(self):
        with pytest.raises(DslParseError):
            parse_formula("a + b)")

    def test_two_consecutive_operators(self):
        """a + * b → DslParseError (no operand between operators)"""
        with pytest.raises(DslParseError):
            parse_formula("a + * b")

    def test_empty_formula(self):
        """Empty string should raise DslParseError"""
        with pytest.raises(DslParseError):
            parse_formula("")

    def test_trailing_operator(self):
        """a + → DslParseError"""
        with pytest.raises(DslParseError):
            parse_formula("a +")
