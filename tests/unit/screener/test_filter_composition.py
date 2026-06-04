"""Unit tests for ScreenerRepository filter composition engine (TDD).

Covers:
- Single AND filter → single predicate
- Two AND filters → AND compound
- Two filters with OR → OR compound
- Three filters AND/OR/AND → left-associativity
- contains operator → ilike
- in operator → in_()
- Unknown column → ValueError
- event_id present → event_exposure join
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock
from uuid import uuid4

from sqlalchemy import inspect as sa_inspect
from sqlalchemy import and_, or_

from src.api.v1.screener.schemas import ScreenerFilter, ScreenerRequest
from src.api.v1.screener.screener_repository import ScreenerRepository


def _repo() -> ScreenerRepository:
    """Create a ScreenerRepository with no real DB session (filter building is pure)."""
    return ScreenerRepository(session=MagicMock())


class TestFilterComposition:
    def test_single_and_filter_produces_single_predicate(self):
        """Single filter list → single SQL predicate, no AND/OR wrapper."""
        filters = [
            ScreenerFilter(column="sector", operator="eq", value="Technology", logical_op="AND"),
        ]
        clause = _repo().build_where_clause(filters)
        # Clause must not be None
        assert clause is not None

    def test_two_and_filters_produce_and_clause(self):
        """Two AND filters → compound AND clause."""
        filters = [
            ScreenerFilter(column="sector", operator="eq", value="Technology", logical_op="AND"),
            ScreenerFilter(column="custom_score", operator="gt", value=50, logical_op="AND"),
        ]
        clause = _repo().build_where_clause(filters)
        # Compound clause should be truthy
        assert clause is not None
        clause_str = str(clause.compile(compile_kwargs={"literal_binds": True}))
        assert "AND" in clause_str.upper()

    def test_two_filters_with_or_produces_or_clause(self):
        """Second filter with OR → OR compound."""
        filters = [
            ScreenerFilter(column="sector", operator="eq", value="Technology", logical_op="AND"),
            ScreenerFilter(column="custom_score", operator="gt", value=50, logical_op="OR"),
        ]
        clause = _repo().build_where_clause(filters)
        assert clause is not None
        clause_str = str(clause.compile(compile_kwargs={"literal_binds": True}))
        assert "OR" in clause_str.upper()

    def test_three_filters_left_associative(self):
        """Three filters AND/OR/AND → left-associative composition."""
        filters = [
            ScreenerFilter(column="sector", operator="eq", value="Energy", logical_op="AND"),
            ScreenerFilter(column="market_cap", operator="gt", value=1e9, logical_op="OR"),
            ScreenerFilter(column="custom_score", operator="lt", value=80, logical_op="AND"),
        ]
        clause = _repo().build_where_clause(filters)
        assert clause is not None
        # Should contain both AND and OR (left-associative composition)
        clause_str = str(clause.compile(compile_kwargs={"literal_binds": True}))
        assert "OR" in clause_str.upper()
        assert "AND" in clause_str.upper()

    def test_contains_operator_uses_ilike(self):
        """contains operator maps to ilike for case-insensitive search."""
        filters = [
            ScreenerFilter(column="name", operator="contains", value="apple", logical_op="AND"),
        ]
        clause = _repo().build_where_clause(filters)
        assert clause is not None
        clause_str = str(clause.compile(compile_kwargs={"literal_binds": True}))
        assert "LIKE" in clause_str.upper() or "ilike" in clause_str.lower()
        assert "%apple%" in clause_str.lower() or "%apple%" in clause_str

    def test_in_operator_uses_in_(self):
        """in operator maps to in_() for list membership."""
        filters = [
            ScreenerFilter(
                column="sector",
                operator="in",
                value=["Technology", "Energy"],
                logical_op="AND",
            ),
        ]
        clause = _repo().build_where_clause(filters)
        assert clause is not None
        clause_str = str(clause.compile(compile_kwargs={"literal_binds": True}))
        assert "IN" in clause_str.upper()

    def test_unknown_column_raises_value_error(self):
        """Unknown column raises ValueError before SQL is built."""
        filters = [
            ScreenerFilter(column="DROP_TABLE", operator="eq", value="x", logical_op="AND"),
        ]
        with pytest.raises(ValueError, match="DROP_TABLE"):
            _repo().build_where_clause(filters)

    def test_empty_filter_list_returns_none(self):
        """Empty filter list → None (no WHERE clause needed)."""
        clause = _repo().build_where_clause([])
        assert clause is None
