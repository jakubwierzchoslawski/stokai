"""
Step 12 — return_pipeline_result.

Constructs the final PipelineResult, flushes the Langfuse trace, and writes
the episodic memory entry to workflow_run.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.interfaces.i_langfuse_tracer import ILangfuseTracer
from src.events.models import PipelineContext, PipelineResult

logger = logging.getLogger(__name__)


async def return_pipeline_result(
    ctx: PipelineContext,
    tracer: ILangfuseTracer,
    db_session: AsyncSession | None = None,
) -> PipelineResult:
    """Build the final PipelineResult and flush observability data.

    Args:
        ctx: Fully-populated pipeline context.
        tracer: Langfuse tracer to flush.
        db_session: Optional async session for writing the workflow_run record.

    Returns:
        Completed PipelineResult.
    """
    assert ctx.event_id is not None, "event_id must be set by return_pipeline_result"

    total_cost = ctx.cost_accumulator.total if ctx.cost_accumulator else 0.0
    trace_id = ctx.langfuse_trace_id or "noop"

    result = PipelineResult(
        event_id=ctx.event_id,
        alert_dispatched=ctx.alert_dispatched,
        silent_logged=ctx.silent_logged,
        deep_dive_enqueued=ctx.deep_dive_enqueued,
        total_cost_usd=total_cost,
        step_latencies_ms=ctx.step_latencies_ms,
        langfuse_trace_id=trace_id,
    )

    # Flush Langfuse trace — never raise even if tracing is broken
    try:
        tracer.end_trace(
            trace_id,
            {
                "event_id": str(ctx.event_id),
                "alert_dispatched": ctx.alert_dispatched,
                "total_cost_usd": total_cost,
            },
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Langfuse end_trace failed: %s", type(exc).__name__)

    # Write episodic memory to workflow_run table
    if db_session is not None:
        try:
            stmt = text(
                """
                INSERT INTO workflow_run (
                    workflow_type, tenant_id, started_at, completed_at,
                    status, cost_usd, langfuse_trace_id
                ) VALUES (
                    'mode_a_pipeline',
                    :tenant_id,
                    NOW(),
                    NOW(),
                    'complete',
                    :cost_usd,
                    :langfuse_trace_id
                )
                ON CONFLICT DO NOTHING
                """
            )
            await db_session.execute(
                stmt,
                {
                    "tenant_id": ctx.raw_event.tenant_id,
                    "cost_usd": total_cost,
                    "langfuse_trace_id": trace_id,
                },
            )
            await db_session.flush()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Failed to write workflow_run record: %s", type(exc).__name__
            )

    return result
