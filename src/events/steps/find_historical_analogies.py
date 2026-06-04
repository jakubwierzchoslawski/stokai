"""
Step 7 — find_historical_analogies (PLAN-F-004).

Executes pgvector HNSW cosine top-K search over the event_embedding table,
joins against event_exposure for price_change_t1d, computes sample_size,
and sets low_sample flag when fewer than 5 valid outcomes exist.

Enforces a 3-second timeout via asyncio.wait_for (REQ-N-001).
"""
from __future__ import annotations

import asyncio
import time

from src.config.settings import Settings
from src.events.exceptions import PipelineError, StepTimeoutError
from src.events.models import AnalogSearchResultSet, PipelineContext
from src.storage.repositories.event_embedding import EventEmbeddingRepository


async def find_historical_analogies(
    ctx: PipelineContext,
    embedding_repo: EventEmbeddingRepository,
    settings: Settings,
    timeout_seconds: float = 3.0,
) -> PipelineContext:
    """Find top-K historical event analogies via HNSW cosine search.

    Reads ctx.embedding and calls EventEmbeddingRepository.search_similar().
    Builds an AnalogSearchResultSet with low_sample derived from the results.
    Populates ctx.analogy_result_set and returns updated context.

    Args:
        ctx: Current pipeline context. embedding must be populated.
        embedding_repo: EventEmbeddingRepository implementation (injected).
        settings: Application settings providing analogy_k (env: ANALOGY_K).
        timeout_seconds: Hard budget for the step. Raises StepTimeoutError
            on breach (default 3.0s per REQ-N-001).

    Returns:
        Updated context with ctx.analogy_result_set populated.

    Raises:
        PipelineError: When ctx.embedding is None (step 6 not run yet).
        StepTimeoutError: When the step exceeds timeout_seconds.
    """
    if ctx.embedding is None:
        raise PipelineError(
            "ctx.embedding is None — embed_event (step 6) must run before "
            "find_historical_analogies (step 7)"
        )

    if ctx.event_id is None:
        raise PipelineError(
            "event_id must be set on PipelineContext before find_historical_analogies"
        )

    async def _run() -> PipelineContext:
        t0 = time.monotonic()
        k = settings.ANALOGY_K
        results = await embedding_repo.search_similar(ctx.embedding, k=k)  # type: ignore[arg-type]
        latency_ms = int((time.monotonic() - t0) * 1000)

        # AC-003: low_sample is True if any individual result has low_sample=True
        any_low_sample = any(r.low_sample for r in results)

        result_set = AnalogSearchResultSet(
            results=results,
            k_requested=k,
            low_sample=any_low_sample,
            source_event_id=ctx.event_id,  # type: ignore[arg-type]
        )

        ctx.analogy_result_set = result_set
        ctx.step_latencies_ms["find_historical_analogies"] = latency_ms
        return ctx

    try:
        return await asyncio.wait_for(_run(), timeout=timeout_seconds)
    except asyncio.TimeoutError as exc:
        raise StepTimeoutError(
            f"find_historical_analogies exceeded {timeout_seconds}s budget"
        ) from exc
