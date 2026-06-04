"""
EmbeddingBatchProcessor — rate-limited OpenAI embedding generation for cold-start seeding.

Processes (event_id, text) pairs in parallel sub-batches. Retries on rate-limit
errors with exponential backoff. Skips already-embedded events (idempotency).
Writes to event_embedding via repository using INSERT ... ON CONFLICT DO NOTHING.

Reuses the same EmbeddingService abstraction as Mode A pipeline step 6 (DIP).
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Protocol
from uuid import UUID

logger = logging.getLogger(__name__)

# Retry configuration for OpenAI rate limit / API errors
MAX_RETRIES = 3
BASE_BACKOFF_SECONDS = 1.0
PROGRESS_LOG_INTERVAL = 1000


class EmbeddingBatchError(Exception):
    """Raised when embedding fails after max retries for one or more events."""


class IEmbeddingService(Protocol):
    """Minimal protocol matching Mode A EmbeddingService abstraction (DIP)."""

    async def embed(self, text: str) -> list[float]:
        """Return a 1536-dimensional embedding vector for the given text."""
        ...


class IEventEmbeddingRepository(Protocol):
    """Minimal protocol for event_embedding write and existence check (DIP)."""

    async def event_has_embedding(self, event_id: UUID) -> bool:
        """Return True if event_embedding row exists for event_id."""
        ...

    async def upsert_embedding(
        self,
        event_id: UUID,
        embedding: list[float],
    ) -> None:
        """Write (event_id, embedding) with INSERT ... ON CONFLICT DO NOTHING."""
        ...


class EmbeddingBatchProcessor:
    """Processes a list of (event_id, text) pairs and generates OpenAI embeddings.

    Args:
        embedding_service: EmbeddingService abstraction (same as Mode A step 6).
        embedding_repo: Repository for event_embedding persistence.
        concurrency: Number of parallel embed() calls per sub-batch.
    """

    def __init__(
        self,
        embedding_service: IEmbeddingService,
        embedding_repo: IEventEmbeddingRepository,
        concurrency: int = 5,
    ) -> None:
        self._embedding_service = embedding_service
        self._embedding_repo = embedding_repo
        self._concurrency = concurrency

    async def process_batch(
        self,
        items: list[tuple[UUID, str]],
        dry_run: bool = False,
    ) -> int:
        """Generate and store embeddings for (event_id, text) pairs.

        Skips events that already have embeddings (idempotency).
        Processes in sub-batches of self._concurrency using asyncio.gather.

        Args:
            items: List of (event_id, text) tuples to embed.
            dry_run: If True, compute but do not write to DB.

        Returns:
            Number of new embeddings created.
        """
        start_time = time.monotonic()
        created = 0
        total = len(items)

        # Filter already-embedded events
        to_process: list[tuple[UUID, str]] = []
        for event_id, text in items:
            exists = await self._embedding_repo.event_has_embedding(event_id)
            if exists:
                logger.debug("Skipping already-embedded event: %s", event_id)
            else:
                to_process.append((event_id, text))

        logger.info(
            "EmbeddingBatchProcessor: %d items to embed (%d already done)",
            len(to_process),
            total - len(to_process),
        )

        # Process in sub-batches of self._concurrency
        for i in range(0, len(to_process), self._concurrency):
            sub_batch = to_process[i : i + self._concurrency]
            results = await asyncio.gather(
                *[self._embed_with_retry(event_id, text) for event_id, text in sub_batch],
                return_exceptions=True,
            )

            for (event_id, _), result in zip(sub_batch, results):
                if isinstance(result, Exception):
                    raise EmbeddingBatchError(
                        f"Embedding failed for event {event_id} after {MAX_RETRIES} retries: {result}"
                    )
                embedding = result
                if not dry_run:
                    await self._embedding_repo.upsert_embedding(event_id, embedding)
                created += 1

            # Progress logging
            if created > 0 and created % PROGRESS_LOG_INTERVAL == 0:
                elapsed = time.monotonic() - start_time
                rate = created / elapsed if elapsed > 0 else 0
                remaining = len(to_process) - created
                est_remaining = remaining / rate if rate > 0 else 0
                logger.info(
                    "EmbeddingBatchProcessor: %d/%d done, %.1f/s, ~%.0fs remaining",
                    created,
                    len(to_process),
                    rate,
                    est_remaining,
                )

        elapsed = time.monotonic() - start_time
        logger.info(
            "EmbeddingBatchProcessor: completed %d embeddings in %.1fs",
            created,
            elapsed,
        )
        return created

    async def _embed_with_retry(self, event_id: UUID, text: str) -> list[float]:
        """Call EmbeddingService.embed with exponential backoff retry.

        Retries on openai.RateLimitError and openai.APIError (max MAX_RETRIES times).
        Raises EmbeddingBatchError if all retries fail.
        """
        last_exc: Exception | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                return await self._embedding_service.embed(text)
            except Exception as exc:
                exc_name = type(exc).__name__
                is_retryable = (
                    "RateLimitError" in exc_name
                    or "APIError" in exc_name
                    or "RateLimit" in exc_name
                )
                if not is_retryable:
                    raise

                last_exc = exc
                backoff = BASE_BACKOFF_SECONDS * (2 ** (attempt - 1))
                logger.warning(
                    "EmbeddingBatchProcessor: %s on attempt %d/%d for event %s; "
                    "retrying in %.1fs",
                    exc_name,
                    attempt,
                    MAX_RETRIES,
                    event_id,
                    backoff,
                )
                await asyncio.sleep(backoff)

        raise EmbeddingBatchError(
            f"Embedding failed for event {event_id} after {MAX_RETRIES} retries: {last_exc}"
        )
