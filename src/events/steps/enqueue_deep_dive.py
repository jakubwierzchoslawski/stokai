"""
Step 11 — enqueue_deep_dive.

Conditionally enqueues a Mode B Event Deep-Dive job when the event is
high-intensity or has a direct company exposure.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

from src.events.interfaces.i_workflow_queue import IWorkflowQueue
from src.events.models import PipelineContext

_DEEP_DIVE_DELAY_MINUTES = 2
_HIGH_INTENSITY_THRESHOLD = 4


async def enqueue_deep_dive(
    ctx: PipelineContext,
    workflow_queue: IWorkflowQueue,
) -> PipelineContext:
    """Enqueue Mode B deep-dive job for high-intensity or directly-exposed events.

    Enqueues when:
    - classification.intensity >= 4, OR
    - any ExposureCandidate has exposure_type == "direct"

    Args:
        ctx: Current pipeline context.
        workflow_queue: Queue for async workflow jobs.

    Returns:
        Updated context with deep_dive_enqueued flag.
    """
    assert ctx.event_id is not None, "event_id must be set before enqueue_deep_dive"

    t0 = time.monotonic()
    should_enqueue = False

    if ctx.classification and ctx.classification.intensity >= _HIGH_INTENSITY_THRESHOLD:
        should_enqueue = True
    elif any(e.exposure_type == "direct" for e in ctx.exposures):
        should_enqueue = True

    if should_enqueue:
        scheduled_for = datetime.now(tz=timezone.utc) + timedelta(
            minutes=_DEEP_DIVE_DELAY_MINUTES
        )
        workflow_queue.enqueue(
            workflow_type="event_deep_dive",
            inputs={"event_id": str(ctx.event_id)},
            priority="high",
            scheduled_for=scheduled_for,
        )
        ctx.deep_dive_enqueued = True

    latency_ms = int((time.monotonic() - t0) * 1000)
    ctx.step_latencies_ms["enqueue_deep_dive"] = latency_ms
    return ctx
