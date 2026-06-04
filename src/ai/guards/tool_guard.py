"""ToolGuard — rejects tool calls not listed in the agent's YAML definition.

Every AgentNode is wrapped with a ToolGuard instantiated from
AgentDefinition.tools before the node is handed to LangGraph.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class ToolNotAllowedError(RuntimeError):
    """Raised when an agent attempts to call a tool not in its allow-list."""

    def __init__(self, tool_name: str, allowed: list[str]) -> None:
        self.tool_name = tool_name
        self.allowed = sorted(allowed)
        super().__init__(
            f"Tool {tool_name!r} is not in the agent's allow-list. "
            f"Allowed tools: {self.allowed}"
        )


class ToolGuard:
    """Enforces per-agent tool allow-lists at runtime.

    Instantiated once per agent from AgentDefinition.tools.
    Pure: no side-effects beyond logging.

    Args:
        allowed_tools: List of tool names the agent is permitted to call.
    """

    def __init__(self, allowed_tools: list[str]) -> None:
        self._allowed: frozenset[str] = frozenset(allowed_tools)
        # Keep the original sorted list for error messages
        self._allowed_sorted: list[str] = sorted(allowed_tools)

    def assert_allowed(self, tool_name: str) -> None:
        """Assert that tool_name is in the agent's allow-list.

        Args:
            tool_name: Name of the tool the agent wants to call.

        Raises:
            ToolNotAllowedError: If the tool is not in the allow-list.
        """
        if tool_name not in self._allowed:
            logger.error(
                "ToolGuard blocked disallowed tool call: tool=%r allowed=%r",
                tool_name,
                self._allowed_sorted,
            )
            raise ToolNotAllowedError(
                tool_name=tool_name,
                allowed=self._allowed_sorted,
            )
