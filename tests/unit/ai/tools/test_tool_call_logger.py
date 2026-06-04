"""Tests for ToolCallLogger (TASK-003)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.ai.tools.base import BaseToolInput, ToolError, ToolErrorType, ToolResult
from src.ai.tools.logging import ToolCallLogger


def _make_logger(
    *,
    db_fails: bool = False,
    langfuse: MagicMock | None = None,
) -> ToolCallLogger:
    session = AsyncMock()
    if db_fails:
        session.execute = AsyncMock(side_effect=RuntimeError("DB unavailable"))
    return ToolCallLogger(session=session, langfuse_client=langfuse)


@pytest.mark.asyncio
async def test_logger_writes_db_row_on_success() -> None:
    logger = _make_logger()
    inputs = BaseToolInput(tenant_id=uuid4())
    result = ToolResult(data=[{"v": 1}], truncated=False, row_count=1)

    await logger.log(
        tool_name="get_portfolio_positions",
        inputs=inputs,
        result=result,
        duration_ms=42,
        cached=False,
    )

    # Session execute was called (INSERT)
    logger._session.execute.assert_called_once()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_logger_swallows_db_error_and_logs_error(caplog: pytest.LogCaptureFixture) -> None:
    import logging

    logger = _make_logger(db_fails=True)
    inputs = BaseToolInput(tenant_id=uuid4())
    result = ToolResult(data=[], truncated=False, row_count=0)

    with caplog.at_level(logging.ERROR):
        # Must NOT raise
        await logger.log(
            tool_name="my_tool",
            inputs=inputs,
            result=result,
            duration_ms=5,
            cached=False,
        )

    assert any("DB" in r.message or "unavailable" in r.message or "error" in r.message.lower() for r in caplog.records)


@pytest.mark.asyncio
async def test_logger_with_langfuse_client_calls_langfuse() -> None:
    lf = MagicMock()
    lf.span = MagicMock(return_value=MagicMock())
    logger = _make_logger(langfuse=lf)
    inputs = BaseToolInput(tenant_id=uuid4())
    result = ToolResult(data=[], truncated=False, row_count=0)

    await logger.log(
        tool_name="get_macro_indicators",
        inputs=inputs,
        result=result,
        duration_ms=10,
        cached=False,
    )

    # Langfuse span was called
    lf.span.assert_called_once()


@pytest.mark.asyncio
async def test_logger_without_langfuse_only_writes_db() -> None:
    logger = _make_logger(langfuse=None)
    inputs = BaseToolInput(tenant_id=uuid4())
    result = ToolResult(data=[], truncated=False, row_count=0)

    # Should not raise
    await logger.log(
        tool_name="get_portfolio_positions",
        inputs=inputs,
        result=result,
        duration_ms=8,
        cached=True,
    )

    logger._session.execute.assert_called_once()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_logger_records_cached_flag() -> None:
    logger = _make_logger()
    inputs = BaseToolInput(tenant_id=uuid4())
    result = ToolResult(data=[], truncated=False, row_count=0)

    await logger.log(
        tool_name="get_portfolio_positions",
        inputs=inputs,
        result=result,
        duration_ms=0,
        cached=True,
    )

    call_args = logger._session.execute.call_args  # type: ignore[attr-defined]
    # The statement parameters should include cached=True
    # (second positional arg to execute is the params dict)
    positional_args = call_args.args if hasattr(call_args, "args") else call_args[0]
    params = positional_args[1] if len(positional_args) > 1 else {}
    assert params.get("cached") is True
