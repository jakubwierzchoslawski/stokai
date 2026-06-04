"""
LangfuseTracer — ILangfuseTracer implementation using the Langfuse Python SDK.

Design contract: observability failures (connection errors, flush failures)
must NEVER block the pipeline. All SDK errors are caught, logged as warnings,
and replaced with no-op sentinel values so callers can continue.
"""
from __future__ import annotations

import logging
import uuid

from langfuse import Langfuse

logger = logging.getLogger(__name__)

_NOOP_ID = "noop-langfuse-unavailable"


class LangfuseTracer:
    """Langfuse-backed tracer satisfying ILangfuseTracer.

    Args:
        secret_key: Langfuse secret key.
        public_key: Langfuse public key.
        host: Self-hosted Langfuse base URL.
    """

    def __init__(self, secret_key: str, public_key: str, host: str) -> None:
        try:
            self._lf = Langfuse(
                secret_key=secret_key,
                public_key=public_key,
                host=host,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Langfuse initialisation failed: %s", type(exc).__name__)
            self._lf = None

        # In-flight trace and span objects keyed by their IDs
        self._traces: dict[str, object] = {}
        self._spans: dict[str, object] = {}

    # ── ILangfuseTracer ───────────────────────────────────────────────────────

    def start_trace(self, name: str, metadata: dict) -> str:
        """Create a new root trace and return its ID."""
        if self._lf is None:
            return _NOOP_ID

        try:
            trace = self._lf.trace(name=name, metadata=metadata)
            trace_id = trace.id
            self._traces[trace_id] = trace
            return trace_id
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Langfuse start_trace failed (%s) — continuing without tracing",
                type(exc).__name__,
            )
            fallback_id = f"noop-{uuid.uuid4()}"
            return fallback_id

    def start_span(self, trace_id: str, name: str, input: dict) -> str:
        """Create a child generation span under *trace_id*."""
        trace = self._traces.get(trace_id)
        if trace is None or trace_id.startswith("noop"):
            return f"noop-span-{uuid.uuid4()}"

        try:
            span = trace.generation(name=name, input=input)
            span_id = span.id
            self._spans[span_id] = span
            return span_id
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Langfuse start_span failed (%s) — continuing without span",
                type(exc).__name__,
            )
            return f"noop-span-{uuid.uuid4()}"

    def end_span(
        self,
        span_id: str,
        output: dict,
        cost_usd: float,
        latency_ms: int,
    ) -> None:
        """Close the span, recording output and performance metrics."""
        if span_id.startswith("noop"):
            return

        span = self._spans.pop(span_id, None)
        if span is None:
            return

        try:
            span.end(
                output=output,
                usage={"total_cost": cost_usd},
                metadata={"latency_ms": latency_ms},
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Langfuse end_span failed (%s)", type(exc).__name__)

    def end_trace(self, trace_id: str, output: dict) -> None:
        """Flush and close the root trace."""
        if trace_id.startswith("noop"):
            return

        trace = self._traces.pop(trace_id, None)
        if trace is not None:
            try:
                trace.update(output=output)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Langfuse trace update failed (%s)", type(exc).__name__)

        if self._lf is not None:
            try:
                self._lf.flush()
            except Exception as exc:  # noqa: BLE001
                logger.warning("Langfuse flush failed (%s)", type(exc).__name__)
