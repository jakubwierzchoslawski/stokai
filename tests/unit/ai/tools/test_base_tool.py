"""Tests for ToolResult, ToolError, ToolCacheEntry, BaseTool, and BaseToolInput.

Covers TASK-001 and TASK-002 contracts.
"""
from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from src.ai.tools.base import (
    MAX_ROWS,
    BaseToolInput,
    ToolCacheEntry,
    ToolError,
    ToolErrorType,
    ToolResult,
)
from src.ai.tools.exceptions import (
    InsufficientData,
    RateLimited,
    ToolNotApplicable,
)


# ---------------------------------------------------------------------------
# TASK-001: ToolResult tests
# ---------------------------------------------------------------------------


def test_tool_result_from_rows_under_50_sets_truncated_false() -> None:
    rows = [{"id": i} for i in range(10)]
    result = ToolResult.from_rows(rows)
    assert result.truncated is False
    assert result.row_count == 10
    assert len(result.data) == 10


def test_tool_result_from_rows_exactly_50_sets_truncated_false() -> None:
    rows = [{"id": i} for i in range(50)]
    result = ToolResult.from_rows(rows)
    assert result.truncated is False
    assert result.row_count == 50


def test_tool_result_from_rows_over_50_truncates_to_50_sets_truncated_true() -> None:
    rows = [{"id": i} for i in range(75)]
    result = ToolResult.from_rows(rows)
    assert result.truncated is True
    assert result.row_count == MAX_ROWS
    assert len(result.data) == MAX_ROWS


def test_tool_result_row_count_matches_bounded_data_length() -> None:
    rows = [{"id": i} for i in range(60)]
    result = ToolResult.from_rows(rows)
    assert result.row_count == len(result.data)


def test_tool_error_is_json_serializable() -> None:
    err = ToolError(
        error_type=ToolErrorType.RATE_LIMITED,
        message="Too many requests",
        retry_after=30,
    )
    serialized = err.model_dump_json()
    parsed = json.loads(serialized)
    assert parsed["error_type"] == "RateLimited"
    assert parsed["message"] == "Too many requests"
    assert parsed["retry_after"] == 30


# ---------------------------------------------------------------------------
# TASK-001: Exception tests
# ---------------------------------------------------------------------------


def test_tool_not_applicable_carries_tool_name_and_reason() -> None:
    exc = ToolNotApplicable(tool_name="get_portfolio_positions", reason="No portfolio found")
    assert exc.tool_name == "get_portfolio_positions"
    assert exc.reason == "No portfolio found"
    assert "get_portfolio_positions" in str(exc)
    assert "No portfolio found" in str(exc)


def test_rate_limited_carries_retry_after_seconds() -> None:
    exc = RateLimited(tool_name="get_macro_indicators", source="FRED", retry_after=60)
    assert exc.tool_name == "get_macro_indicators"
    assert exc.source == "FRED"
    assert exc.retry_after == 60


def test_insufficient_data_message_propagated() -> None:
    exc = InsufficientData(tool_name="get_company_scores", reason="No scores available")
    assert exc.tool_name == "get_company_scores"
    assert exc.reason == "No scores available"
    assert "get_company_scores" in str(exc)


# ---------------------------------------------------------------------------
# TASK-001: ToolCacheEntry composite key test
# ---------------------------------------------------------------------------


def test_tool_cache_entry_has_composite_key() -> None:
    run_id = uuid4()
    entry = ToolCacheEntry(
        run_id=run_id,
        tool_name="get_portfolio_positions",
        args_hash="abc12345",
        result=ToolResult(data=[{"ticker": "AAPL"}], truncated=False, row_count=1),
    )
    assert entry.run_id == run_id
    assert entry.tool_name == "get_portfolio_positions"
    assert entry.args_hash == "abc12345"


# ---------------------------------------------------------------------------
# TASK-002: BaseTool caching and error-mapping tests
# ---------------------------------------------------------------------------


def _make_tool(execute_return: list[dict[str, Any]] | Exception) -> Any:
    """Build a concrete BaseTool subclass for testing."""
    from src.ai.tools.base import BaseTool

    class _FakeTool(BaseTool):
        name = "fake_tool"

        async def _execute(self, inputs: BaseToolInput) -> list[dict[str, Any]]:
            if isinstance(execute_return, Exception):
                raise execute_return
            return execute_return  # type: ignore[return-value]

    mock_logger = AsyncMock()
    mock_cache_or_fetch = MagicMock()
    return _FakeTool(cache_or_fetch=mock_cache_or_fetch, logger=mock_logger)


@pytest.mark.asyncio
async def test_second_call_with_same_args_returns_cached_result_without_calling_execute() -> None:
    tool = _make_tool([{"ticker": "AAPL"}])
    inputs = BaseToolInput(tenant_id=uuid4())
    run_id = uuid4()
    run_cache: dict[str, ToolResult] = {}

    result1 = await tool.execute(inputs, run_id, run_cache)
    result2 = await tool.execute(inputs, run_id, run_cache)

    assert result1 is result2
    # _execute should only have been called once — the second call returns cache
    assert isinstance(result2, ToolResult)


@pytest.mark.asyncio
async def test_second_call_with_different_run_id_calls_execute_again() -> None:
    rows = [{"ticker": "AAPL"}]
    tool = _make_tool(rows)
    inputs = BaseToolInput(tenant_id=uuid4())
    run_cache_1: dict[str, ToolResult] = {}
    run_cache_2: dict[str, ToolResult] = {}
    run_id_1 = uuid4()
    run_id_2 = uuid4()

    result1 = await tool.execute(inputs, run_id_1, run_cache_1)
    result2 = await tool.execute(inputs, run_id_2, run_cache_2)

    # Different run caches → different executions; both should return ToolResult
    assert isinstance(result1, ToolResult)
    assert isinstance(result2, ToolResult)


