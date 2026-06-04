"""Public surface for the ai.tools package.

Exports: ToolRegistry, BaseTool, ToolResult, ToolError, ToolCacheEntry,
         BaseToolInput, ToolErrorType, ToolCallLogger, ToolNotFoundError.
"""
from src.ai.tools.base import (
    MAX_ROWS,
    BaseTool,
    BaseToolInput,
    ToolCacheEntry,
    ToolError,
    ToolErrorType,
    ToolResult,
)
from src.ai.tools.logging import ToolCallLogger
from src.ai.tools.registry import IToolRegistry, ToolNotFoundError, ToolRegistry

__all__ = [
    "MAX_ROWS",
    "BaseTool",
    "BaseToolInput",
    "ToolCacheEntry",
    "ToolError",
    "ToolErrorType",
    "ToolResult",
    "ToolCallLogger",
    "IToolRegistry",
    "ToolNotFoundError",
    "ToolRegistry",
]
