"""
Step 10 — dispatch_or_log_silent.

Dispatches an alert for each matched rule, or writes a silent-log entry if no
rules matched.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

from src.alerts.interfaces.i_alert_dispatcher import IAlertDispatcher
from src.events.models import PipelineContext
from src.storage.interfaces.i_alert_repository import IAlertRepository


async def dispatch_or_log_silent(
    ctx: PipelineContext,
    dispatcher: IAlertDispatcher,
    alert_repo: IAlertRepository,
) -> PipelineContext:
    """Dispatch alerts or log silence.

    Args:
        ctx: Current pipeline context (rule_match and alert_text must be set).
        dispatcher: Alert delivery implementation (SendGrid or no-op).
        alert_repo: Repository for persisting alert/silent-log records.

    Returns:
        Updated context with alert_dispatched or silent_logged flags set.
    """
    assert ctx.event_id is not None, "event_id must be set before dispatch_or_log_silent"

    t0 = time.monotonic()
    rule_matches = ctx.rule_match or []

    # Capture total pipeline cost at point of dispatch/log (AC-003).
    total_cost_usd: float | None = (
        ctx.cost_accumulator.total if ctx.cost_accumulator is not None else None
    )

    if rule_matches:
        for match in rule_matches:
            await dispatcher.dispatch(match, ctx.alert_text or "", ctx.event_id)
            await alert_repo.insert_alert(
                {
                    "tenant_id": match.tenant_id,
                    "event_id": ctx.event_id,
                    "company_id": None,
                    "rule_id": match.rule_id,
                    "channel": ",".join(match.channels),
                    "sent_at": datetime.now(tz=timezone.utc),
                    "content": ctx.alert_text or "",
                    "confidence": 1.0,
                },
                cost_usd=total_cost_usd,
            )
        ctx.alert_dispatched = True
    else:
        await dispatcher.log_silent(ctx.event_id, ctx.raw_event.tenant_id)
        await alert_repo.insert_silent_log(
            ctx.event_id,
            ctx.raw_event.tenant_id,
            cost_usd=total_cost_usd,
        )
        ctx.silent_logged = True

    latency_ms = int((time.monotonic() - t0) * 1000)
    ctx.step_latencies_ms["dispatch_or_log_silent"] = latency_ms
    return ctx