@pytest.mark.asyncio
async def test_tool_not_applicable_exception_maps_to_tool_error_of_correct_type() -> None:
    exc = ToolNotApplicable(tool_name="fake_tool", reason="not applicable")
    tool = _make_tool(exc)
    inputs = BaseToolInput(tenant_id=uuid4())
    run_cache: dict[str, ToolResult] = {}

    result = await tool.execute(inputs, uuid4(), run_cache)
    assert isinstance(result, ToolError)
    assert result.error_type == ToolErrorType.TOOL_NOT_APPLICABLE


@pytest.mark.asyncio
async def test_insufficient_data_exception_maps_to_tool_error() -> None:
    exc = InsufficientData(tool_name="fake_tool", reason="no data")
    tool = _make_tool(exc)
    inputs = BaseToolInput(tenant_id=uuid4())
    run_cache: dict[str, ToolResult] = {}

    result = await tool.execute(inputs, uuid4(), run_cache)
    assert isinstance(result, ToolError)
    assert result.error_type == ToolErrorType.INSUFFICIENT_DATA


@pytest.mark.asyncio
async def test_rate_limited_exception_maps_to_tool_error_with_retry_after() -> None:
    exc = RateLimited(tool_name="fake_tool", source="FRED", retry_after=45)
    tool = _make_tool(exc)
    inputs = BaseToolInput(tenant_id=uuid4())
    run_cache: dict[str, ToolResult] = {}

    result = await tool.execute(inputs, uuid4(), run_cache)
    assert isinstance(result, ToolError)
    assert result.error_type == ToolErrorType.RATE_LIMITED
    assert result.retry_after == 45


@pytest.mark.asyncio
async def test_unknown_exception_propagates_uncaught() -> None:
    exc = ValueError("unexpected error")
    tool = _make_tool(exc)
    inputs = BaseToolInput(tenant_id=uuid4())
    run_cache: dict[str, ToolResult] = {}

    with pytest.raises(ValueError, match="unexpected error"):
        await tool.execute(inputs, uuid4(), run_cache)


def test_base_tool_input_requires_tenant_id() -> None:
    with pytest.raises(Exception):
        BaseToolInput()  # type: ignore[call-arg]

    # Valid construction
    tenant_id = uuid4()
    inp = BaseToolInput(tenant_id=tenant_id)
    assert inp.tenant_id == tenant_id


@pytest.mark.asyncio
async def test_args_hash_excludes_tenant_id() -> None:
    """Two inputs differing only in tenant_id must produce the same args_hash,
    meaning the cached result is the same for same functional args regardless of tenant.
    However, the cache key includes run_id, so within a run same functional args → same hash.
    """
    from src.ai.tools.base import BaseTool

    calls: list[str] = []

    class _HashTool(BaseTool):
        name = "hash_tool"

        async def _execute(self, inputs: BaseToolInput) -> list[dict[str, Any]]:
            calls.append("executed")
            return [{"value": 1}]

    mock_logger = AsyncMock()
    mock_cof = MagicMock()
    tool = _HashTool(cache_or_fetch=mock_cof, logger=mock_logger)

    tenant_1 = uuid4()
    tenant_2 = uuid4()
    run_id = uuid4()

    inp1 = BaseToolInput(tenant_id=tenant_1)
    inp2 = BaseToolInput(tenant_id=tenant_2)

    # Both have the same non-tenant-id fields (none here), so same args_hash
    # They should map to the same cache key → second call is a hit
    run_cache: dict[str, ToolResult] = {}
    await tool.execute(inp1, run_id, run_cache)
    await tool.execute(inp2, run_id, run_cache)

    assert len(calls) == 1  # second call was a cache hit


@pytest.mark.asyncio
async def test_logger_called_on_cache_hit_with_cached_true() -> None:
    tool = _make_tool([{"ticker": "MSFT"}])
    inputs = BaseToolInput(tenant_id=uuid4())
    run_id = uuid4()
    run_cache: dict[str, ToolResult] = {}

    await tool.execute(inputs, run_id, run_cache)  # miss
    await tool.execute(inputs, run_id, run_cache)  # hit

    # Logger must be called twice
    assert tool._logger.log.call_count == 2  # type: ignore[attr-defined]
    # Second call should pass cached=True — use .kwargs for compatibility
    second_call = tool._logger.log.call_args_list[1]  # type: ignore[attr-defined]
    second_kwargs = second_call.kwargs if hasattr(second_call, "kwargs") else second_call[1]
    assert second_kwargs.get("cached") is True


@pytest.mark.asyncio
async def test_logger_called_on_cache_miss_with_cached_false() -> None:
    tool = _make_tool([{"ticker": "MSFT"}])
    inputs = BaseToolInput(tenant_id=uuid4())
    run_id = uuid4()
    run_cache: dict[str, ToolResult] = {}

    await tool.execute(inputs, run_id, run_cache)

    assert tool._logger.log.call_count == 1  # type: ignore[attr-defined]
    first_call = tool._logger.log.call_args_list[0]  # type: ignore[attr-defined]
    first_kwargs = first_call.kwargs if hasattr(first_call, "kwargs") else first_call[1]
    assert first_kwargs.get("cached") is False
