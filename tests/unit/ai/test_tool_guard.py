"""Unit tests for ToolGuard.

TDD: tests written before implementation.
"""
from __future__ import annotations

import pytest

from src.ai.guards.tool_guard import ToolGuard, ToolNotAllowedError


class TestAllowedToolDoesNotRaise:
    def test_allowed_tool_does_not_raise(self) -> None:
        """A tool that is in the allowed list passes silently."""
        guard = ToolGuard(allowed_tools=["query_portfolio", "get_market_data"])
        # Should not raise
        guard.assert_allowed("query_portfolio")
        guard.assert_allowed("get_market_data")


class TestDisallowedToolRaisesToolNotAllowedError:
    def test_disallowed_tool_raises_tool_not_allowed_error(self) -> None:
        """A tool not in the allowed list raises ToolNotAllowedError."""
        guard = ToolGuard(allowed_tools=["query_portfolio"])

        with pytest.raises(ToolNotAllowedError) as exc_info:
            guard.assert_allowed("delete_portfolio")

        err = exc_info.value
        assert err.tool_name == "delete_portfolio"


class TestErrorIncludesAllowedToolsList:
    def test_error_includes_allowed_tools_list(self) -> None:
        """The exception .allowed attribute lists all permitted tools (sorted)."""
        allowed = ["get_market_data", "query_portfolio", "search_news"]
        guard = ToolGuard(allowed_tools=allowed)

        with pytest.raises(ToolNotAllowedError) as exc_info:
            guard.assert_allowed("nonexistent_tool")

        assert exc_info.value.allowed == sorted(allowed)


class TestGuardIsCaseSensitive:
    def test_guard_is_case_sensitive(self) -> None:
        """Tool name matching is case-sensitive: 'GetPortfolio' != 'get_portfolio'."""
        guard = ToolGuard(allowed_tools=["get_portfolio"])

        with pytest.raises(ToolNotAllowedError):
            guard.assert_allowed("GetPortfolio")


class TestEmptyToolsListBlocksAllToolCalls:
    def test_empty_tools_list_blocks_all_tool_calls(self) -> None:
        """An agent with tools=[] blocks every tool call."""
        guard = ToolGuard(allowed_tools=[])

        with pytest.raises(ToolNotAllowedError):
            guard.assert_allowed("get_market_data")

        with pytest.raises(ToolNotAllowedError):
            guard.assert_allowed("any_tool")
