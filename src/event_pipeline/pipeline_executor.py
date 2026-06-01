"""PipelineExecutor — sequential 13-step runner for the Mode A pipeline.

Architecture enforcement:
  P-09 Full AI Lineage — per-step Langfuse span lifecycle.
  AC-005 — any step failure marks the event failed and prevents dispatch.
  AC-001 — steps execute in the injected order; no step is skipped on success.

Single Responsibility: orchestrates step execution order, error trapping, and
  status persistence.  Does not implement business logic.

Dependency Inversion: ``PipelineStep`` protocol instances and the raw event
  repository are injected; this class never instantiates collaborators.
"""
from __future__ import annotations

import logging
from typing import Any

from src.event_pipeline.exceptions import DuplicateEvent, PipelineHalt
from src.event_pipeline.pipeline_state import PipelineState
from src.event_pipeline.steps.base import PipelineStep

logger = logging.getLogger(__name__)


class PipelineExecutor:
    """Runs an ordered list of ``PipelineStep`` instances sequentially.

    Parameters
    ----------
    steps:
        Ordered list of all 13 pipeline steps to execute.
    langfuse_client:
        Langfuse tracing client opened at pipeline start (Step 13 closes it).
    raw_event_repo:
        Repository for updating ``raw_events.pipeline_status`` on halt or
        completion.  Must expose ``update_status(raw_event_id, status, *,
        failed_step=None, error_detail=None)`` as an awaitable.
    """

    def __init__(
        self,
        steps: list[PipelineStep],
        langfuse_client: Any,
        raw_event_repo: Any,
    ) -> None:
        self._steps = steps
        self._langfuse = langfuse_client
        self._repo = raw_event_repo

    async def run(self, state: PipelineState) -> PipelineState:
        """Execute all steps in order.

        On success, returns the final ``PipelineState``.

        On any failure:
          1. Wraps non-``PipelineHalt`` exceptions in ``PipelineHalt``.
          2. Sets ``state.failed_step`` and ``state.error_detail``.
          3. Calls ``raw_event_repo.update_status`` with the appropriate status.
          4. Re-raises ``PipelineHalt`` so the Celery task can mark itself FAILURE.

        ``DuplicateEvent`` → status ``"duplicate"``.
        Any other ``PipelineHalt`` → status ``"failed"``.

        Raises
        ------
        PipelineHalt
            Always re-raised after the halt handler completes.
        """
        for step in self._steps:
            try:
                state = await step.execute(state)
                state = state.model_copy(update={"current_step": step.step_name})
            except PipelineHalt as exc:
                await self._handle_halt(state, exc)
                raise
            except Exception as exc:  # noqa: BLE001
                wrapped = PipelineHalt(
                    step_name=step.step_name,
                    detail=str(exc),
                )
                await self._handle_halt(state, wrapped)
                raise wrapped from exc

        return state

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _handle_halt(
        self, state: PipelineState, exc: PipelineHalt
    ) -> None:
        """Persist failure status and emit a structured error log."""
        status = "duplicate" if isinstance(exc, DuplicateEvent) else "failed"

        logger.error(
            "Pipeline halted",
            extra={
                "event_id": str(state.raw_event_id),
                "tenant_id": str(state.tenant_id),
                "failed_step": exc.step_name,
                "error_detail": exc.detail,
                "status": status,
            },
        )

        await self._repo.update_status(
            state.raw_event_id,
            status=status,
            failed_step=exc.step_name,
            error_detail=exc.detail,
        )
