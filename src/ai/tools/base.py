"""BaseTool ABC, ToolResult, ToolError, ToolCacheEntry, BaseToolInput.

All tool families inherit from BaseTool. The execute() method encodes:
  - Per-workflow run-cache (keyed on run_id:tool_name:args_hash)
  - 50-row bounded output via ToolResult.from_rows()
  - Standard error mapping (ToolNotApplicable, InsufficientData, RateLimited)
  - Delegation of timing + DB writes to ToolCallLogger
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from abc import ABC, abstractmethod
from enum import StrEnum
from typing import TYPE_CHECKING, Any
from uuid import UUID

from pydantic import BaseModel, Field

from src.ai.tools.exceptions import InsufficientData, RateLimited, ToolNotApplicable

if TYPE_CHECKING:
    from src.ai.tools.logging import ToolCallLogger
    from ingestion.cache_or_fetch import CacheOrFetch

logger = logging.getLogger(__name__)

MAX_ROWS = 50


# ---------------------------------------------------------------------------
# ToolErrorType
# ---------------------------------------------------------------------------


class ToolErrorType(StrEnum):
    """Enumeration of structured error types returned by tools."""

    TOOL_NOT_APPLICABLE = "ToolNotApplicable"
    INSUFFICIENT_DATA = "InsufficientData"
    RATE_LIMITED = "RateLimited"


# ---------------------------------------------------------------------------
# ToolResult
# ---------------------------------------------------------------------------


class ToolResult(BaseModel):
    """Bounded result returned by every successful tool call.

    Attributes:
        data: Up to MAX_ROWS rows of data.
        truncated: True when the source had more than MAX_ROWS rows.
        row_count: Actual number of rows in data (always <= MAX_ROWS).
    """

    data: list[dict[str, Any]] = Field(max_length=MAX_ROWS)
    truncated: bool = False
    row_count: int

    @classmethod
    def from_rows(cls, rows: list[dict[str, Any]]) -> "ToolResult":
        """Build a ToolResult, truncating to MAX_ROWS if necessary.

        Args:
            rows: Raw rows from the data source.

        Returns:
            A bounded ToolResult with truncated flag set if rows exceeded MAX_ROWS.
        """
        truncated = len(rows) > MAX_ROWS
        bounded = rows[:MAX_ROWS]
        return cls(data=bounded, truncated=truncated, row_count=len(bounded))


# ---------------------------------------------------------------------------
# ToolError
# ---------------------------------------------------------------------------


class ToolError(BaseModel):
    """Structured error returned when a tool cannot complete its work.

    JSON-serializable via Pydantic's model_dump_json().

    Attributes:
        error_type: Enum discriminating the error class.
        message: Human-readable explanation.
        retry_after: Seconds until retry is sensible (RATE_LIMITED only).
    """

    error_type: ToolErrorType
    message: str
    retry_after: int | None = None


# ---------------------------------------------------------------------------
# ToolCacheEntry
# ---------------------------------------------------------------------------


class ToolCacheEntry(BaseModel):
    """An entry in the per-workflow-run tool cache.

    The composite key (run_id, tool_name, args_hash) uniquely identifies a
    previously-executed tool call within a single workflow run.

    Attributes:
        run_id: UUID of the workflow run.
        tool_name: Name of the tool that produced this entry.
        args_hash: SHA-256 hex digest (8 chars) of the tool inputs
                   excluding tenant_id.
        result: The bounded ToolResult from the tool execution.
    """

    run_id: UUID
    tool_name: str
    args_hash: str
    result: ToolResult


# ---------------------------------------------------------------------------
# BaseToolInput
# ---------------------------------------------------------------------------


class BaseToolInput(BaseModel):
    """Minimum input every tool must accept.

    tenant_id is required on every call for multi-tenant isolation.
    """

    tenant_id: UUID


# ---------------------------------------------------------------------------
# BaseTool
# ---------------------------------------------------------------------------


class BaseTool(ABC):
    """Abstract base class for all tool implementations.

    Subclasses must define:
        name (class attribute): unique tool name used by ToolRegistry
        _execute(inputs): returns list[dict] (raw rows, <= MAX_ROWS enforced by execute())

    Constructor injects:
        cache_or_fetch: CacheOrFetch cascade from PLAN-F-032
        logger: ToolCallLogger that handles DB write + Langfuse span
    """

    name: str

    def __init__(
        self,
        cache_or_fetch: "CacheOrFetch",
        logger: "ToolCallLogger",
    ) -> None:
        self._cache_or_fetch = cache_or_fetch
        self._logger = logger

    # ------------------------------------------------------------------
    # Public execute — run-cache + error mapping + logger
    # ------------------------------------------------------------------

    async def execute(
        self,
        inputs: BaseToolInput,
        run_id: UUID,
        run_cache: dict[str, ToolResult],
    ) -> ToolResult | ToolError:
        """Execute the tool with run-level caching and error mapping.

        Steps:
        1. Compute args_hash from inputs excluding tenant_id.
        2. Build run-cache key: f"{run_id}:{self.name}:{args_hash}".
        3. Return cached ToolResult on hit (log cached=True).
        4. On miss, call _execute(), wrap with ToolResult.from_rows(),
           store in run_cache (log cached=False).
        5. Map known exceptions to ToolError; let unknown exceptions propagate.

        Args:
            inputs: Pydantic model with at least tenant_id.
            run_id: UUID of the current workflow run.
            run_cache: Shared dict for the current run; mutated in place.

        Returns:
            ToolResult on success, ToolError on handled exception.

        Raises:
            Any exception not in (ToolNotApplicable, InsufficientData, RateLimited).
        """
        # Step 1 & 2: compute cache key
        args_hash = self._compute_args_hash(inputs)
        cache_key = f"{run_id}:{self.name}:{args_hash}"

        # Step 3: cache hit
        if cache_key in run_cache:
            await self._logger.log(
                tool_name=self.name,
                inputs=inputs,
                result=run_cache[cache_key],
                duration_ms=0,
                cached=True,
            )
            return run_cache[cache_key]

        # Step 4: cache miss — call _execute
        start = time.monotonic()
        try:
            raw_rows = await self._execute(inputs)
            result = ToolResult.from_rows(raw_rows)
            run_cache[cache_key] = result
            duration_ms = int((time.monotonic() - start) * 1000)
            await self._logger.log(
                tool_name=self.name,
                inputs=inputs,
                result=result,
                duration_ms=duration_ms,
                cached=False,
            )
            return result

        # Step 5: map known exceptions
        except ToolNotApplicable as exc:
            duration_ms = int((time.monotonic() - start) * 1000)
            error = ToolError(
                error_type=ToolErrorType.TOOL_NOT_APPLICABLE,
                message=str(exc),
            )
            await self._logger.log(
                tool_name=self.name,
                inputs=inputs,
                result=error,
                duration_ms=duration_ms,
                cached=False,
            )
            return error

        except InsufficientData as exc:
            duration_ms = int((time.monotonic() - start) * 1000)
            error = ToolError(
                error_type=ToolErrorType.INSUFFICIENT_DATA,
                message=str(exc),
            )
            await self._logger.log(
                tool_name=self.name,
                inputs=inputs,
                result=error,
                duration_ms=duration_ms,
                cached=False,
            )
            return error

        except RateLimited as exc:
            duration_ms = int((time.monotonic() - start) * 1000)
            error = ToolError(
                error_type=ToolErrorType.RATE_LIMITED,
                message=str(exc),
                retry_after=exc.retry_after,
            )
            await self._logger.log(
                tool_name=self.name,
                inputs=inputs,
                result=error,
                duration_ms=duration_ms,
                cached=False,
            )
            return error

        # Unknown exceptions propagate uncaught

    # ------------------------------------------------------------------
    # Abstract
    # ------------------------------------------------------------------

    @abstractmethod
    async def _execute(self, inputs: BaseToolInput) -> list[dict[str, Any]]:
        """Fetch raw rows for this tool call.

        Must be implemented by every concrete tool.  The return value is
        automatically bounded to MAX_ROWS by execute().
        """

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_args_hash(inputs: BaseToolInput) -> str:
        """Compute a deterministic hash of inputs, excluding tenant_id.

        Two inputs that differ only in tenant_id will produce the same hash,
        since caching is functional (content-based), not identity-based.

        Returns:
            8-character hex prefix of a SHA-256 digest.
        """
        data = inputs.model_dump(mode="json")
        data.pop("tenant_id", None)
        serialized = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode()).hexdigest()[:8]
