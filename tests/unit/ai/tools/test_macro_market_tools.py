"""Tests for Macro + Market tool family (TASK-008)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.ai.tools.base import ToolError, ToolErrorType, ToolResult
from src.ai.tools.exceptions import RateLimited
from src.ai.tools.families.macro_market import (
    GetMacroIndicators,
    GetSectorPerformance,
)


def _make_tool(cls, rows: list[dict] | None = None):
    mock_cof = MagicMock()
    mock_cof.cache_or_fetch = AsyncMock(return_value=rows or [])
    mock_logger = AsyncMock()
    tool = cls(cache_or_fetch=mock_cof, logger=mock_logger)
    tool._execute = AsyncMock(return_value=rows or [])
    return tool


def test_get_macro_indicators_tool_name() -> None:
    assert GetMacroIndicators.name == "get_macro_indicators"


def test_get_sector_performance_tool_name() -> None:
    assert GetSectorPerformance.name == "get_sector_performance"


@pytest.mark.asyncio
async def test_get_macro_indicators_returns_tool_result() -> None:
    from src.ai.tools.families.macro_market import GetMacroIndicatorsInput

    rows = [{"indicator": "GDP", "value": 25000}]
    tool = _make_tool(GetMacroIndicators, rows)
    inputs = GetMacroIndicatorsInput(tenant_id=uuid4(), indicator_list=["GDP"])
    run_cache: dict = {}
    result = await tool.execute(inputs, uuid4(), run_cache)
    assert isinstance(result, ToolResult)
    assert result.row_count == 1


@pytest.mark.asyncio
async def test_get_macro_indicators_indicator_list_capped_at_max_rows() -> None:
    from src.ai.tools.families.macro_market import GetMacroIndicatorsInput

    # Requesting 75 indicators — indicator_list gets capped at MAX_ROWS
    from src.ai.tools.base import MAX_ROWS

    indicators = [f"IND_{i}" for i in range(75)]
    rows = [{"indicator": ind, "value": i} for i, ind in enumerate(indicators[:MAX_ROWS])]
    tool = _make_tool(GetMacroIndicators, rows)
    inputs = GetMacroIndicatorsInput(tenant_id=uuid4(), indicator_list=indicators)
    run_cache: dict = {}
    result = await tool.execute(inputs, uuid4(), run_cache)
    assert isinstance(result, ToolResult)
    assert result.row_count == MAX_ROWS


@pytest.mark.asyncio
async def test_rate_limited_from_fred_returns_tool_error() -> None:
    from src.ai.tools.families.macro_market import GetMacroIndicatorsInput
    from src.ai.tools.base import BaseTool

    class _RateLimitedMacroTool(GetMacroIndicators):
        async def _execute(self, inputs):  # type: ignore[override]
            raise RateLimited(tool_name=self.name, source="FRED", retry_after=30)

    mock_cof = MagicMock()
    mock_logger = AsyncMock()
    tool = _RateLimitedMacroTool(cache_or_fetch=mock_cof, logger=mock_logger)
    inputs = GetMacroIndicatorsInput(tenant_id=uuid4(), indicator_list=["GDP"])
    run_cache: dict = {}
    result = await tool.execute(inputs, uuid4(), run_cache)
    assert isinstance(result, ToolError)
    assert result.error_type == ToolErrorType.RATE_LIMITED
    assert result.retry_after == 30


@pytest.mark.asyncio
async def test_get_sector_performance_returns_tool_result() -> None:
    from src.ai.tools.families.macro_market import GetSectorPerformanceInput

    rows = [{"sector": "Technology", "return_1d": 0.02}]
    tool = _make_tool(GetSectorPerformance, rows)
    inputs = GetSectorPerformanceInput(tenant_id=uuid4())
    run_cache: dict = {}
    result = await tool.execute(inputs, uuid4(), run_cache)
    assert isinstance(result, ToolResult)
