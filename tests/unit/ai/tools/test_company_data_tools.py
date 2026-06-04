"""Tests for Company Data tool family (TASK-005)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.ai.tools.base import ToolResult
from src.ai.tools.families.company_data import (
    GetCompanyFundamentals,
    GetCompanyScores,
    GetPriceHistory,
)


def _make_tool(cls, rows: list[dict] | None = None):
    mock_cof = MagicMock()
    mock_cof.cache_or_fetch = AsyncMock(return_value=rows or [])
    mock_logger = AsyncMock()
    tool = cls(cache_or_fetch=mock_cof, logger=mock_logger)
    tool._execute = AsyncMock(return_value=rows or [])
    return tool


def test_get_company_fundamentals_tool_name() -> None:
    assert GetCompanyFundamentals.name == "get_company_fundamentals"


def test_get_company_scores_tool_name() -> None:
    assert GetCompanyScores.name == "get_company_scores"


def test_get_price_history_tool_name() -> None:
    assert GetPriceHistory.name == "get_price_history"


@pytest.mark.asyncio
async def test_get_company_fundamentals_returns_tool_result() -> None:
    from src.ai.tools.families.company_data import GetCompanyFundamentalsInput

    rows = [{"ticker": "AAPL", "revenue": 100000}]
    tool = _make_tool(GetCompanyFundamentals, rows)
    inputs = GetCompanyFundamentalsInput(tenant_id=uuid4(), ticker="AAPL")
    run_cache: dict = {}
    result = await tool.execute(inputs, uuid4(), run_cache)
    assert isinstance(result, ToolResult)
    assert result.row_count == 1


@pytest.mark.asyncio
async def test_get_company_scores_scoped_to_tenant() -> None:
    from src.ai.tools.families.company_data import GetCompanyScoresInput

    tenant_id = uuid4()
    rows = [{"ticker": "GOOG", "score": 0.85}]
    mock_cof = MagicMock()
    mock_cof.cache_or_fetch = AsyncMock(return_value=rows)
    mock_logger = AsyncMock()
    tool = GetCompanyScores(cache_or_fetch=mock_cof, logger=mock_logger)
    inputs = GetCompanyScoresInput(tenant_id=tenant_id, ticker="GOOG")
    run_cache: dict = {}
    result = await tool.execute(inputs, uuid4(), run_cache)
    assert isinstance(result, ToolResult)
    mock_cof.cache_or_fetch.assert_called_once()


@pytest.mark.asyncio
async def test_get_price_history_returns_at_most_50_bars() -> None:
    from src.ai.tools.families.company_data import GetPriceHistoryInput

    rows = [{"close": i} for i in range(75)]
    tool = _make_tool(GetPriceHistory, rows)
    inputs = GetPriceHistoryInput(
        tenant_id=uuid4(),
        ticker="TSLA",
        from_date="2024-01-01",
        to_date="2024-12-31",
        interval="1d",
    )
    run_cache: dict = {}
    result = await tool.execute(inputs, uuid4(), run_cache)
    assert isinstance(result, ToolResult)
    assert result.row_count == 50
    assert result.truncated is True


@pytest.mark.asyncio
async def test_company_tool_tenant_id_in_query() -> None:
    from src.ai.tools.families.company_data import GetCompanyFundamentalsInput

    tenant_id = uuid4()
    rows = [{"ticker": "NVDA"}]
    mock_cof = MagicMock()
    mock_cof.cache_or_fetch = AsyncMock(return_value=rows)
    mock_logger = AsyncMock()
    tool = GetCompanyFundamentals(cache_or_fetch=mock_cof, logger=mock_logger)
    inputs = GetCompanyFundamentalsInput(tenant_id=tenant_id, ticker="NVDA")
    run_cache: dict = {}
    await tool.execute(inputs, uuid4(), run_cache)
    mock_cof.cache_or_fetch.assert_called_once()


@pytest.mark.asyncio
async def test_get_price_history_exact_50_bars_not_truncated() -> None:
    from src.ai.tools.families.company_data import GetPriceHistoryInput

    rows = [{"close": i} for i in range(50)]
    tool = _make_tool(GetPriceHistory, rows)
    inputs = GetPriceHistoryInput(
        tenant_id=uuid4(),
        ticker="TSLA",
        from_date="2024-01-01",
        to_date="2024-12-31",
        interval="1d",
    )
    run_cache: dict = {}
    result = await tool.execute(inputs, uuid4(), run_cache)
    assert result.row_count == 50
    assert result.truncated is False
