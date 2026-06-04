"""
Step 2 — classify_event.

Calls Claude Haiku 4.5 to classify the raw event into structured metadata.
Prompt is loaded from a versioned Markdown file; SHA-256 of the file bytes
is recorded on the Langfuse span as `prompt_version`.

All LLM calls are traced via Langfuse.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path

from pydantic import ValidationError

from src.ai.interfaces.i_langfuse_tracer import ILangfuseTracer
from src.ai.interfaces.i_llm_client import ILLMClient
from src.events.exceptions import PipelineError
from src.events.models import ClassificationResult, PipelineContext

logger = logging.getLogger(__name__)

_MODEL = "claude-haiku-4-5"
_MAX_INPUT_TOKENS = 2000
_MAX_OUTPUT_TOKENS = 200
_TIMEOUT_SECONDS = 5.0
_COST_CEILING_USD = 0.05

_DEFAULT_PROMPT_PATH = Path("prompts/classifiers/event_classifier.md")


def _load_prompt(prompt_path: Path) -> tuple[str, str]:
    """Load prompt content and compute its SHA-256.

    Returns:
        Tuple of (prompt_content, hex_sha256).
    """
    raw_bytes = prompt_path.read_bytes()
    sha = hashlib.sha256(raw_bytes).hexdigest()
    content = raw_bytes.decode("utf-8")
    return content, sha


def _approximate_token_count(text: str) -> int:
    """Approximate token count using word-based heuristic (1.3 tokens per word)."""
    return int(len(text.split()) * 1.3)


async def classify_event(
    ctx: PipelineContext,
    llm: ILLMClient,
    tracer: ILangfuseTracer,
    prompt_path: Path = _DEFAULT_PROMPT_PATH,
) -> PipelineContext:
    """Classify the raw event using Claude Haiku 4.5 (step 2 of Mode A pipeline).

    Args:
        ctx: Current pipeline context.
        llm: LLM client configured for claude-haiku-4-5.
        tracer: Langfuse tracer for observability.
        prompt_path: Path to the versioned prompt Markdown file.

    Returns:
        Updated context with ``ctx.classification`` populated.

    Raises:
        PipelineError: On empty event text, malformed LLM response, or schema
            validation failure.
        StepTimeoutError: When the LLM call exceeds 5 seconds.
        CostCeilingExceededError: When accumulated cost exceeds $0.05 per event.
    """
    # --- 1. Extract event text and guard against empty input ---
    event_text: str = ctx.raw_event.raw_payload.get("text", "")
    if not event_text:
        raise PipelineError("classify_event received empty event text")

    # --- 2. Pre-truncate if input would exceed token budget ---
    approx_tokens = _approximate_token_count(event_text)
    if approx_tokens > _MAX_INPUT_TOKENS:
        logger.warning(
            "classify_event: event text approximate token count %d exceeds limit %d; truncating.",
            approx_tokens,
            _MAX_INPUT_TOKENS,
        )
        # Truncate words to fit within budget
        words = event_text.split()
        max_words = int(_MAX_INPUT_TOKENS / 1.3)
        event_text = " ".join(words[:max_words])

    # --- 3. Load prompt and compute SHA ---
    prompt_content, prompt_version = _load_prompt(prompt_path)
    system_prompt = prompt_content.replace("{{event_text}}", event_text)

    # --- 4. Start Langfuse span before LLM call ---
    span_id = tracer.start_span(
        ctx.langfuse_trace_id or "",
        "classify_event",
        {
            "prompt_version": prompt_version,
            "model": _MODEL,
            "source_provider": ctx.raw_event.source_provider,
        },
    )

    # --- 5. Call LLM ---
    t0 = time.monotonic()
    content, input_tokens, output_tokens = await llm.complete(
        system_prompt=system_prompt,
        user_message=event_text,
        max_tokens=_MAX_OUTPUT_TOKENS,
        timeout_seconds=_TIMEOUT_SECONDS,
    )
    latency_ms = int((time.monotonic() - t0) * 1000)

    # --- 6. Parse JSON response ---
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        tracer.end_span(span_id, {"error": "json_decode_failure"}, cost_usd=0.0, latency_ms=latency_ms)
        raise PipelineError("classify_event: LLM returned non-JSON response") from exc

    # --- 7. Validate against Pydantic schema ---
    try:
        result = ClassificationResult(**parsed)
    except (ValidationError, TypeError) as exc:
        tracer.end_span(span_id, {"error": "schema_validation_failure"}, cost_usd=0.0, latency_ms=latency_ms)
        raise PipelineError("classify_event: response failed schema validation") from exc

    # --- 8. Accumulate cost via pricing table and enforce ceiling ---
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
            "classification": result.model_dump(),
        },
        cost_usd=cost_usd,
        latency_ms=latency_ms,
    )

    # --- 10. Store result and return ---
    ctx.classification = result
    ctx.step_latencies_ms["classify_event"] = latency_ms
    return ctx
