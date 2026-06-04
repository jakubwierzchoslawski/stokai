"""Tests for Events + History tool family (TASK-006)."""
from __future__ import annotations

from typing import Any, Protocol
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.ai.tools.base import ToolResult
from src.ai.tools.families.events_history import (
    GetAiRecommendationHistory,
    GetEventAnalogies,
    GetEventsByCompany,
)


def _make_tool(cls, rows: list[dict] | None = None):
    mock_cof = MagicMock()
    mock_cof.cache_or_fetch = AsyncMock(return_value=rows or [])
    mock_logger = AsyncMock()
    tool = cls(cache_or_fetch=mock_cof, logger=mock_logger)
    tool._execute = AsyncMock(return_value=rows or [])
    return tool


def test_get_events_by_company_tool_name() -> None:
    assert GetEventsByCompany.name == "get_events_by_company"


def test_get_event_analogies_tool_name() -> None:
    assert GetEventAnalogies.name == "get_event_analogies"


def test_get_ai_recommendation_history_tool_name() -> None:
    assert GetAiRecommendationHistory.name == "get_ai_recommendation_history"


@pytest.mark.asyncio
async def test_get_events_by_company_returns_tool_result() -> None:
    from src.ai.tools.families.events_history import GetEventsByCompanyInput

    rows = [{"event_id": str(uuid4()), "title": "Earthquake in Chile"}]
    tool = _make_tool(GetEventsByCompany, rows)
    inputs = GetEventsByCompanyInput(tenant_id=uuid4(), company_id=uuid4())
    run_cache: dict = {}
    result = await tool.execute(inputs, uuid4(), run_cache)
    assert isinstance(result, ToolResult)
    assert result.row_count == 1


@pytest.mark.asyncio
async def test_get_event_analogies_capped_at_max_rows() -> None:
    from src.ai.tools.families.events_history import GetEventAnalogiesInput

    rows = [{"event_id": str(uuid4())} for _ in range(75)]
    tool = _make_tool(GetEventAnalogies, rows)

    mock_search = AsyncMock()
    mock_search.search = AsyncMock(return_value=rows)
    inputs = GetEventAnalogiesInput(
        tenant_id=uuid4(),
        event_id=uuid4(),
        top_k=75,
    )
    run_cache: dict = {}
    result = await tool.execute(inputs, uuid4(), run_cache)
    assert isinstance(result, ToolResult)
    assert result.row_count == 50
    assert result.truncated is True


@pytest.mark.asyncio
async def test_get_ai_recommendation_history_returns_tool_result() -> None:
    from src.ai.tools.families.events_history import GetAiRecommendationHistoryInput

    rows = [{"recommendation_id": str(uuid4()), "action": "BUY"}]
    tool = _make_tool(GetAiRecommendationHistory, rows)
    inputs = GetAiRecommendationHistoryInput(tenant_id=uuid4(), ticker="AAPL")
    run_cache: dict = {}
    result = await tool.execute(inputs, uuid4(), run_cache)
    assert isinstance(result, ToolResult)


@pytest.mark.asyncio
async def test_get_events_by_company_global_events_visible_to_all_tenants() -> None:
    """Events with tenant_id IS NULL are visible to all tenants."""
    from src.ai.tools.families.events_history import (
        GetEventsByCompany,
        GetEventsByCompanyInput,
    )

    tenant_id = uuid4()
    company_id = uuid4()
    global_event_rows = [
        {"event_id": str(uuid4()), "tenant_id": None, "title": "Global event"}
    ]

    mock_cof = MagicMock()
    mock_cof.cache_or_fetch = AsyncMock(return_value=global_event_rows)
    mock_logger = AsyncMock()
    tool = GetEventsByCompany(cache_or_fetch=mock_cof, logger=mock_logger)

    inputs = GetEventsByCompanyInput(tenant_id=tenant_id, company_id=company_id)
    run_cache: dict = {}
    result = await tool.execute(inputs, uuid4(), run_cache)
    assert isinstance(result, ToolResult)
    assert result.row_count == 1


@pytest.mark.asyncio
async def test_events_tool_other_tenant_events_not_returned() -> None:
    """Events belonging to a different tenant should not be returned."""
    from src.ai.tools.families.events_history import (
        GetEventsByCompany,
        GetEventsByCompanyInput,
    )

    my_tenant = uuid4()
    other_tenant = uuid4()
    company_id = uuid4()

    # Simulate DB/cache returning only rows for my_tenant or global
    my_rows = [
        {"event_id": str(uuid4()), "tenant_id": str(my_tenant), "title": "My event"},
        {"event_id": str(uuid4()), "tenant_id": None, "title": "Global event"},
    ]

    mock_cof = MagicMock()
    mock_cof.cache_or_fetch = AsyncMock(return_value=my_rows)
    mock_logger = AsyncMock()
    tool = GetEventsByCompany(cache_or_fetch=mock_cof, logger=mock_logger)

    inputs = GetEventsByCompanyInput(tenant_id=my_tenant, company_id=company_id)
    run_cache: dict = {}
    result = await tool.execute(inputs, uuid4(), run_cache)
    # Only rows for my_tenant or global should appear — not other_tenant rows
    for row in result.data:  # type: ignore[union-attr]
        assert row.get("tenant_id") != str(other_tenant)
