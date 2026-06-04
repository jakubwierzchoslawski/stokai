"""
Step 1 — persist_raw_event.

Persists the raw inbound event to the geo_event staging row and stores the
generated event_id in the pipeline context. Also handles source-disabled logic
for Twitter/X when TWITTER_ENABLED=false.
"""
from __future__ import annotations

import time

from src.events.exceptions import SourceDisabledError
from src.events.models import PipelineContext
from src.storage.interfaces.i_geo_event_repository import IGeoEventRepository


async def persist_raw_event(
    ctx: PipelineContext,
    repo: IGeoEventRepository,
    twitter_enabled: bool = False,
) -> PipelineContext:
    """Persist the raw event and set ctx.event_id.

    Args:
        ctx: Current pipeline context.
        repo: Geo-event repository for DB writes.
        twitter_enabled: Whether the Twitter/X source is enabled. Defaults to False.

    Returns:
        Updated pipeline context with event_id populated.

    Raises:
        SourceDisabledError: When the event source is "twitter" and Twitter is disabled.
    """
    # Guard: reject Twitter events when the source is administratively disabled
    if ctx.raw_event.source_provider == "twitter" and not twitter_enabled:
        raise SourceDisabledError(
            "Twitter/X source is disabled (TWITTER_ENABLED=false). "
            "Event will not be processed."
        )

    t0 = time.monotonic()
    event_id = await repo.upsert_raw(ctx.raw_event)
    latency_ms = int((time.monotonic() - t0) * 1000)

    ctx.event_id = event_id
    ctx.step_latencies_ms["persist_raw_event"] = latency_ms
    return ctx
