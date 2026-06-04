"""
Step 6 — embed_event (PLAN-F-004).

Embeds event text using EmbeddingService (text-embedding-3-small, 500 tokens max)
and persists the VECTOR(1536) to event_embedding table via EventEmbeddingRepository.

Idempotent: checks for existing row before calling API (Principle 2 — Infinite TTL).
Enforces 2-second timeout via asyncio.wait_for.
"""
from __future__ import annotations

import asyncio
import time

from src.ai.embedding.service import EmbeddingService
from src.events.exceptions import PipelineError, StepTimeoutError
from src.events.models import PipelineContext
from src.storage.repositories.event_embedding import EventEmbeddingRepository

_EMBED_MODEL = "text-embedding-3-small"
_MAX_EMBED_TOKENS = 500
_COST_CEILING_USD = 0.05


def _approximate_token_count(text: str) -> int:
    """Approximate token count using word-based heuristic (1.3 tokens per word).

    Capped at _MAX_EMBED_TOKENS to reflect the API's effective input budget.
    """
    return min(int(len(text.split()) * 1.3), _MAX_EMBED_TOKENS)


async def embed_event(
    ctx: PipelineContext,
    embedding_service: EmbeddingService,
    embedding_repo: EventEmbeddingRepository,
    timeout_seconds: float = 2.0,
) -> PipelineContext:
    """Embed event text and persist the vector (idempotent).

    Checks for an existing row in event_embedding before calling the API.
    If an embedding already exists it is returned directly — no API call,
    no cost incurred (Principle 2: Infinite TTL / idempotent re-run safety).

    Args:
        ctx: Current pipeline context. event_id must be set.
        embedding_service: EmbeddingService implementation (injected).
        embedding_repo: EventEmbeddingRepository implementation (injected).
        timeout_seconds: Hard budget for the entire step. Raises StepTimeoutError
            on breach (default 2.0s per REQ-N-001).

    Returns:
        Updated context with ctx.embedding populated.

    Raises:
        PipelineError: When event_id is not set on ctx.
        StepTimeoutError: When the step exceeds timeout_seconds.
        CostCeilingExceededError: When accumulated cost exceeds $0.05 per event.
    """
    if ctx.event_id is None:
        raise PipelineError("event_id must be set on PipelineContext before embed_event")

    async def _run() -> PipelineContext:
        t0 = time.monotonic()

        # AC-005: Check for cached embedding first (idempotency / infinite TTL)
        existing = await embedding_repo.get_by_event_id(ctx.event_id)  # type: ignore[arg-type]
        if existing is not None:
            ctx.embedding = existing
            ctx.step_latencies_ms["embed_event"] = int((time.monotonic() - t0) * 1000)
            return ctx

        # Build event text from raw payload
        payload = ctx.raw_event.raw_payload
        title = payload.get("title", "")
        summary = payload.get("summary", "")
        event_text = f"{title} {summary}".strip()

        # AC-001: Call EmbeddingService with optional Langfuse span
        embedding = await embedding_service.embed(
            event_text, span=ctx.langfuse_span
        )

        # Accumulate cost: approximate input tokens, no output tokens for embeddings
        input_tokens = _approximate_token_count(event_text)
        ctx.cost_accumulator.add_from_tokens(_EMBED_MODEL, input_tokens, 0)
        ctx.cost_accumulator.check_ceiling(_COST_CEILING_USD)

        # Persist — idempotent save (ON CONFLICT DO NOTHING)
        await embedding_repo.save(ctx.event_id, embedding)  # type: ignore[arg-type]

        ctx.embedding = embedding
        ctx.step_latencies_ms["embed_event"] = int((time.monotonic() - t0) * 1000)
        return ctx

    try:
        return await asyncio.wait_for(_run(), timeout=timeout_seconds)
    except asyncio.TimeoutError as exc:
        raise StepTimeoutError(
            f"embed_event exceeded {timeout_seconds}s budget"
        ) from exc
