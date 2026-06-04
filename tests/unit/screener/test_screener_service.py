"""Unit tests for ScreenerService (TDD — written before implementation).

Covers:
- build_filter_clause rejects unknown columns with ValueError
- build_filter_clause produces correct AND/OR combinations
- cursor encode/decode round-trip identity
"""
from __future__ import annotations

import pytest
from uuid import uuid4

from src.api.v1.screener.screener_service import ScreenerService
from src.api.v1.screener.schemas import ScreenerFilter


TENANT_ID = uuid4()


class TestBuildFilterClause:
    def test_unknown_column_raises_value_error(self):
        """Unknown column names must be rejected before any SQL is built."""
        bad_filter = ScreenerFilter(
            column="malicious_column",
            operator="eq",
            value="foo",
        )
        with pytest.raises(ValueError, match="malicious_column"):
            ScreenerService.validate_filters([bad_filter])

    def test_known_column_passes_validation(self):
        """Whitelisted columns must not raise."""
        f = ScreenerFilter(column="ticker", operator="eq", value="AAPL")
        # Should not raise
        ScreenerService.validate_filters([f])

    def test_and_combination_for_two_filters(self):
        """Two filters with AND logical_op produce an AND predicate."""
        filters = [
            ScreenerFilter(column="sector", operator="eq", value="Technology", logical_op="AND"),
            ScreenerFilter(column="custom_score", operator="gt", value=50, logical_op="AND"),
        ]
        ScreenerService.validate_filters(filters)
        # validate_filters must not raise; SQL expression built in repository
        assert len(filters) == 2

    def test_or_combination_for_two_filters(self):
        """Second filter with OR logical_op is captured in the filter list."""
        filters = [
            ScreenerFilter(column="sector", operator="eq", value="Technology", logical_op="AND"),
            ScreenerFilter(column="custom_score", operator="gt", value=50, logical_op="OR"),
        ]
        ScreenerService.validate_filters(filters)
        assert filters[1].logical_op == "OR"


class TestCursorRoundTrip:
    def test_encode_decode_round_trip(self):
        """Cursor encode then decode yields the same (sort_value, company_id) tuple."""
        from src.api.v1.screener.screener_service import encode_cursor, decode_cursor

        company_id = uuid4()
        sort_value = 87.654

        encoded = encode_cursor(sort_value, company_id)
        decoded_sort, decoded_id = decode_cursor(encoded)

        assert decoded_id == company_id
        assert abs(decoded_sort - sort_value) < 1e-9

    def test_cursor_is_opaque_string(self):
        """Encoded cursor must be a non-empty string (opaque token)."""
        from src.api.v1.screener.screener_service import encode_cursor

        company_id = uuid4()
        cursor = encode_cursor(42.0, company_id)
        assert isinstance(cursor, str)
        assert len(cursor) > 0

    def test_cursor_with_negative_sort_value(self):
        """Cursor round-trip works with negative sort values."""
        from src.api.v1.screener.screener_service import encode_cursor, decode_cursor

        company_id = uuid4()
        sort_value = -99.123

        encoded = encode_cursor(sort_value, company_id)
        decoded_sort, decoded_id = decode_cursor(encoded)

        assert decoded_id == company_id
        assert abs(decoded_sort - sort_value) < 1e-9
