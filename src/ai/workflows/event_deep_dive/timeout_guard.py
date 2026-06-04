"""
ai.workflows.event_deep_dive.timeout_guard — asyncio.timeout context manager wrapper.

WorkflowTimeoutGuard wraps code under an asyncio.timeout() context manager
and converts asyncio.TimeoutError into WorkflowTimeoutError carrying elapsed
time metadata.

PLAN-F-010 TASK-003.
"""
from __future__ import annotations

import asyncio
import time
from types import TracebackType

from src.ai.workflows.event_deep_dive.exceptions import WorkflowTimeoutError


class WorkflowTimeoutGuard:
    """Async context manager that enforces a hard time limit on a workflow.

    Usage::

        async with WorkflowTimeoutGuard(hard_limit_seconds=900):
            result = await graph.ainvoke(state)

    Raises:
        WorkflowTimeoutError: If the body exceeds *hard_limit_seconds*.
    """

    def __init__(self, hard_limit_seconds: float) -> None:
        self._limit = hard_limit_seconds
        self._start: float = 0.0

    async def __aenter__(self) -> "WorkflowTimeoutGuard":
        self._start = time.monotonic()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> bool:
        if exc_type is asyncio.TimeoutError:
            elapsed = time.monotonic() - self._start
            raise WorkflowTimeoutError(elapsed_seconds=elapsed) from exc_val
        return False

    # Allow usage as `async with WorkflowTimeoutGuard(...): await some_task()`
    # by wrapping the body in asyncio.wait_for via __aenter__/__aexit__ pair.

    async def run(self, coro):  # type: ignore[override]
        """Await *coro* inside an asyncio.timeout context.

        Convenience method for code that cannot use the context-manager syntax.
        """
        try:
            return await asyncio.wait_for(coro, timeout=self._limit)
        except asyncio.TimeoutError:
            elapsed = time.monotonic() - self._start
            raise WorkflowTimeoutError(elapsed_seconds=elapsed)

    # ── Internal async context that actually enforces the timeout ─────────────

    def __class_getitem__(cls, item):
        return cls

    # Override to use asyncio.timeout properly
    async def __aenter__(self) -> "WorkflowTimeoutGuard":  # type: ignore[override]
        self._start = time.monotonic()
        self._timeout_ctx = asyncio.timeout(self._limit)
        await self._timeout_ctx.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> bool:
        try:
            suppress = await self._timeout_ctx.__aexit__(exc_type, exc_val, exc_tb)
        except asyncio.TimeoutError:
            elapsed = time.monotonic() - self._start
            raise WorkflowTimeoutError(elapsed_seconds=elapsed) from None

        if exc_type is asyncio.TimeoutError:
            elapsed = time.monotonic() - self._start
            raise WorkflowTimeoutError(elapsed_seconds=elapsed) from exc_val

        return bool(suppress)
