"""Tests for ToolRegistry (TASK-003)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.ai.tools.base import BaseTool, BaseToolInput
from src.ai.tools.registry import ToolNotFoundError, ToolRegistry


def _make_mock_tool(name: str) -> BaseTool:
    tool = MagicMock(spec=BaseTool)
    tool.name = name
    return tool


def test_registry_resolves_registered_tool() -> None:
    registry = ToolRegistry()
    tool = _make_mock_tool("get_portfolio_positions")
    registry.register(tool)
    resolved = registry.resolve("get_portfolio_positions")
    assert resolved is tool


def test_registry_resolve_raises_tool_not_found_for_unknown_name() -> None:
    registry = ToolRegistry()
    registry.register(_make_mock_tool("get_portfolio_positions"))
    with pytest.raises(ToolNotFoundError) as exc_info:
        registry.resolve("nonexistent_tool")
    assert "nonexistent_tool" in str(exc_info.value)
    assert "get_portfolio_positions" in str(exc_info.value)


def test_registry_resolve_is_case_sensitive() -> None:
    registry = ToolRegistry()
    registry.register(_make_mock_tool("get_Portfolio_Positions"))
    with pytest.raises(ToolNotFoundError):
        registry.resolve("get_portfolio_positions")


def test_registry_all_tools_returns_all_registered() -> None:
    registry = ToolRegistry()
    tool_a = _make_mock_tool("tool_a")
    tool_b = _make_mock_tool("tool_b")
    registry.register(tool_a)
    registry.register(tool_b)
    all_tools = registry.all_tools()
    assert len(all_tools) == 2
    names = {t.name for t in all_tools}
    assert names == {"tool_a", "tool_b"}


def test_tool_not_found_error_includes_available_list() -> None:
    err = ToolNotFoundError("missing_tool", available=["tool_a", "tool_b"])
    assert "missing_tool" in str(err)
    assert "tool_a" in str(err)
    assert "tool_b" in str(err)
