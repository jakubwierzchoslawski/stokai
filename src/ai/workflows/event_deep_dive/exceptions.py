"""
ai.workflows.event_deep_dive.exceptions — workflow-specific exception types.

All exceptions carry structured metadata via to_dict() so they are safe to
serialize to JSON for logging and Celery error handling.

PLAN-F-010 TASK-003.
"""
from __future__ import annotations


class CostCeilingExceededError(Exception):
    """Raised by CostAccumulator when total_usd + new_amount >= ceiling_usd.

    Raised BEFORE the amount is added so the accumulator stays consistent.

    Attributes:
        cost_accumulated: The total accumulated before the failing add() call.
        ceiling_usd:      The configured cost ceiling that would have been exceeded.
    """

    def __init__(
        self,
        cost_accumulated: float,
        ceiling_usd: float,
        message: str | None = None,
    ) -> None:
        super().__init__(
            message
            or (
                f"Cost ceiling of ${ceiling_usd:.4f} would be exceeded; "
                f"accumulated=${cost_accumulated:.4f}"
            )
        )
        self.cost_accumulated = cost_accumulated
        self.ceiling_usd = ceiling_usd

    def to_dict(self) -> dict:
        """Return a JSON-serializable dict of the error details."""
        return {
            "error": "CostCeilingExceededError",
            "cost_accumulated": self.cost_accumulated,
            "ceiling_usd": self.ceiling_usd,
        }


class WorkflowTimeoutError(Exception):
    """Raised by WorkflowTimeoutGuard when hard_limit_seconds is exceeded.

    Attributes:
        elapsed_seconds: Wall-clock time elapsed before the timeout fired.
    """

    def __init__(self, elapsed_seconds: float) -> None:
        super().__init__(
            f"Event deep-dive workflow timed out after {elapsed_seconds:.2f}s"
        )
        self.elapsed_seconds = elapsed_seconds

    def to_dict(self) -> dict:
        """Return a JSON-serializable dict of the error details."""
        return {
            "error": "WorkflowTimeoutError",
            "elapsed_seconds": self.elapsed_seconds,
        }


class WorkflowInputError(Exception):
    """Raised by deterministic nodes when required input data is missing or invalid.

    Example: event_id not found in the database.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
