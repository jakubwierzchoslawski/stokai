"""
IWorkflowQueue — protocol for enqueuing async workflow jobs.
"""
from __future__ import annotations

from datetime import datetime

from typing_extensions import Protocol, runtime_checkable


@runtime_checkable
class IWorkflowQueue(Protocol):
    """Interface for enqueuing workflow jobs (e.g. Celery tasks).

    Implementations must be non-blocking — the actual job runs asynchronously.
    """

    def enqueue(
        self,
        workflow_type: str,
        inputs: dict,
        priority: str,
        scheduled_for: datetime,
    ) -> None:
        """Enqueue a workflow job.

        Args:
            workflow_type: Identifier of the workflow to run (e.g. "event_deep_dive").
            inputs: Serialisable dict of job inputs.
            priority: Job priority hint: "high" | "normal" | "low".
            scheduled_for: When the job should become eligible for pickup.
        """
        ...
