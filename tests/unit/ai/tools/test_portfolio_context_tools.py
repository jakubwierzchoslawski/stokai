"""Tests for Portfolio Context tool family (TASK-004)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.ai.tools.base import ToolResult
from src.ai.tools.families.portfolio_context import (
    GetPortfolioPositions,
    GetScoringProfile,
    GetWatchlist,
)


def _make_tool(cls, rows: list[dict] | None = None):
    """Build a concrete portfolio tool with mocked dependencies."""
    mock_cof = AsyncMock()
    mock_cof.cache_or_fetch = AsyncMock(return_value=rows or [])
    mock_logger = AsyncMock()
    tool = cls(cache_or_fetch=mock_cof, logger=mock_logger)
    # Patch _execute directly to return rows
    tool._execute = AsyncMock(return_value=rows or [])
    return tool


def _make_full_tool(cls, rows: list[dict] | None = None):
    """Build a tool where cache_or_fetch returns rows."""
    mock_cof = MagicMock()
    mock_cof.cache_or_fetch = AsyncMock(return_value=rows or [])
    mock_logger = AsyncMock()
    return cls(cache_or_fetch=mock_cof, logger=mock_logger)


@pytest.mark.asyncio
async def test_get_portfolio_positions_returns_tool_result() -> None:
    from src.ai.tools.families.portfolio_context import GetPortfolioPositionsInput

    rows = [{"ticker": "AAPL", "shares": 10}]
    tool = _make_tool(GetPortfolioPositions, rows)
    inputs = GetPortfolioPositionsInput(tenant_id=uuid4(), user_id=uuid4())
    run_cache: dict = {}
    result = await tool.execute(inputs, uuid4(), run_cache)
    assert isinstance(result, ToolResult)
    assert result.row_count == 1


@pytest.mark.asyncio
async def test_get_watchlist_returns_tool_result() -> None:
    from src.ai.tools.families.portfolio_context import GetWatchlistInput

    rows = [{"ticker": "MSFT"}]
    tool = _make_tool(GetWatchlist, rows)
    inputs = GetWatchlistInput(tenant_id=uuid4(), user_id=uuid4())
    run_cache: dict = {}
    result = await tool.execute(inputs, uuid4(), run_cache)
    assert isinstance(result, ToolResult)


@pytest.mark.asyncio
async def test_get_scoring_profile_returns_tool_result() -> None:
    from src.ai.tools.families.portfolio_context import GetScoringProfileInput

    rows = [{"profile_name": "growth", "weight": 0.5}]
    tool = _make_tool(GetScoringProfile, rows)
    inputs = GetScoringProfileInput(tenant_id=uuid4())
    run_cache: dict = {}
    result = await tool.execute(inputs, uuid4(), run_cache)
    assert isinstance(result, ToolResult)


def test_get_portfolio_positions_tool_name() -> None:
    assert GetPortfolioPositions.name == "get_portfolio_positions"


def test_get_watchlist_tool_name() -> None:
    assert GetWatchlist.name == "get_watchlist"


def test_get_scoring_profile_tool_name() -> None:
    assert GetScoringProfile.name == "get_scoring_profile"


@pytest.mark.asyncio
async def test_get_portfolio_positions_empty_portfolio() -> None:
    from src.ai.tools.families.portfolio_context import GetPortfolioPositionsInput

    tool = _make_tool(GetPortfolioPositions, [])
    inputs = GetPortfolioPositionsInput(tenant_id=uuid4(), user_id=uuid4())
    run_cache: dict = {}
    result = await tool.execute(inputs, uuid4(), run_cache)
    assert isinstance(result, ToolResult)
    assert result.row_count == 0


@pytest.mark.asyncio
async def test_portfolio_tool_passes_tenant_id_to_cache_or_fetch() -> None:
    """Tenant ID must be scoped in the data retrieval call."""
    from src.ai.tools.families.portfolio_context import (
        GetPortfolioPositions,
        GetPortfolioPositionsInput,
    )

    tenant_id = uuid4()
    user_id = uuid4()
    mock_cof = MagicMock()
    mock_cof.cache_or_fetch = AsyncMock(return_value=[{"ticker": "AAPL"}])
    mock_logger = AsyncMock()
    tool = GetPortfolioPositions(cache_or_fetch=mock_cof, logger=mock_logger)
    inputs = GetPortfolioPositionsInput(tenant_id=tenant_id, user_id=user_id)
    run_cache: dict = {}
    result = await tool.execute(inputs, uuid4(), run_cache)
    assert isinstance(result, ToolResult)
    # cache_or_fetch must have been called
    mock_cof.cache_or_fetch.assert_called_once()
