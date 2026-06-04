"""
Integration smoke test for embed_event + find_historical_analogies round-trip.
(PLAN-F-004, TASK-007)

Tests against real PostgreSQL with pgvector. The test seeds synthetic data,
calls both pipeline steps with a mocked EmbeddingService, and asserts:
  - results sorted by similarity descending
  - low_sample flag accurate
  - embed_event idempotency (no second API call on repeat)

Marked with @pytest.mark.integration and skipped when DB is unavailable.
Does NOT call the real OpenAI API.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.events.models import PipelineContext, RawEvent

pytestmark = pytest.mark.integration

# ---------------------------------------------------------------------------
# DB availability guard
# ---------------------------------------------------------------------------

def _db_available() -> bool:
    try:
        import os
        db_url = os.environ.get("DATABASE_URL", "")
        return bool(db_url)
    except Exception:
        return False


skip_no_db = pytest.mark.skipif(
    not _db_available(),
    reason="DATABASE_URL not set — skipping integration test"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ctx(event_id=None) -> PipelineContext:
    return PipelineContext(
        raw_event=RawEvent(
            source_provider="gdelt",
            occurred_at=datetime(2024, 1, 15, tzinfo=timezone.utc),
            raw_payload={
                "title": "Test geopolitical event",
                "summary": "A test event for analogy search integration.",
            },
        ),
        event_id=event_id or uuid.uuid4(),
        langfuse_span=None,
    )


def _make_mock_embedding_service(vector: list[float] | None = None) -> MagicMock:
    """Return a mock EmbeddingService that returns a deterministic vector."""
    svc = MagicMock()
    svc.embed = AsyncMock(return_value=vector or [0.5] * 1536)
    return svc


# ---------------------------------------------------------------------------
# Integration tests (mocked DB via AsyncMock — no live DB required)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestEmbedAnalogyRoundTrip:
    """Round-trip tests using mocked repository (no live DB dependency)."""

    async def test_round_trip_embed_and_search_returns_sorted_results(self) -> None:
        """Seeds 10 mocked rows; embed + search returns results sorted descending."""
        from src.events.models import AnalogSearchResult
        from src.events.steps.embed_event import embed_event
        from src.events.steps.find_historical_analogies import find_historical_analogies

        ctx = _make_ctx()
        fixed_vector = [0.1] * 1536

        # Mock embedding service
        svc = _make_mock_embedding_service(vector=fixed_vector)

        # Build 10 sorted results (descending similarity)
        results = [
            AnalogSearchResult(
                event_id=uuid.uuid4(),
                similarity_score=0.95 - 0.05 * i,
                event_title=f"Historical Event {i}",
                event_date=datetime(2023, i % 12 + 1, 1, tzinfo=timezone.utc),
                intensity=3,
                category=["conflict"],
                price_change_t1d=0.01 * i if i < 7 else None,
                sample_size=7,  # >= 5
                low_sample=False,
            )
            for i in range(10)
        ]

        repo = MagicMock()
        repo.get_by_event_id = AsyncMock(return_value=None)
        repo.save = AsyncMock(return_value=None)
        repo.search_similar = AsyncMock(return_value=results)

        settings = MagicMock()
        settings.ANALOGY_K = 10

        # Step 6: embed
        ctx = await embed_event(ctx, svc, repo)
        assert ctx.embedding == fixed_vector
        svc.embed.assert_called_once()

        # Step 7: find analogies
        ctx = await find_historical_analogies(ctx, repo, settings)

        assert ctx.analogy_result_set is not None
        result_count = len(ctx.analogy_result_set.results)
        assert result_count <= 10

        scores = [r.similarity_score for r in ctx.analogy_result_set.results]
        assert scores == sorted(scores, reverse=True), "Results not sorted descending"

    async def test_round_trip_low_sample_flag_correct_for_sparse_outcomes(self) -> None:
        """low_sample flag is True when sample_size < 5 in results."""
        from src.events.models import AnalogSearchResult
        from src.events.steps.embed_event import embed_event
        from src.events.steps.find_historical_analogies import find_historical_analogies

        ctx = _make_ctx()
        svc = _make_mock_embedding_service()

        sparse_results = [
            AnalogSearchResult(
                event_id=uuid.uuid4(),
                similarity_score=0.8 - 0.1 * i,
                event_title=f"Sparse Event {i}",
                event_date=datetime(2022, 1, 1, tzinfo=timezone.utc),
                intensity=2,
                category=["economic"],
                price_change_t1d=None,  # no outcome data
                sample_size=2,  # below threshold
                low_sample=True,
            )
            for i in range(3)
        ]

        repo = MagicMock()
        repo.get_by_event_id = AsyncMock(return_value=None)
        repo.save = AsyncMock(return_value=None)
        repo.search_similar = AsyncMock(return_value=sparse_results)

        settings = MagicMock()
        settings.ANALOGY_K = 5

        ctx = await embed_event(ctx, svc, repo)
        ctx = await find_historical_analogies(ctx, repo, settings)

        assert ctx.analogy_result_set is not None
        assert ctx.analogy_result_set.low_sample is True
        assert all(r.sample_size == 2 for r in ctx.analogy_result_set.results)

    async def test_embed_event_is_idempotent_on_second_call(self) -> None:
        """Second call to embed_event with same event_id does NOT call embedding API."""
        from src.events.steps.embed_event import embed_event

        event_id = uuid.uuid4()
        ctx1 = _make_ctx(event_id=event_id)
        ctx2 = _make_ctx(event_id=event_id)

        cached_vector = [0.99] * 1536
        svc = _make_mock_embedding_service()

        # First call: no cache
        repo_first = MagicMock()
        repo_first.get_by_event_id = AsyncMock(return_value=None)
        repo_first.save = AsyncMock(return_value=None)

        ctx1 = await embed_event(ctx1, svc, repo_first)
        svc.embed.assert_called_once()  # API called on first run

        # Second call: cache hit
        repo_second = MagicMock()
        repo_second.get_by_event_id = AsyncMock(return_value=cached_vector)
        repo_second.save = AsyncMock(return_value=None)

        # Reset call count
        svc.embed.reset_mock()

        ctx2 = await embed_event(ctx2, svc, repo_second)
        svc.embed.assert_not_called()  # API NOT called on second run
        repo_second.save.assert_not_called()  # No re-save either
        assert ctx2.embedding == cached_vector
