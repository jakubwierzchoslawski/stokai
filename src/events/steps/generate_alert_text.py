"""
Step 8 — generate_alert_text.

Calls Claude Sonnet 4.6 to generate an ~80-word market alert text based on
classification, historical analogies, and exposed companies.
"""
from __future__ import annotations

import os
import time

from src.ai.interfaces.i_langfuse_tracer import ILangfuseTracer
from src.ai.interfaces.i_llm_client import ILLMClient
from src.events.models import PipelineContext

_MODEL = "claude-sonnet-4-6"
_COST_CEILING_USD = 0.05

_PROMPT_PATH = os.path.join(
    os.path.dirname(__file__),
    "..",
    "..",
    "..",
    "prompts",
    "classifiers",
    "alert_text_generator.md",
)


def _load_system_prompt() -> str:
    with open(_PROMPT_PATH, encoding="utf-8") as fh:
        return fh.read()


def _build_user_message(ctx: PipelineContext) -> str:
    cls = ctx.classification
    payload = ctx.raw_event.raw_payload
    title = payload.get("title", "")
    summary = payload.get("summary", "")

    parts = [
        f"Event: {title}",
        f"Summary: {summary}",
        f"Categories: {', '.join(cls.category) if cls else 'unknown'}",
        f"Intensity: {cls.intensity if cls else 'unknown'}/5",
        f"Sentiment: {cls.sentiment if cls else 'unknown'}",
        f"Regions: {', '.join(cls.geo_regions) if cls else 'unknown'}",
        f"Sectors: {', '.join(cls.affected_sectors) if cls else 'unknown'}",
    ]

    if ctx.analogies:
        top_analogies = ctx.analogies[:3]
        analogy_lines = [
            f"  - {a['title']} ({a['occurred_at'].year if hasattr(a['occurred_at'], 'year') else a['occurred_at']})"
            for a in top_analogies
        ]
        parts.append("Historical analogies:\n" + "\n".join(analogy_lines))

    if ctx.tickers:
        parts.append(f"Exposed tickers: {', '.join(ctx.tickers[:5])}")

    return "\n".join(parts)


async def generate_alert_text(
    ctx: PipelineContext,
    llm: ILLMClient,
    tracer: ILangfuseTracer,
) -> PipelineContext:
    """Generate an ~80-word alert using Claude Sonnet 4.6.

    Args:
        ctx: Current pipeline context.
        llm: LLM client configured for claude-sonnet-4-6.
        tracer: Langfuse tracer.

    Returns:
        Updated context with alert_text populated.

    Raises:
        StepTimeoutError: When LLM call exceeds 8 seconds.
        PipelineError: On API errors.
    """
    system_prompt = _load_system_prompt()
    user_message = _build_user_message(ctx)

    span_id = tracer.start_span(
        ctx.langfuse_trace_id or "",
        "generate_alert_text",
        {"model": "claude-sonnet-4-6", "has_analogies": bool(ctx.analogies)},
    )

    t0 = time.monotonic()
    content, input_tokens, output_tokens = await llm.complete(
        system_prompt=system_prompt,
        user_message=user_message,
        max_tokens=200,
        timeout_seconds=8.0,
    )
    latency_ms = int((time.monotonic() - t0) * 1000)

    cost_usd = ctx.cost_accumulator.add_from_tokens(_MODEL, input_tokens, output_tokens)
    ctx.cost_accumulator.check_ceiling(_COST_CEILING_USD)

    tracer.end_span(
        span_id,
        {"alert_text_length": len(content), "cost_usd": cost_usd},
        cost_usd=cost_usd,
        latency_ms=latency_ms,
    )
    ctx.alert_text = content
    ctx.step_latencies_ms["generate_alert_text"] = latency_ms
    return ctx
