"""Tool-domain exceptions.

These are raised by concrete tool _execute() methods and automatically
mapped to ToolError variants by BaseTool.execute().
"""
from __future__ import annotations


class ToolNotApplicable(Exception):
    """Raised when a tool cannot be applied to the given inputs.

    For example, get_portfolio_positions when the user has no portfolio.

    Args:
        tool_name: Name of the tool raising the exception.
        reason: Human-readable explanation of why the tool is not applicable.
    """

    def __init__(self, tool_name: str, reason: str) -> None:
        self.tool_name = tool_name
        self.reason = reason
        super().__init__(f"[{tool_name}] ToolNotApplicable: {reason}")


class InsufficientData(Exception):
    """Raised when a tool cannot return a meaningful result due to missing data.

    For example, requesting scores for a company that has never been scored.

    Args:
        tool_name: Name of the tool raising the exception.
        reason: Human-readable explanation of what data is missing.
    """

    def __init__(self, tool_name: str, reason: str) -> None:
        self.tool_name = tool_name
        self.reason = reason
        super().__init__(f"[{tool_name}] InsufficientData: {reason}")


class RateLimited(Exception):
    """Raised when an upstream data source enforces a rate limit.

    Args:
        tool_name: Name of the tool raising the exception.
        source: Name of the upstream source that is rate-limiting (e.g. "FRED").
        retry_after: Seconds until the caller may retry, or None if unknown.
    """

    def __init__(
        self, tool_name: str, source: str, retry_after: int | None = None
    ) -> None:
        self.tool_name = tool_name
        self.source = source
        self.retry_after = retry_after
        msg = f"[{tool_name}] RateLimited by {source}"
        if retry_after is not None:
            msg += f" — retry after {retry_after}s"
        super().__init__(msg)
