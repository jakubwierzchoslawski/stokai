"""
ai.workflows.timeout_guard — Shared timeout configuration and soft-timeout guard.

Defines:
  WorkflowTimeoutConfig  — frozen dataclass per workflow type
  WORKFLOW_TIMEOUT_CONFIGS — registry mapping WorkflowType → config
  WorkflowSoftTimeoutGuard — async context manager that intercepts
      Celery SoftTimeLimitExceeded, persists partial state, writes
      Langfuse score, and exits cleanly so the task succeeds.

PLAN-N-002
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any
from uuid import UUID

from src.ai.workflows.state import WorkflowState, WorkflowStatus, WorkflowType

if TYPE_CHECKING:
    from src.storage.repositories.interfaces import IWorkflowRunRepository

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# WorkflowTimeoutConfig
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WorkflowTimeoutConfig:
    """Immutable per-workflow latency budget.

    Attributes:
        workflow_type:      The workflow this config applies to.
        hard_limit_seconds: Celery time_limit (SIGKILL boundary).
        soft_limit_seconds: Celery soft_time_limit (SoftTimeLimitExceeded).
        target_seconds_p95: Operational p95 target; used for monitoring.
    """

    workflow_type: WorkflowType
    hard_limit_seconds: int
    soft_limit_seconds: int
    target_seconds_p95: int


# ---------------------------------------------------------------------------
# WORKFLOW_TIMEOUT_CONFIGS registry
# ---------------------------------------------------------------------------

WORKFLOW_TIMEOUT_CONFIGS: dict[WorkflowType, WorkflowTimeoutConfig] = {
    WorkflowType.MORNING_BRIEF: WorkflowTimeoutConfig(
        workflow_type=WorkflowType.MORNING_BRIEF,
        hard_limit_seconds=600,
        soft_limit_seconds=570,
        target_seconds_p95=300,
    ),
    WorkflowType.ON_DEMAND: WorkflowTimeoutConfig(
        workflow_type=WorkflowType.ON_DEMAND,
        hard_limit_seconds=360,
        soft_limit_seconds=330,
        target_seconds_p95=240,
    ),
    WorkflowType.WATCHLIST_SCAN: WorkflowTimeoutConfig(
        workflow_type=WorkflowType.WATCHLIST_SCAN,
        hard_limit_seconds=480,
        soft_limit_seconds=450,
        target_seconds_p95=180,
    ),
    WorkflowType.EARNINGS_BRIEF: WorkflowTimeoutConfig(
        workflow_type=WorkflowType.EARNINGS_BRIEF,
        hard_limit_seconds=600,
        soft_limit_seconds=570,
        target_seconds_p95=240,
    ),
    WorkflowType.EVENT_DEEP_DIVE: WorkflowTimeoutConfig(
        workflow_type=WorkflowType.EVENT_DEEP_DIVE,
        hard_limit_seconds=900,
        soft_limit_seconds=870,
        target_seconds_p95=420,
    ),
}


# ---------------------------------------------------------------------------
# WorkflowSoftTimeoutGuard
# ---------------------------------------------------------------------------


class WorkflowSoftTimeoutGuard:
    """Async context manager that handles Celery SoftTimeLimitExceeded.

    On SoftTimeLimitExceeded:
      1. Sets state.status = TIMEOUT
      2. Sets state.partial_result = True
      3. Sets state.timeout_at = utcnow()
      4. Calls repository.save_timeout(workflow_id, state, timeout_at)
      5. Writes Langfuse score "workflow_timeout" = 1 on the active trace
      6. Writes duration_ms to the Langfuse trace
      7. Logs structured ERROR entry
      8. Returns True (suppresses the exception) so the Celery task exits
         as SUCCESS rather than FAILURE.

    On any other exception: the exception propagates; save_timeout is NOT called.

    On clean exit: no-op; state is unchanged.
    """

    def __init__(
        self,
        state: WorkflowState,
        repository: IWorkflowRunRepository,
        langfuse_client: Any | None = None,
    ) -> None:
        self._state = state
        self._repository = repository
        self._langfuse_client = langfuse_client
        # Mutable reference — updated during _handle_soft_timeout
        self._final_state: WorkflowState = state

    async def __aenter__(self) -> "WorkflowSoftTimeoutGuard":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> bool:
        """Handle exit from the managed block.

        Returns:
            True  — suppress SoftTimeLimitExceeded
            False — propagate all other exceptions
        """
        if exc_type is None:
            # Clean exit — nothing to do
            return False

        # Lazy import to allow tests without celery installed
        try:
            from celery.exceptions import SoftTimeLimitExceeded as _SLTE
        except ImportError:
            _SLTE = None  # type: ignore[assignment,misc]

        # Check if this is SoftTimeLimitExceeded (by type identity or by name
        # to support test doubles that subclass a local stub).
        is_soft_timeout = (
            (_SLTE is not None and issubclass(exc_type, _SLTE))
            or exc_type.__name__ == "SoftTimeLimitExceeded"
        )

        if is_soft_timeout:
            await self._handle_soft_timeout()
            return True  # suppress exception

        return False  # propagate other exceptions

    async def _handle_soft_timeout(self) -> None:
        """Flush partial state and record the timeout event."""
        timeout_at = datetime.now(tz=timezone.utc)

        # Mutate a copy of state (WorkflowState is a Pydantic BaseModel)
        timed_out_state = self._state.model_copy(
            update={
                "status": WorkflowStatus.TIMEOUT,
                "partial_result": True,
                "timeout_at": timeout_at,
            }
        )
        self._final_state = timed_out_state

        elapsed_seconds = (timeout_at - self._state.started_at).total_seconds()
        workflow_id = self._state.workflow_id

        # 1. Persist partial state to DB
        try:
            await self._repository.save_timeout(
                workflow_id=workflow_id,
                partial_state=timed_out_state,
                timeout_at=timeout_at,
            )
        except Exception:
            logger.exception(
                "WorkflowSoftTimeoutGuard: failed to save timeout state for "
                "workflow_id=%s",
                workflow_id,
            )

        # 2. Write Langfuse score and duration — wrapped so Langfuse outage never
        #    prevents the partial state from being saved.
        if self._langfuse_client is not None:
            try:
                duration_ms = elapsed_seconds * 1000
                trace_id = self._state.langfuse_trace_id
                if trace_id:
                    self._langfuse_client.score(
                        trace_id=trace_id,
                        name=f"{self._state.workflow_type.value}_duration_ms",
                        value=duration_ms,
                    )
                    self._langfuse_client.score(
                        trace_id=trace_id,
                        name="workflow_timeout",
                        value=1,
                    )
            except Exception:
                logger.warning(
                    "WorkflowSoftTimeoutGuard: Langfuse write failed for "
                    "workflow_id=%s (continuing)",
                    workflow_id,
                )

        # 3. Structured error log
        logger.error(
            "WorkflowSoftTimeoutGuard: soft timeout reached",
            extra={
                "workflow_id": str(workflow_id),
                "workflow_type": self._state.workflow_type.value,
                "elapsed_seconds": elapsed_seconds,
                "cost_usd": self._state.cost_usd,
                "partial_result": True,
            },
        )
