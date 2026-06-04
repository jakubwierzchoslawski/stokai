"""
Step 5 — persist_event_record.

Persists the classified event and its exposure map to the database.
"""
from __future__ import annotations

import time

from src.events.models import PipelineContext
from src.storage.interfaces.i_event_exposure_repository import IEventExposureRepository
from src.storage.interfaces.i_geo_event_repository import IGeoEventRepository


async def persist_event_record(
    ctx: PipelineContext,
    geo_repo: IGeoEventRepository,
    exposure_repo: IEventExposureRepository,
) -> PipelineContext:
    """Persist classification data and exposure candidates.

    Args:
        ctx: Current pipeline context (event_id, classification, exposures must be set).
        geo_repo: Repository for updating the geo_event row with classification fields.
        exposure_repo: Repository for bulk-inserting event_exposure rows.

    Returns:
        Updated context (unchanged apart from step latency tracking).
    """
    assert ctx.event_id is not None, "event_id must be set before persist_event_record"
    assert ctx.classification is not None, "classification must be set before persist_event_record"

    payload = ctx.raw_event.raw_payload
    title = payload.get("title", "")
    summary = payload.get("summary", "")
    lat = payload.get("lat")
    lon = payload.get("lon")

    t0 = time.monotonic()

    await geo_repo.persist_classified(
        event_id=ctx.event_id,
        classification=ctx.classification,
        title=title,
        summary=summary,
        lat=float(lat) if lat is not None else None,
        lon=float(lon) if lon is not None else None,
        source_provider=ctx.raw_event.source_provider,
        tenant_id=ctx.raw_event.tenant_id,
    )

    await exposure_repo.bulk_insert(ctx.event_id, ctx.exposures)

    latency_ms = int((time.monotonic() - t0) * 1000)
    ctx.step_latencies_ms["persist_event_record"] = latency_ms
    return ctx
