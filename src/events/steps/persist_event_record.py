"""
Step 5 — persist_event_record.

Persists the classified event and its exposure map to the database.
After a successful commit, enqueues the geo-modifier Celery task
(scoring.apply_geo_modifier) as a fire-and-forget operation.

PLAN-F-018 TASK-006: Added geo-modifier enqueue after DB transaction completes.
"""
from __future__ import annotations

import logging
import time

from src.events.models import PipelineContext
from src.storage.interfaces.i_event_exposure_repository import IEventExposureRepository
from src.storage.interfaces.i_geo_event_repository import IGeoEventRepository

logger = logging.getLogger(__name__)


async def persist_event_record(
    ctx: PipelineContext,
    geo_repo: IGeoEventRepository,
    exposure_repo: IEventExposureRepository,
) -> PipelineContext:
    """Persist classification data and exposure candidates.

    After both writes commit, enqueues scoring.apply_geo_modifier as fire-and-forget.
    A Celery broker failure does not roll back the DB writes — the enqueue is
    performed after the transaction block exits.

    Args:
        ctx: Current pipeline context (event_id, classification, exposures must be set).
        geo_repo: Repository for updating the geo_event row with classification fields.
        exposure_repo: Repository for bulk-inserting event_exposure rows.

    Returns:
        Updated context with geo_modifier_enqueued flag set.
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

    # Enqueue geo-modifier AFTER the transaction has committed (fire-and-forget).
    # This is placed outside the DB writes so a broker failure cannot roll back DB state.
    tenant_id = ctx.raw_event.tenant_id
    if tenant_id is not None:
        try:
            from src.scoring.geo_modifier_worker import apply_geo_modifier_delay

            apply_geo_modifier_delay(
                event_id=str(ctx.event_id),
                tenant_id=str(tenant_id),
            )
            ctx.geo_modifier_enqueued = True
            logger.debug(
                "persist_event_record: geo_modifier enqueued for event=%s tenant=%s",
                ctx.event_id,
                tenant_id,
            )
        except Exception as exc:
            # Non-fatal: log and continue. The reapply endpoint can re-trigger later.
            logger.warning(
                "persist_event_record: failed to enqueue geo_modifier for event=%s: %s",
                ctx.event_id,
                exc,
            )
    else:
        logger.debug(
            "persist_event_record: no tenant_id on event=%s — geo_modifier not enqueued.",
            ctx.event_id,
        )

    return ctx
