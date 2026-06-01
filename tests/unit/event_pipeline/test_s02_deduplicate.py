"""Unit tests for DeduplicateStep (TASK-004, TDD).

Tests written before implementation.
Covers: AC-006.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.event_pipeline.pipeline_state import (
    PipelineState,
    RawEventPayload,
    RawEventSource,
)


def _make_state() -> PipelineState:
    tenant_id = uuid.uuid4()
    raw_event_id = uuid.uuid4()
    return PipelineState(
        raw_event_id=raw_event_id,
        tenant_id=tenant_id,
        payload=RawEventPayload(
            source=RawEventSource.GDELT,
            raw_payload={"title": "Test conflict event"},
            detected_at=datetime.now(timezone.utc),
            tenant_id=tenant_id,
        ),
    )


class TestDedupStepPassesOnNewEvent:
    """test_dedup_step_passes_on_new_event"""

    @pytest.mark.asyncio
    async def test_dedup_step_passes_on_new_event(self):
        """Redis miss: fingerprint set in state and Redis key written."""
        from src.event_pipeline.steps.s02_deduplicate import DeduplicateStep

        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(return_value=None)  # Redis miss
        redis_mock.setex = AsyncMock()

        repo_mock = AsyncMock()
        repo_mock.update_fingerprint = AsyncMock()

        step = DeduplicateStep(redis_client=redis_mock, repo=repo_mock)
        state = _make_state()

        result = await step.execute(state)

        assert result.fingerprint is not None
        assert len(result.fingerprint) > 0
        redis_mock.setex.assert_called_once()


class TestDedupStepRaisesOnRedisHit:
    """test_dedup_step_raises_on_redis_hit"""

    @pytest.mark.asyncio
    async def test_dedup_step_raises_on_redis_hit(self):
        """Redis hit: DuplicateEvent raised immediately."""
        from src.event_pipeline.steps.s02_deduplicate import DeduplicateStep
        from src.event_pipeline.exceptions import DuplicateEvent

        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(return_value=b"1")  # Redis HIT

        repo_mock = AsyncMock()

        step = DeduplicateStep(redis_client=redis_mock, repo=repo_mock)
        state = _make_state()

        with pytest.raises(DuplicateEvent):
            await step.execute(state)


class TestDedupStepUsesConfiguredTtl:
    """test_dedup_step_uses_configured_ttl"""

    @pytest.mark.asyncio
    async def test_dedup_step_uses_configured_ttl(self):
        """SETEX is called with TTL from settings (default 3600)."""
        from src.event_pipeline.steps.s02_deduplicate import DeduplicateStep

        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(return_value=None)
        redis_mock.setex = AsyncMock()

        repo_mock = AsyncMock()
        repo_mock.update_fingerprint = AsyncMock()

        with patch.dict("os.environ", {"DEDUP_TTL_SECONDS": "3600"}):
            step = DeduplicateStep(redis_client=redis_mock, repo=repo_mock)
            state = _make_state()
            await step.execute(state)

        # setex(key, ttl, value) — check ttl arg
        call_args = redis_mock.setex.call_args
        # second positional arg or 'time' keyword
        ttl_arg = call_args.args[1] if len(call_args.args) > 1 else call_args.kwargs.get("time")
        assert ttl_arg == 3600


class TestDedupStepFingerprintConsistency:
    """Fingerprint is deterministic for the same payload."""

    @pytest.mark.asyncio
    async def test_fingerprint_deterministic(self):
        """Two calls with identical payload produce the same fingerprint."""
        from src.event_pipeline.steps.s02_deduplicate import DeduplicateStep

        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(return_value=None)
        redis_mock.setex = AsyncMock()

        repo_mock = AsyncMock()
        repo_mock.update_fingerprint = AsyncMock()

        step = DeduplicateStep(redis_client=redis_mock, repo=repo_mock)

        # Build two states with identical payloads
        tenant_id = uuid.uuid4()
        payload_data = {"title": "identical event", "source": "test"}

        state1 = PipelineState(
            raw_event_id=uuid.uuid4(),
            tenant_id=tenant_id,
            payload=RawEventPayload(
                source=RawEventSource.GDELT,
                raw_payload=payload_data,
                detected_at=datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc),
                tenant_id=tenant_id,
            ),
        )
        state2 = PipelineState(
            raw_event_id=uuid.uuid4(),
            tenant_id=tenant_id,
            payload=RawEventPayload(
                source=RawEventSource.GDELT,
                raw_payload=payload_data,
                detected_at=datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc),
                tenant_id=tenant_id,
            ),
        )

        result1 = await step.execute(state1)
        redis_mock.get = AsyncMock(return_value=None)  # reset for second call
        redis_mock.setex = AsyncMock()
        result2 = await step.execute(state2)

        assert result1.fingerprint == result2.fingerprint
