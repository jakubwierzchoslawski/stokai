"""ToolRegistry — maps tool names to BaseTool instances.

Instantiated once at startup by initialise_ai_module(), stored on app.state.
"""
from __future__ import annotations

from typing import Protocol

from src.ai.tools.base import BaseTool


# ---------------------------------------------------------------------------
# ToolNotFoundError
# ---------------------------------------------------------------------------


class ToolNotFoundError(KeyError):
    """Raised when resolve() is called with an unknown tool name.

    Args:
        tool_name: The name that was not found.
        available: Sorted list of registered tool names for the error message.
    """

    def __init__(self, tool_name: str, available: list[str]) -> None:
        self.tool_name = tool_name
        self.available = sorted(available)
        super().__init__(
            f"Tool {tool_name!r} not found. Available tools: {self.available}"
        )


# ---------------------------------------------------------------------------
# IToolRegistry protocol
# ---------------------------------------------------------------------------


class IToolRegistry(Protocol):
    """Protocol for ToolRegistry.  Inject this type at call sites."""

    def resolve(self, tool_name: str) -> BaseTool:
        """Return the BaseTool registered under tool_name.

        Raises:
            ToolNotFoundError: If no tool with that name is registered.
        """
        ...

    def all_tools(self) -> list[BaseTool]:
        """Return all registered BaseTool instances (order is stable)."""
        ...


# ---------------------------------------------------------------------------
# ToolRegistry
# ---------------------------------------------------------------------------


class ToolRegistry:
    """Concrete implementation of IToolRegistry.

    Call register() once per tool at startup, then resolve() at runtime.

    Resolution is case-sensitive so tool names in agent YAML must match exactly.
    """

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """Register a tool instance under its name.

        Overwrites any previous registration for the same name.

        Args:
            tool: A concrete BaseTool subclass with a valid name attribute.
        """
        self._tools[tool.name] = tool

    def resolve(self, tool_name: str) -> BaseTool:
        """Return the tool registered under tool_name.

        Args:
            tool_name: Exact (case-sensitive) name of the tool.

        Raises:
            ToolNotFoundError: If no tool with that name is registered.
        """
        try:
            return self._tools[tool_name]
        except KeyError:
            raise ToolNotFoundError(
                tool_name=tool_name,
                available=list(self._tools.keys()),
            ) from None

    def all_tools(self) -> list[BaseTool]:
        """Return all registered tools (insertion order)."""
        return list(self._tools.values())
