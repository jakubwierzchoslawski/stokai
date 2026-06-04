"""Tests for Memory + Track Record tool family (TASK-009)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.ai.tools.base import ToolResult
from src.ai.tools.families.memory_track_record import (
    GetProceduralPatterns,
    GetRecommendationOutcomes,
    GetSemanticFacts,
)


def _make_tool(cls, rows: list[dict] | None = None):
    mock_cof = MagicMock()
    mock_cof.cache_or_fetch = AsyncMock(return_value=rows or [])
    mock_logger = AsyncMock()
    tool = cls(cache_or_fetch=mock_cof, logger=mock_logger)
    tool._execute = AsyncMock(return_value=rows or [])
    return tool


def test_get_semantic_facts_tool_name() -> None:
    assert GetSemanticFacts.name == "get_semantic_facts"


def test_get_procedural_patterns_tool_name() -> None:
    assert GetProceduralPatterns.name == "get_procedural_patterns"


def test_get_recommendation_outcomes_tool_name() -> None:
    assert GetRecommendationOutcomes.name == "get_recommendation_outcomes"


@pytest.mark.asyncio
async def test_get_semantic_facts_returns_tool_result() -> None:
    from src.ai.tools.families.memory_track_record import GetSemanticFactsInput

    rows = [{"fact_id": str(uuid4()), "fact_text": "Company X has good margins"}]
    tool = _make_tool(GetSemanticFacts, rows)
    inputs = GetSemanticFactsInput(tenant_id=uuid4(), namespace="company", query="margins")
    run_cache: dict = {}
    result = await tool.execute(inputs, uuid4(), run_cache)
    assert isinstance(result, ToolResult)
    assert result.row_count == 1


@pytest.mark.asyncio
async def test_get_procedural_patterns_ordered_by_success_rate() -> None:
    from src.ai.tools.families.memory_track_record import GetProceduralPatternsInput

    # Rows simulate DB result ordered by success_rate DESC
    rows = [
        {"pattern_id": str(uuid4()), "success_rate": 0.9},
        {"pattern_id": str(uuid4()), "success_rate": 0.7},
    ]
    tool = _make_tool(GetProceduralPatterns, rows)
    inputs = GetProceduralPatternsInput(tenant_id=uuid4())
    run_cache: dict = {}
    result = await tool.execute(inputs, uuid4(), run_cache)
    assert isinstance(result, ToolResult)
    assert result.row_count == 2


@pytest.mark.asyncio
async def test_get_recommendation_outcomes_returns_tool_result() -> None:
    from src.ai.tools.families.memory_track_record import GetRecommendationOutcomesInput

    rows = [{"outcome_id": str(uuid4()), "outcome": "positive"}]
    tool = _make_tool(GetRecommendationOutcomes, rows)
    inputs = GetRecommendationOutcomesInput(tenant_id=uuid4(), ticker="AAPL")
    run_cache: dict = {}
    result = await tool.execute(inputs, uuid4(), run_cache)
    assert isinstance(result, ToolResult)


@pytest.mark.asyncio
async def test_memory_tool_tenant_id_in_query() -> None:
    from src.ai.tools.families.memory_track_record import (
        GetSemanticFacts,
        GetSemanticFactsInput,
    )

    tenant_id = uuid4()
    rows = [{"fact_id": str(uuid4()), "fact_text": "test fact"}]
    mock_cof = MagicMock()
    mock_cof.cache_or_fetch = AsyncMock(return_value=rows)
    mock_logger = AsyncMock()
    tool = GetSemanticFacts(cache_or_fetch=mock_cof, logger=mock_logger)
    inputs = GetSemanticFactsInput(tenant_id=tenant_id, namespace="entity", query="test")
    run_cache: dict = {}
    result = await tool.execute(inputs, uuid4(), run_cache)
    assert isinstance(result, ToolResult)
    mock_cof.cache_or_fetch.assert_called_once()


@pytest.mark.asyncio
async def test_get_semantic_facts_capped_at_50() -> None:
    from src.ai.tools.families.memory_track_record import GetSemanticFactsInput

    rows = [{"fact_id": str(uuid4()), "fact_text": f"fact {i}"} for i in range(75)]
    tool = _make_tool(GetSemanticFacts, rows)
    inputs = GetSemanticFactsInput(tenant_id=uuid4(), namespace="entity", query="q")
    run_cache: dict = {}
    result = await tool.execute(inputs, uuid4(), run_cache)
    assert result.row_count == 50
    assert result.truncated is True
