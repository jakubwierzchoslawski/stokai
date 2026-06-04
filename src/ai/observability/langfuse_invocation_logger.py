"""LangfuseInvocationLogger — context-manager decorator for agent invocation tracing.

REQ-N-008: every agent invocation logs prompt_version (git SHA) to Langfuse span.

On entry:
1. Resolves the git SHA of the agent's system_prompt_file.
2. Opens a Langfuse span with metadata: agent_role_id, model_id, prompt_version,
   workflow_id, tenant_id.

On exit:
3. Records cost_usd, input_tokens, output_tokens, confidence, latency_ms.
4. Closes the span.

If Langfuse client is None (LANGFUSE_HOST not configured), all operations are no-ops.
Git SHA resolution falls back to "unknown" if git is unavailable.
"""
from __future__ import annotations

import logging
import subprocess
import time
from types import TracebackType
from typing import Any

from src.ai.registry.agent_definition import AgentDefinition

logger = logging.getLogger(__name__)


def _resolve_git_sha(file_path: str) -> str:
    """Return the most recent git commit SHA for the given file path.

    Falls back to "unknown" if git is unavailable or the file is untracked.

    Args:
        file_path: Relative or absolute path to the prompt file.

    Returns:
        40-character hex SHA, or "unknown".
    """
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%H", file_path],
            capture_output=True,
            text=True,
            check=False,
        )
        sha = result.stdout.strip()
        return sha if sha else "unknown"
    except (FileNotFoundError, OSError):
        return "unknown"


class _InvocationContext:
    """Holds the active Langfuse span and provides record_usage()."""

    def __init__(self, span: Any | None) -> None:
        self._span = span
        self._usage: dict = {}

    def record_usage(
        self,
        cost_usd: float = 0.0,
        input_tokens: int = 0,
        output_tokens: int = 0,
        confidence: float | None = None,
        latency_ms: float | None = None,
    ) -> None:
        """Record usage metrics to be flushed when the span closes.

        Args:
            cost_usd: Estimated USD cost of the invocation.
            input_tokens: Number of input tokens consumed.
            output_tokens: Number of output tokens generated.
            confidence: Agent confidence score (0.0–1.0).
            latency_ms: Wall-clock latency in milliseconds.
        """
        self._usage = {
            "cost_usd": cost_usd,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "confidence": confidence,
            "latency_ms": latency_ms,
        }

    def _close(self, latency_ms: float) -> None:
        if self._span is None:
            return
        if not self._usage.get("latency_ms"):
            self._usage["latency_ms"] = latency_ms
        try:
            self._span.update(output=self._usage)
            self._span.end()
        except Exception:
            logger.exception("Failed to close Langfuse span")


class LangfuseInvocationLogger:
    """Context-manager that opens/closes a Langfuse span around an agent invocation.

    Args:
        definition: The AgentDefinition for the agent being invoked.
        langfuse_client: An initialised Langfuse client, or None to no-op.
        workflow_id: Identifier for the enclosing workflow run.
        tenant_id: Tenant identifier attached to every span (security).
    """

    def __init__(
        self,
        definition: AgentDefinition,
        langfuse_client: Any | None,
        workflow_id: str,
        tenant_id: str,
    ) -> None:
        self._definition = definition
        self._client = langfuse_client
        self._workflow_id = workflow_id
        self._tenant_id = tenant_id
        self._ctx: _InvocationContext | None = None
        self._start_time: float = 0.0

    def __enter__(self) -> _InvocationContext:
        self._start_time = time.monotonic()
        self._ctx = self._open_span()
        return self._ctx

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        elapsed_ms = (time.monotonic() - self._start_time) * 1000.0
        if self._ctx is not None:
            self._ctx._close(latency_ms=elapsed_ms)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _open_span(self) -> _InvocationContext:
        if self._client is None:
            return _InvocationContext(span=None)

        prompt_version = _resolve_git_sha(self._definition.system_prompt_file)

        try:
            trace = self._client.trace(
                name=f"agent-invocation:{self._definition.role_id}",
                metadata={
                    "workflow_id": self._workflow_id,
                    "tenant_id": self._tenant_id,
                },
            )
            span = trace.span(
                name=self._definition.role_id,
                metadata={
                    "agent_role_id": self._definition.role_id,
                    "model_id": self._definition.model.model_id,
                    "prompt_version": prompt_version,
                    "workflow_id": self._workflow_id,
                    "tenant_id": self._tenant_id,
                },
            )
            return _InvocationContext(span=span)
        except Exception:
            logger.exception(
                "Failed to open Langfuse span for agent=%s",
                self._definition.role_id,
            )
            return _InvocationContext(span=None)
