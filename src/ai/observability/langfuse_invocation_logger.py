"""LangfuseInvocationLogger — context-manager decorator for agent invocation tracing.

REQ-N-008 / PLAN-F-014 TASK-008 (AC-004):
Every agent invocation logs prompt_version (git blob SHA) to the Langfuse span.

SHA resolution order:
1. IPromptLoader.get_sha(role_id) — git blob SHA of the prompt file (preferred).
2. git log -1 --format=%H <file_path> — commit SHA fallback when no loader is injected.
3. "unknown" — if git is unavailable or the role has no prompt file.

On entry:
1. Resolves the git blob SHA via IPromptLoader.get_sha(role_id) or git log fallback.
2. Opens a Langfuse span with metadata: agent_role_id, model_id, prompt_version,
   workflow_id, tenant_id.

On exit:
3. Records cost_usd, input_tokens, output_tokens, confidence, latency_ms.
4. Closes the span.

If Langfuse client is None (LANGFUSE_HOST not configured), all operations are no-ops.
"""
from __future__ import annotations

import logging
import subprocess
import time
from types import TracebackType
from typing import Any

from src.ai.registry.agent_definition import AgentDefinition

logger = logging.getLogger(__name__)


def _role_id_to_snake(role_id: str) -> str:
    """Convert kebab-case role_id to snake_case for prompt file lookup.

    e.g. 'relevance-analyst' -> 'relevance_analyst'
    """
    return role_id.replace("-", "_")


def _resolve_git_sha(file_path: str) -> str:
    """Return the most recent git commit SHA for the given file path.

    Used as a fallback when no IPromptLoader is injected.
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


def _resolve_prompt_version(
    role_id: str,
    system_prompt_file: str,
    prompt_loader: Any | None,
) -> str:
    """Resolve prompt_version (git blob SHA) for the given role.

    Resolution order:
    1. IPromptLoader.get_sha(snake_role_id) — blob SHA (preferred, AC-004).
    2. git log fallback on system_prompt_file.
    3. "unknown" on any error.

    Args:
        role_id: Agent role identifier (kebab-case).
        system_prompt_file: Path to the system prompt file (fallback).
        prompt_loader: Optional IPromptLoader instance.

    Returns:
        40-char hex SHA or "unknown".
    """
    if prompt_loader is not None:
        snake_role_id = _role_id_to_snake(role_id)
        try:
            return prompt_loader.get_sha(snake_role_id)
        except FileNotFoundError:
            logger.warning(
                "PromptLoader: no prompt file for role_id=%s; using 'unknown'", role_id
            )
            return "unknown"
        except RuntimeError:
            # Re-raise non-FileNotFoundError errors (per TASK-008 spec)
            raise

    # No loader injected — fall back to git log on the file path
    return _resolve_git_sha(system_prompt_file)


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
        prompt_loader: Optional IPromptLoader for blob-SHA resolution (PLAN-F-014 AC-004).
            When provided, get_sha(role_id) is used instead of git log. If the role has
            no prompt file (PromptNotFoundError / FileNotFoundError), prompt_version is
            set to "unknown" without failing the invocation.
    """

    def __init__(
        self,
        definition: AgentDefinition,
        langfuse_client: Any | None,
        workflow_id: str,
        tenant_id: str,
        prompt_loader: Any | None = None,
    ) -> None:
        self._definition = definition
        self._client = langfuse_client
        self._workflow_id = workflow_id
        self._tenant_id = tenant_id
        self._prompt_loader = prompt_loader
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

        prompt_version = _resolve_prompt_version(
            role_id=self._definition.role_id,
            system_prompt_file=self._definition.system_prompt_file,
            prompt_loader=self._prompt_loader,
        )

        # TASK-009 (AC-005): tag canary_cohort on spans where the serving SHA
        # matches the active canary label for this role.
        canary_cohort = self._check_canary_cohort(prompt_version)

        try:
            trace = self._client.trace(
                name=f"agent-invocation:{self._definition.role_id}",
                metadata={
                    "workflow_id": self._workflow_id,
                    "tenant_id": self._tenant_id,
                },
            )
            span_metadata: dict = {
                "agent_role_id": self._definition.role_id,
                "model_id": self._definition.model.model_id,
                "prompt_version": prompt_version,
                "workflow_id": self._workflow_id,
                "tenant_id": self._tenant_id,
            }
            if canary_cohort:
                span_metadata["canary_cohort"] = True

            span = trace.span(
                name=self._definition.role_id,
                metadata=span_metadata,
            )
            return _InvocationContext(span=span)
        except Exception:
            logger.exception(
                "Failed to open Langfuse span for agent=%s",
                self._definition.role_id,
            )
            return _InvocationContext(span=None)

    def _check_canary_cohort(self, prompt_version: str) -> bool:
        """Return True if the current prompt_version matches the active canary label.

        Requires a prompt_loader with get_active_version support (TASK-009, AC-005).
        Falls back to False if unavailable.
        """
        if self._prompt_loader is None or prompt_version in ("unknown", ""):
            return False
        try:
            label_service = getattr(self._prompt_loader, "_label_service", None)
            if label_service is None:
                return False
            import asyncio
            from src.ai.prompts.label_service import PromptLabel

            snake_role_id = _role_id_to_snake(self._definition.role_id)
            # Run async get_active_version in the current event loop or a new one
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # Cannot await in sync context with running loop; skip canary tagging
                    return False
                canary_sha = loop.run_until_complete(
                    label_service.get_active_version(snake_role_id, PromptLabel.canary)
                )
            except RuntimeError:
                return False
            return canary_sha == prompt_version
        except Exception:
            logger.debug("Canary cohort check failed — defaulting to False")
            return False
