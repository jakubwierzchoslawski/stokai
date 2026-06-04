"""
NodeExecutor — wraps every AgentNode.execute() call in Langfuse span brackets.

Architecture §7.1: Langfuse spans must be wired into workflow node execution.

Responsibilities:
- Open an agent span (via ILangfuseTracer) before invoking the agent.
- Resolve the prompt SHA via PromptVersionResolver.
- Extract output metadata (tokens_in, tokens_out, cost_usd, confidence) from
  the agent output.
- Close the agent span with output metadata (always — even on exception).
- After the Langfuse span is closed, write an agent_invocation row to
  PostgreSQL via EpisodicRepository (authoritative dual-write, PLAN-F-015).

Dual-write ordering (per PLAN-N-008 TASK-005):
- Langfuse close is wrapped in try/except so Langfuse outages do not abort
  the workflow.  The span is always attempted even on agent failure.
- EpisodicRepository write is authoritative: failure propagates.

Tool-call path:
- execute_tool_call_async opens a tool span, closes it, then writes
  a tool_call row to PostgreSQL via EpisodicRepository.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Protocol, runtime_checkable
from uuid import UUID

from src.ai.observability.exceptions import SpanNotOpenError
from src.ai.observability.span_metadata import SpanMetadata
from src.ai.observability.tracer import ILangfuseTracer

logger = logging.getLogger(__name__)


# ── Agent and output protocols ───────────────────────────────────────────────


@runtime_checkable
class AgentOutput(Protocol):
    """Minimal interface for the object returned by AgentNode.invoke()."""

    tokens_in: int
    tokens_out: int
    cost_usd: float
    confidence: float


@runtime_checkable
class AgentConfig(Protocol):
    """Minimal interface for the YAML agent configuration loaded by AgentRegistry."""

    agent_role_id: str
    model: str
    prompt_path: str


@runtime_checkable
class AgentNode(Protocol):
    """Minimal interface for an agent node that can be invoked."""

    config: AgentConfig

    def invoke(self, state: Any) -> AgentOutput:
        """Execute the agent and return structured output."""
        ...


# ── NodeExecutor ─────────────────────────────────────────────────────────────


class NodeExecutor:
    """Wraps AgentNode execution with Langfuse span open/close brackets.

    Parameters
    ----------
    tracer:
        ILangfuseTracer implementation (injected, never imported directly).
    prompt_resolver:
        PromptVersionResolver instance for SHA resolution.
    episodic_repo:
        Optional EpisodicRepository; when provided, writes agent_invocation and
        tool_call rows after span close.
    """

    def __init__(
        self,
        tracer: ILangfuseTracer,
        prompt_resolver: Any,
        episodic_repo: Any | None = None,
    ) -> None:
        self._tracer = tracer
        self._prompt_resolver = prompt_resolver
        self._episodic_repo = episodic_repo

    # ── Agent node execution ─────────────────────────────────────────────────

    def execute_agent_node(
        self,
        state: Any,
        agent: AgentNode,
        parent_span_id: str | None = None,
    ) -> AgentOutput:
        """Execute agent with full Langfuse span instrumentation (sync).

        Uses try/finally to guarantee the Langfuse span is closed even on
        exception.  The Langfuse close is wrapped in try/except so Langfuse
        outages don't propagate.

        Note: DB dual-write (episodic_repo) is NOT performed in the sync
        variant because it requires await.  Use execute_agent_node_async for
        the authoritative dual-write path.
        """
        trace_id: str = state.trace_id or ""
        config: AgentConfig = agent.config
        prompt_version = self._prompt_resolver.resolve(config.prompt_path)

        open_metadata = self._build_open_metadata(state, config, prompt_version)
        span_id = self._tracer.open_agent_span(trace_id, parent_span_id, open_metadata)
        start_ts = time.monotonic()

        output: AgentOutput | None = None
        exc_to_raise: BaseException | None = None

        try:
            output = agent.invoke(state)
        except BaseException as exc:
            exc_to_raise = exc
        finally:
            elapsed_ms = int((time.monotonic() - start_ts) * 1000)
            close_metadata = self._build_close_metadata(
                state, config, prompt_version, output, elapsed_ms
            )
            self._close_span_best_effort(span_id, close_metadata)

        if exc_to_raise is not None:
            raise exc_to_raise

        return output  # type: ignore[return-value]

    async def execute_agent_node_async(
        self,
        state: Any,
        agent: AgentNode,
        parent_span_id: str | None = None,
    ) -> AgentOutput:
        """Async variant with authoritative PostgreSQL dual-write.

        1. Open Langfuse agent span.
        2. Invoke agent (sync).
        3. Close Langfuse span (best-effort, Langfuse outage does not abort).
        4. Write agent_invocation row to PostgreSQL (authoritative — raises on failure).
        """
        trace_id: str = state.trace_id or ""
        config: AgentConfig = agent.config
        prompt_version = self._prompt_resolver.resolve(config.prompt_path)

        open_metadata = self._build_open_metadata(state, config, prompt_version)
        span_id = self._tracer.open_agent_span(trace_id, parent_span_id, open_metadata)
        start_ts = time.monotonic()

        output: AgentOutput | None = None
        exc_to_raise: BaseException | None = None

        try:
            output = agent.invoke(state)
        except BaseException as exc:
            exc_to_raise = exc
        finally:
            elapsed_ms = int((time.monotonic() - start_ts) * 1000)
            close_metadata = self._build_close_metadata(
                state, config, prompt_version, output, elapsed_ms
            )
            # Langfuse close is best-effort
            self._close_span_best_effort(span_id, close_metadata)

        if exc_to_raise is not None:
            raise exc_to_raise

        # Authoritative DB write — runs after Langfuse span is closed
        if self._episodic_repo is not None and output is not None:
            await self._episodic_repo.append_agent_invocation(
                workflow_run_id=state.workflow_id,
                agent_role=config.agent_role_id,
                prompt_version=prompt_version,
                cost_usd=output.cost_usd,
            )

        return output  # type: ignore[return-value]

    # ── Tool call execution ──────────────────────────────────────────────────

    async def execute_tool_call_async(
        self,
        state: Any,
        invocation_id: UUID,
        tool_name: str,
        parent_span_id: str | None,
        args_hash: str,
        cached: bool,
        result_rows: int,
        latency_ms: int,
        error_type: str | None,
    ) -> None:
        """Open/close a Langfuse tool span and write a tool_call row to PostgreSQL.

        Langfuse close is best-effort.  DB write is authoritative.
        """
        trace_id: str = state.trace_id or ""

        span_id = self._tracer.open_tool_span(
            trace_id=trace_id,
            parent_span_id=parent_span_id,
            tool_name=tool_name,
            args_hash=args_hash,
            cached=cached,
        )

        # Close Langfuse tool span (best-effort)
        try:
            self._tracer.close_tool_span(
                span_id=span_id,
                result_rows=result_rows,
                latency_ms=latency_ms,
                error_type=error_type,
            )
        except Exception as langfuse_err:
            logger.error(
                "Langfuse close_tool_span failed for span=%s: %s",
                span_id,
                langfuse_err,
                exc_info=True,
            )

        # Authoritative DB write
        if self._episodic_repo is not None:
            await self._episodic_repo.append_tool_call(
                invocation_id=invocation_id,
                tool_name=tool_name,
            )

    # ── Private helpers ──────────────────────────────────────────────────────

    def _build_open_metadata(
        self, state: Any, config: AgentConfig, prompt_version: str
    ) -> SpanMetadata:
        return SpanMetadata(
            workflow_id=state.workflow_id,
            workflow_type=state.workflow_type,
            tenant_id=state.tenant_id,
            user_id=state.user_id,
            agent_role_id=config.agent_role_id,
            prompt_version=prompt_version,
            model_used=config.model,
            confidence=None,
            cost_usd=None,
            tokens_in=None,
            tokens_out=None,
            latency_ms=None,
            tools_called=None,
            state_snapshot_ref=None,
        )

    def _build_close_metadata(
        self,
        state: Any,
        config: AgentConfig,
        prompt_version: str,
        output: AgentOutput | None,
        elapsed_ms: int,
    ) -> SpanMetadata:
        if output is not None:
            return SpanMetadata(
                workflow_id=state.workflow_id,
                workflow_type=state.workflow_type,
                tenant_id=state.tenant_id,
                user_id=state.user_id,
                agent_role_id=config.agent_role_id,
                prompt_version=prompt_version,
                model_used=config.model,
                confidence=output.confidence,
                cost_usd=output.cost_usd,
                tokens_in=output.tokens_in,
                tokens_out=output.tokens_out,
                latency_ms=elapsed_ms,
                tools_called=None,
                state_snapshot_ref=None,
            )
        # Exception path — all optional fields are None
        return SpanMetadata(
            workflow_id=state.workflow_id,
            workflow_type=state.workflow_type,
            tenant_id=state.tenant_id,
            user_id=state.user_id,
            agent_role_id=config.agent_role_id,
            prompt_version=prompt_version,
            model_used=config.model,
            confidence=None,
            cost_usd=None,
            tokens_in=None,
            tokens_out=None,
            latency_ms=elapsed_ms,
            tools_called=None,
            state_snapshot_ref=None,
        )

    def _close_span_best_effort(self, span_id: str, metadata: SpanMetadata) -> None:
        """Close Langfuse agent span; log errors instead of propagating."""
        try:
            self._tracer.close_agent_span(span_id, metadata)
        except SpanNotOpenError:
            raise
        except Exception as langfuse_err:
            logger.error(
                "Langfuse close_agent_span failed for span=%s: %s",
                span_id,
                langfuse_err,
                exc_info=True,
            )
