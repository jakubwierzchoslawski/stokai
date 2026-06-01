"""Step 13: TRACE — close Langfuse trace and record generated_at timestamp.

Architecture enforcement:
  P-09 Full AI Lineage — trace must be closed on every pipeline run (success and failure).
  AC-001 — generated_at timestamps the completion of the pipeline.
  REQ-N-001 — latency_ms logged to enable SLA auditing.

Single Responsibility: trace lifecycle and timestamp recording only.
Dependency Inversion: repository and Langfuse client injected.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from src.event_pipeline.pipeline_state import PipelineState

logger = logging.getLogger(__name__)


class TraceStep:
    """Pipeline Step 13: TRACE.

    Closes the Langfuse trace opened at pipeline start, sets
    ``state.generated_at``, persists it to the DB, and emits a
    structured completion log line.

    Parameters
    ----------
    repo:
        Repository exposing ``set_generated_at(raw_event_id, generated_at) -> Awaitable``.
    langfuse_client:
        Langfuse trace object exposing ``finish()`` method.
    """

    step_name: str = "s13_trace"

    def __init__(self, repo: Any, langfuse_client: Any) -> None:
        self._repo = repo
        self._langfuse = langfuse_client

    async def execute(self, state: PipelineState) -> PipelineState:
        """Close the Langfuse trace and persist the completion timestamp."""
        generated_at = datetime.now(timezone.utc)

        # Persist generated_at to raw_events record
        await self._repo.set_generated_at(state.raw_event_id, generated_at)

        # Close Langfuse trace — P-09
        try:
            self._langfuse.finish()
        except Exception:  # noqa: BLE001
            logger.warning(
                "Step 13 (TRACE): Langfuse trace close failed — pipeline still completes"
            )

        # Compute latency for SLA auditing (REQ-N-001)
        detected_at = state.payload.detected_at
        latency_ms: int | None = None
        if detected_at is not None:
            delta = generated_at - detected_at.replace(tzinfo=timezone.utc) \
                if detected_at.tzinfo is None else generated_at - detected_at
            latency_ms = int(delta.total_seconds() * 1000)

        logger.info(
            "Step 13 (TRACE): pipeline completed",
            extra={
                "event_id": str(state.raw_event_id),
                "tenant_id": str(state.tenant_id),
                "latency_ms": latency_ms,
                "route": state.route.value if state.route else None,
                "confidence": state.confidence,
                "step_count": 13,
            },
        )

        return state.model_copy(update={"generated_at": generated_at})
