"""ToolCallLogger — writes every tool call to the tool_call agentic table
and optionally opens a Langfuse child span for observability.

If the DB write fails, the error is swallowed after logging at ERROR level
so that a transient DB issue never blocks an ongoing agent workflow.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.tools.base import BaseToolInput, ToolError, ToolResult

logger = logging.getLogger(__name__)

# DDL reference:
#   tool_call(tool_call_id UUID PK, invocation_id UUID, tool_name TEXT,
#             arguments JSONB, result JSONB, duration_ms INT,
#             cost_tier TEXT, cached BOOL)
_INSERT_TOOL_CALL = sa.text(
    """
    INSERT INTO tool_call (
        tool_call_id,
        invocation_id,
        tool_name,
        arguments,
        result,
        duration_ms,
        cost_tier,
        cached
    ) VALUES (
        :tool_call_id,
        :invocation_id,
        :tool_name,
        CAST(:arguments AS jsonb),
        CAST(:result AS jsonb),
        :duration_ms,
        :cost_tier,
        :cached
    )
    """
)


class ToolCallLogger:
    """Records tool call metadata to the agentic ``tool_call`` table.

    Optionally creates Langfuse child spans when a Langfuse client is provided.

    Args:
        session: Injected AsyncSession bound to the request / worker context.
        langfuse_client: Optional Langfuse client for span creation. When None,
                         only the DB write is performed.
    """

    def __init__(
        self,
        session: AsyncSession,
        langfuse_client: Any | None = None,
    ) -> None:
        self._session = session
        self._langfuse = langfuse_client

    async def log(
        self,
        *,
        tool_name: str,
        inputs: BaseToolInput,
        result: ToolResult | ToolError,
        duration_ms: int,
        cached: bool,
        invocation_id: uuid.UUID | None = None,
        cost_tier: str = "standard",
    ) -> None:
        """Write a tool_call row and optionally create a Langfuse span.

        Args:
            tool_name: Name of the tool that was executed.
            inputs: The BaseToolInput (or subclass) passed to execute().
            result: The ToolResult or ToolError returned.
            duration_ms: Wall-clock execution time in milliseconds.
            cached: True when the result came from the run-cache.
            invocation_id: Optional link to the parent agent invocation.
            cost_tier: Free-text cost tier label (default "standard").
        """
        tool_call_id = uuid.uuid4()

        # Serialize inputs and result to JSON strings for JSONB columns
        arguments_json = inputs.model_dump_json()
        result_json = result.model_dump_json()

        # --- Langfuse span (if client is available) ---
        if self._langfuse is not None:
            try:
                self._langfuse.span(
                    name=f"tool_call:{tool_name}",
                    input=arguments_json,
                    output=result_json,
                    metadata={
                        "tool_call_id": str(tool_call_id),
                        "duration_ms": duration_ms,
                        "cached": cached,
                    },
                )
            except Exception as lf_exc:
                logger.warning(
                    "Langfuse span creation failed for tool %r: %s",
                    tool_name,
                    lf_exc,
                )

        # --- DB write ---
        try:
            await self._session.execute(
                _INSERT_TOOL_CALL,
                {
                    "tool_call_id": str(tool_call_id),
                    "invocation_id": str(invocation_id) if invocation_id else None,
                    "tool_name": tool_name,
                    "arguments": arguments_json,
                    "result": result_json,
                    "duration_ms": duration_ms,
                    "cost_tier": cost_tier,
                    "cached": cached,
                },
            )
        except Exception as db_exc:
            logger.error(
                "ToolCallLogger DB write error for tool %r: %s — swallowing to avoid "
                "disrupting agent workflow",
                tool_name,
                db_exc,
            )
