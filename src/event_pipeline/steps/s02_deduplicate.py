"""Step 2: DEDUPLICATE — fingerprint computation and Redis SETEX check.

Architecture enforcement:
  P-02 Cache-First Lookup — Redis SETEX as primary dedup gate.
  AC-006 — second submission of same payload short-circuits after Step 2.

Single Responsibility: fingerprint computation, Redis check, and DB guard.
Dependency Inversion: Redis client and RawEventRepository are injected.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from typing import Any

from src.event_pipeline.exceptions import DuplicateEvent
from src.event_pipeline.pipeline_state import PipelineState

logger = logging.getLogger(__name__)

_DEFAULT_DEDUP_TTL = 3600  # 1 hour
_DEDUP_KEY_PREFIX = "event:dedup:"


def _compute_fingerprint(state: PipelineState) -> str:
    """Compute a deterministic SHA-256 fingerprint for the event payload.

    The fingerprint is derived from source + canonical JSON of raw_payload.
    Canonical JSON uses sorted keys and no extra whitespace for stability.
    """
    source_val = state.payload.source.value
    payload_json = json.dumps(state.payload.raw_payload, sort_keys=True, ensure_ascii=False)
    raw = f"{source_val}:{payload_json}"
    return hashlib.sha256(raw.encode()).hexdigest()


class DeduplicateStep:
    """Pipeline Step 2: DEDUPLICATE.

    Computes the event fingerprint and checks Redis for an existing key.
    If the key exists, raises ``DuplicateEvent`` to halt the pipeline.
    If the key is absent, writes the key (SETEX with configured TTL) and
    records the fingerprint on the RawEvent DB record.

    Parameters
    ----------
    redis_client:
        Async Redis client exposing ``get`` and ``setex`` methods.
    repo:
        RawEventRepository for updating the fingerprint column.
    """

    step_name: str = "s02_deduplicate"

    def __init__(self, redis_client: Any, repo: Any) -> None:
        self._redis = redis_client
        self._repo = repo
        self._ttl = int(os.environ.get("DEDUP_TTL_SECONDS", _DEFAULT_DEDUP_TTL))

    async def execute(self, state: PipelineState) -> PipelineState:
        """Compute fingerprint and check/write the Redis dedup key."""
        fingerprint = _compute_fingerprint(state)
        redis_key = f"{_DEDUP_KEY_PREFIX}{fingerprint}"

        existing = await self._redis.get(redis_key)
        if existing is not None:
            logger.info(
                "Step 2 (DEDUPLICATE): duplicate detected raw_event_id=%s fingerprint=%s",
                state.raw_event_id,
                fingerprint,
            )
            raise DuplicateEvent(
                step_name=self.step_name,
                detail=f"Fingerprint {fingerprint} already present in dedup window",
            )

        # Write Redis dedup key with TTL
        await self._redis.setex(redis_key, self._ttl, "1")

        # Persist fingerprint to DB record
        await self._repo.update_fingerprint(state.raw_event_id, fingerprint)

        logger.info(
            "Step 2 (DEDUPLICATE): new event accepted raw_event_id=%s fingerprint=%s",
            state.raw_event_id,
            fingerprint,
        )

        return state.model_copy(update={"fingerprint": fingerprint})
