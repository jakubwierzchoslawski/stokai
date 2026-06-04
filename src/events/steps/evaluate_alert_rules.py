"""
Step 9 — evaluate_alert_rules.

Evaluates active alert rules against the classified event and stores matching
rules in the pipeline context.
"""
from __future__ import annotations

import time

from src.alerts.interfaces.i_alert_rule_evaluator import IAlertRuleEvaluator
from src.events.models import PipelineContext


async def evaluate_alert_rules(
    ctx: PipelineContext,
    evaluator: IAlertRuleEvaluator,
) -> PipelineContext:
    """Evaluate alert rules and store matches in ctx.rule_match.

    Args:
        ctx: Current pipeline context (event_id, classification, exposures must be set).
        evaluator: Alert rule evaluator with anti-fatigue logic.

    Returns:
        Updated context with rule_match populated (empty list if no matches).
    """
    assert ctx.event_id is not None, "event_id must be set before evaluate_alert_rules"
    assert ctx.classification is not None, "classification must be set before evaluate_alert_rules"

    t0 = time.monotonic()
    matches = await evaluator.evaluate(
        event_id=ctx.event_id,
        classification=ctx.classification,
        exposures=ctx.exposures,
        tenant_id=ctx.raw_event.tenant_id,
    )
    latency_ms = int((time.monotonic() - t0) * 1000)

    ctx.rule_match = matches
    ctx.step_latencies_ms["evaluate_alert_rules"] = latency_ms
    return ctx
