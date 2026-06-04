"""
Pipeline-level exception hierarchy.

All exceptions are intentionally broad so callers only need to catch
PipelineError to handle the full failure surface of the executor.
"""


class PipelineError(Exception):
    """Base class for all pipeline failures."""


class CostCeilingExceededError(PipelineError):
    """Raised when the per-event cost accumulator exceeds the configured ceiling.

    Attributes:
        accumulated_usd: The total cost at the time the ceiling was breached.
        ceiling_usd: The ceiling value that was exceeded.
    """

    def __init__(self, message: str, accumulated_usd: float, ceiling_usd: float) -> None:
        super().__init__(message)
        self.accumulated_usd = accumulated_usd
        self.ceiling_usd = ceiling_usd


class StepTimeoutError(PipelineError):
    """Raised when an individual pipeline step exceeds its time budget."""


class SourceDisabledError(PipelineError):
    """Raised when an event arrives from a source that is administratively disabled."""
