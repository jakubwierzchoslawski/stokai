"""
Step 3 — extract_tickers.

Calls Claude Haiku 4.5 to extract affected NYSE/NASDAQ ticker symbols from the event text.
Prompt is loaded from a versioned Markdown file; SHA-256 of the file bytes is recorded
on the Langfuse span as `prompt_version`.

All LLM calls are traced via Langfuse.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

from pydantic import ValidationError

from src.ai.interfaces.i_langfuse_tracer import ILangfuseTracer
from src.ai.interfaces.i_llm_client import ILLMClient
from src.events.exceptions import PipelineError
from src.events.models import PipelineContext, TickerExtractionResult

_MODEL = "claude-haiku-4-5"
_MAX_OUTPUT_TOKENS = 100
_TIMEOUT_SECONDS = 3.0
_COST_CEILING_USD = 0.05

_DEFAULT_PROMPT_PATH = Path("prompts/classifiers/ticker_extractor.md")


def _load_prompt(prompt_path: Path) -> tuple[str, str]:
    """Load prompt content and compute its SHA-256.

    Returns:
        Tuple of (prompt_content, hex_sha256).
    """
    raw_bytes = prompt_path.read_bytes()
    sha = hashlib.sha256(raw_bytes).hexdigest()
    content = raw_bytes.decode("utf-8")
    return content, sha


async def extract_tickers(
    ctx: PipelineContext,
    llm: ILLMClient,
    tracer: ILangfuseTracer,
    prompt_path: Path = _DEFAULT_PROMPT_PATH,
) -> PipelineContext:
    """Extract NYSE/NASDAQ ticker symbols using Claude Haiku 4.5 (step 3 of Mode A pipeline).

    An empty tickers list is a valid, non-error result when no companies are mentioned.

    Args:
        ctx: Current pipeline context (classification should be populated).
        llm: LLM client configured for claude-haiku-4-5.
        tracer: Langfuse tracer for observability.
        prompt_path: Path to the versioned prompt Markdown file.

    Returns:
        Updated context with ``ctx.tickers`` populated (may be an empty list).

    Raises:
        PipelineError: On malformed LLM response or schema validation failure.
        StepTimeoutError: When the LLM call exceeds 3 seconds.
        CostCeilingExceededError: When accumulated cost exceeds $0.05 per event.
    """
    # --- 1. Extract event text ---
    event_text: str = ctx.raw_event.raw_payload.get("text", "")

    # --- 2. Load prompt and compute SHA ---
    prompt_content, prompt_version = _load_prompt(prompt_path)
    system_prompt = prompt_content.replace("{{event_text}}", event_text)

    # --- 3. Start Langfuse span before LLM call ---
    span_id = tracer.start_span(
        ctx.langfuse_trace_id or "",
        "extract_tickers",
        {
            "prompt_version": prompt_version,
            "model": _MODEL,
        },
    )

    # --- 4. Call LLM ---
    t0 = time.monotonic()
    content, input_tokens, output_tokens = await llm.complete(
        system_prompt=system_prompt,
        user_message=event_text,
        max_tokens=_MAX_OUTPUT_TOKENS,
        timeout_seconds=_TIMEOUT_SECONDS,
    )
    latency_ms = int((time.monotonic() - t0) * 1000)

    # --- 5. Parse JSON response ---
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        tracer.end_span(span_id, {"error": "json_decode_failure"}, cost_usd=0.0, latency_ms=latency_ms)
        raise PipelineError("extract_tickers: LLM returned non-JSON response") from exc

    # --- 6. Validate against Pydantic schema (empty list is valid) ---
    try:
        result = TickerExtractionResult(**parsed)
    except (ValidationError, TypeError) as exc:
        tracer.end_span(span_id, {"error": "schema_validation_failure"}, cost_usd=0.0, latency_ms=latency_ms)
        raise PipelineError("extract_tickers: response failed schema validation") from exc

    # --- 7. Accumulate cost via pricing table and enforce ceiling ---
    cost_usd = ctx.cost_accumulator.add_from_tokens(_MODEL, input_tokens, output_tokens)
    ctx.cost_accumulator.check_ceiling(_COST_CEILING_USD)

    tracer.end_span(
        span_id,
        {
            "prompt_version": prompt_version,
            "model": _MODEL,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "latency_ms": latency_ms,
            "cost_usd": cost_usd,
            "tickers": result.tickers,
        },
        cost_usd=cost_usd,
        latency_ms=latency_ms,
    )

    # --- 9. Store result and return ---
    ctx.tickers = result.tickers
    ctx.step_latencies_ms["extract_tickers"] = latency_ms
    return ctx
