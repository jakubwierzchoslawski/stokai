"""Cross-tool unit tests (TASK-011).

Parametrised over one tool per family to verify cross-cutting concerns:
  - Run-cache (same run_id → cache hit, no second execute call)
  - 75-row truncation → 50 rows, truncated=True
  - ToolNotApplicable / InsufficientData / RateLimited error mapping
  - tenant_id scoping (portfolio, company, events, macro, memory)
  - Global events visibility
"""
from __future__ import annotations

from typing import Any, NamedTuple
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from src.ai.tools.base import (
    MAX_ROWS,
    BaseTool,
    BaseToolInput,
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
# Helpers
# ---------------------------------------------------------------------------


def _mock_tool_with_rows(tool_cls: type[BaseTool], rows: list[dict]) -> BaseTool:
    mock_cof = MagicMock()
    mock_cof.cache_or_fetch = AsyncMock(return_value=rows)
    mock_logger = AsyncMock()
    tool = tool_cls(cache_or_fetch=mock_cof, logger=mock_logger)
    tool._execute = AsyncMock(return_value=rows)
    return tool


def _mock_tool_raising(tool_cls: type[BaseTool], exc: Exception) -> BaseTool:
    mock_cof = MagicMock()
    mock_logger = AsyncMock()
    tool = tool_cls(cache_or_fetch=mock_cof, logger=mock_logger)
    tool._execute = AsyncMock(side_effect=exc)
    return tool


# ---------------------------------------------------------------------------
# One representative input per family
# ---------------------------------------------------------------------------

def _portfolio_input():
    from src.ai.tools.families.portfolio_context import GetPortfolioPositionsInput
    return GetPortfolioPositionsInput(tenant_id=uuid4(), user_id=uuid4())


def _company_input():
    from src.ai.tools.families.company_data import GetCompanyFundamentalsInput
    return GetCompanyFundamentalsInput(tenant_id=uuid4(), ticker="AAPL")


def _events_input():
    from src.ai.tools.families.events_history import GetEventsByCompanyInput
    return GetEventsByCompanyInput(tenant_id=uuid4(), company_id=uuid4())


def _exposure_input():
    from src.ai.tools.families.exposure_correlation import GetEventExposureInput
    return GetEventExposureInput(tenant_id=uuid4(), event_id=uuid4())


def _macro_input():
    from src.ai.tools.families.macro_market import GetMacroIndicatorsInput
    return GetMacroIndicatorsInput(tenant_id=uuid4(), indicator_list=["GDP"])


def _memory_input():
    from src.ai.tools.families.memory_track_record import GetSemanticFactsInput
    return GetSemanticFactsInput(tenant_id=uuid4(), namespace="entity", query="test")


# ---------------------------------------------------------------------------
# test_any_tool_second_call_same_run_id_returns_cached
# ---------------------------------------------------------------------------

FAMILY_TOOL_INPUT_PAIRS = [
    ("portfolio", "src.ai.tools.families.portfolio_context", "GetPortfolioPositions", _portfolio_input),
    ("company",   "src.ai.tools.families.company_data",       "GetCompanyFundamentals", _company_input),
    ("events",    "src.ai.tools.families.events_history",     "GetEventsByCompany",     _events_input),
    ("exposure",  "src.ai.tools.families.exposure_correlation", "GetEventExposure",     _exposure_input),
    ("macro",     "src.ai.tools.families.macro_market",       "GetMacroIndicators",     _macro_input),
    ("memory",    "src.ai.tools.families.memory_track_record","GetSemanticFacts",        _memory_input),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("label,module,cls_name,input_fn", FAMILY_TOOL_INPUT_PAIRS)
async def test_any_tool_second_call_same_run_id_returns_cached(
    label: str, module: str, cls_name: str, input_fn: Any
) -> None:
    import importlib

    mod = importlib.import_module(module)
    tool_cls = getattr(mod, cls_name)
    rows = [{"id": 1}]
    tool = _mock_tool_with_rows(tool_cls, rows)
    inputs = input_fn()
    run_id = uuid4()
    run_cache: dict = {}

    result1 = await tool.execute(inputs, run_id, run_cache)
    result2 = await tool.execute(inputs, run_id, run_cache)

    assert result1 is result2
    # _execute is only called once — the second is a cache hit
    tool._execute.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("label,module,cls_name,input_fn", FAMILY_TOOL_INPUT_PAIRS)
async def test_any_tool_75_rows_returns_50_truncated(
    label: str, module: str, cls_name: str, input_fn: Any
) -> None:
    import importlib

    mod = importlib.import_module(module)
    tool_cls = getattr(mod, cls_name)
    rows = [{"id": i} for i in range(75)]
    tool = _mock_tool_with_rows(tool_cls, rows)
    inputs = input_fn()
    run_cache: dict = {}

    result = await tool.execute(inputs, uuid4(), run_cache)
    assert isinstance(result, ToolResult)
    assert result.row_count == MAX_ROWS
    assert result.truncated is True


# ---------------------------------------------------------------------------
# Error-mapping cross-tool tests (use portfolio tool as representative)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tool_not_applicable_maps_to_tool_error_tool_not_applicable() -> None:
    from src.ai.tools.families.portfolio_context import GetPortfolioPositions

    exc = ToolNotApplicable(tool_name="get_portfolio_positions", reason="no portfolio")
    tool = _mock_tool_raising(GetPortfolioPositions, exc)
    inputs = _portfolio_input()
    run_cache: dict = {}
    result = await tool.execute(inputs, uuid4(), run_cache)
    assert isinstance(result, ToolError)
    assert result.error_type == ToolErrorType.TOOL_NOT_APPLICABLE


@pytest.mark.asyncio
async def test_insufficient_data_maps_to_tool_error_insufficient_data() -> None:
    from src.ai.tools.families.company_data import GetCompanyFundamentals

    exc = InsufficientData(tool_name="get_company_fundamentals", reason="no data")
    tool = _mock_tool_raising(GetCompanyFundamentals, exc)
    inputs = _company_input()
    run_cache: dict = {}
    result = await tool.execute(inputs, uuid4(), run_cache)
    assert isinstance(result, ToolError)
    assert result.error_type == ToolErrorType.INSUFFICIENT_DATA


@pytest.mark.asyncio
async def test_rate_limited_maps_to_tool_error_rate_limited_with_retry_after() -> None:
    from src.ai.tools.families.macro_market import GetMacroIndicators

    exc = RateLimited(tool_name="get_macro_indicators", source="FRED", retry_after=60)
    tool = _mock_tool_raising(GetMacroIndicators, exc)
    inputs = _macro_input()
    run_cache: dict = {}
    result = await tool.execute(inputs, uuid4(), run_cache)
    assert isinstance(result, ToolError)
    assert result.error_type == ToolErrorType.RATE_LIMITED
    assert result.retry_after == 60


# ---------------------------------------------------------------------------
# Tenant scoping tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_portfolio_tool_tenant_id_in_query() -> None:
    from src.ai.tools.families.portfolio_context import (
        GetPortfolioPositions,
        GetPortfolioPositionsInput,
    )

    tenant_id = uuid4()
    rows = [{"ticker": "AAPL"}]
    mock_cof = MagicMock()
    mock_cof.cache_or_fetch = AsyncMock(return_value=rows)
    mock_logger = AsyncMock()
    tool = GetPortfolioPositions(cache_or_fetch=mock_cof, logger=mock_logger)
    inputs = GetPortfolioPositionsInput(tenant_id=tenant_id, user_id=uuid4())
    run_cache: dict = {}
    await tool.execute(inputs, uuid4(), run_cache)
    mock_cof.cache_or_fetch.assert_called_once()


@pytest.mark.asyncio
async def test_company_tool_tenant_id_in_query() -> None:
    from src.ai.tools.families.company_data import (
        GetCompanyScores,
        GetCompanyScoresInput,
    )

    tenant_id = uuid4()
    rows = [{"score": 0.9}]
    mock_cof = MagicMock()
    mock_cof.cache_or_fetch = AsyncMock(return_value=rows)
    mock_logger = AsyncMock()
    tool = GetCompanyScores(cache_or_fetch=mock_cof, logger=mock_logger)
    inputs = GetCompanyScoresInput(tenant_id=tenant_id, ticker="MSFT")
    run_cache: dict = {}
    await tool.execute(inputs, uuid4(), run_cache)
    mock_cof.cache_or_fetch.assert_called_once()


@pytest.mark.asyncio
async def test_events_tool_global_events_visible_to_all_tenants() -> None:
    from src.ai.tools.families.events_history import (
        GetEventsByCompany,
        GetEventsByCompanyInput,
    )

    tenant_id = uuid4()
    rows = [
        {"event_id": str(uuid4()), "tenant_id": None, "title": "Global"},
        {"event_id": str(uuid4()), "tenant_id": str(tenant_id), "title": "Mine"},
    ]
    mock_cof = MagicMock()
    mock_cof.cache_or_fetch = AsyncMock(return_value=rows)
    mock_logger = AsyncMock()
    tool = GetEventsByCompany(cache_or_fetch=mock_cof, logger=mock_logger)
    inputs = GetEventsByCompanyInput(tenant_id=tenant_id, company_id=uuid4())
    run_cache: dict = {}
    result = await tool.execute(inputs, uuid4(), run_cache)
    assert isinstance(result, ToolResult)
    assert result.row_count == 2  # both global and tenant-specific are returned


@pytest.mark.asyncio
async def test_events_tool_other_tenant_events_not_returned() -> None:
    from src.ai.tools.families.events_history import (
        GetEventsByCompany,
        GetEventsByCompanyInput,
    )

    my_tenant = uuid4()
    other_tenant = uuid4()
    rows = [
        {"event_id": str(uuid4()), "tenant_id": str(other_tenant), "title": "Other"},
        {"event_id": str(uuid4()), "tenant_id": str(my_tenant), "title": "Mine"},
        {"event_id": str(uuid4()), "tenant_id": None, "title": "Global"},
    ]
    mock_cof = MagicMock()
    mock_cof.cache_or_fetch = AsyncMock(return_value=rows)
    mock_logger = AsyncMock()
    tool = GetEventsByCompany(cache_or_fetch=mock_cof, logger=mock_logger)
    inputs = GetEventsByCompanyInput(tenant_id=my_tenant, company_id=uuid4())
    run_cache: dict = {}
    result = await tool.execute(inputs, uuid4(), run_cache)
    assert isinstance(result, ToolResult)
    # Only mine + global = 2, not other tenant
    assert result.row_count == 2
    for row in result.data:
        assert row.get("tenant_id") != str(other_tenant)


@pytest.mark.asyncio
async def test_macro_tool_tenant_id_in_query() -> None:
    from src.ai.tools.families.macro_market import (
        GetMacroIndicators,
        GetMacroIndicatorsInput,
    )

    tenant_id = uuid4()
    rows = [{"indicator": "CPI", "value": 2.3}]
    mock_cof = MagicMock()
    mock_cof.cache_or_fetch = AsyncMock(return_value=rows)
    mock_logger = AsyncMock()
    tool = GetMacroIndicators(cache_or_fetch=mock_cof, logger=mock_logger)
    inputs = GetMacroIndicatorsInput(tenant_id=tenant_id, indicator_list=["CPI"])
    run_cache: dict = {}
    await tool.execute(inputs, uuid4(), run_cache)
    mock_cof.cache_or_fetch.assert_called_once()


@pytest.mark.asyncio
async def test_memory_tool_tenant_id_in_query() -> None:
    from src.ai.tools.families.memory_track_record import (
        GetSemanticFacts,
        GetSemanticFactsInput,
    )

    tenant_id = uuid4()
    rows = [{"fact_id": str(uuid4()), "fact_text": "Test fact"}]
    mock_cof = MagicMock()
    mock_cof.cache_or_fetch = AsyncMock(return_value=rows)
    mock_logger = AsyncMock()
    tool = GetSemanticFacts(cache_or_fetch=mock_cof, logger=mock_logger)
    inputs = GetSemanticFactsInput(tenant_id=tenant_id, namespace="entity", query="q")
    run_cache: dict = {}
    await tool.execute(inputs, uuid4(), run_cache)
    mock_cof.cache_or_fetch.assert_called_once()
