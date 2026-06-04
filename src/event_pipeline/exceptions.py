"""
Pipeline exceptions for Mode A Reactive Pipeline.
"""
from __future__ import annotations


class PipelineError(Exception):
    """Base class for all pipeline errors."""


class StepTimeoutError(PipelineError):
    """Raised when a pipeline step exceeds its latency budget.

    Attributes:
        step_name: Name of the step that timed out.
        budget_ms: Allowed latency budget in milliseconds.
        actual_ms: Actual elapsed time in milliseconds.
    """

    def __init__(self, step_name: str, budget_ms: int, actual_ms: float) -> None:
        self.step_name = step_name
        self.budget_ms = budget_ms
        self.actual_ms = actual_ms
        super().__init__(
            f"Step '{step_name}' exceeded budget: {actual_ms:.1f} ms > {budget_ms} ms"
        )


class PipelineIngestionError(PipelineError):
    """Raised when event ingestion fails at the adapter level."""


class PipelineClassificationError(PipelineError):
    """Raised when event classification fails."""


class PipelineDispatchError(PipelineError):
    """Raised when alert dispatch fails."""
