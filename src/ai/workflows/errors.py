"""
ai.workflows.errors — Workflow-level exception types.

All exceptions carry structured data via a to_dict() method that is safe to
serialize to JSON (no Python-only types, no secrets).
"""
from __future__ import annotations

from uuid import UUID


class WorkflowCostLimitError(Exception):
    """Raised by CostCeilingGuard when the per-run cost ceiling is reached.

    Attributes:
        accumulated  — the current cost_usd value that triggered the halt.
        ceiling      — the configured ceiling_usd that was exceeded.
        workflow_id  — the workflow whose run was terminated.
    """

    def __init__(self, accumulated: float, ceiling: float, workflow_id: UUID) -> None:
        super().__init__(
            f"Workflow {workflow_id} exceeded cost ceiling: "
            f"${accumulated:.4f} >= ${ceiling:.4f}"
        )
        self.accumulated = accumulated
        self.ceiling = ceiling
        self.workflow_id = workflow_id

    def to_dict(self) -> dict:
        """Return a JSON-serializable dictionary of the error details."""
        return {
            "error": "WorkflowCostLimitError",
            "workflow_id": str(self.workflow_id),
            "accumulated_usd": self.accumulated,
            "ceiling_usd": self.ceiling,
        }


class WorkflowTimeoutError(Exception):
    """Raised when the on-demand analysis exceeds its time budget.

    Attributes:
        workflow_id     — the workflow whose run timed out.
        elapsed_seconds — how long the run took before being interrupted.
    """

    def __init__(self, workflow_id: UUID, elapsed_seconds: float) -> None:
        super().__init__(
            f"Workflow {workflow_id} timed out after {elapsed_seconds:.1f}s"
        )
        self.workflow_id = workflow_id
        self.elapsed_seconds = elapsed_seconds

    def to_dict(self) -> dict:
        """Return a JSON-serializable dictionary of the error details."""
        return {
            "error": "WorkflowTimeoutError",
            "workflow_id": str(self.workflow_id),
            "elapsed_seconds": self.elapsed_seconds,
        }


class EvaluateQualityError(Exception):
    """Raised by evaluate_quality node when it cannot compute overall confidence."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"evaluate_quality failed: {reason}")
        self.reason = reason


class WorkflowRunNotFoundError(Exception):
    """Raised by WorkflowRunRepository when a workflow_run row does not exist.

    Used by save_timeout() to surface missing-row failures rather than
    silently swallowing them (PLAN-N-002 TASK-003).
    """

    def __init__(self, workflow_id: UUID) -> None:
        super().__init__(f"WorkflowRun not found: workflow_id={workflow_id}")
        self.workflow_id = workflow_id
