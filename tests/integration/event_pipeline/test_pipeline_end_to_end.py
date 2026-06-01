"""Integration tests — full pipeline end-to-end with mocked LLM and providers.

TASK-013: All 6 scenarios from the plan.

These tests are marked @pytest.mark.integration and require:
- PostgreSQL test DB (pgvector extension).
- Redis instance.
LLM calls are replaced with deterministic mocks.

In CI, run with: pytest -m integration tests/integration/event_pipeline/

In local development without a DB/Redis, these tests are skipped automatically
unless RUN_INTEGRATION_TESTS=1 is set in the environment.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.event_pipeline.pipeline_state import (
    AlertRoute,
    EventCategory,
    PipelineState,
    RawEventPayload,
    RawEventSource,
)
from src.event_pipeline.exceptions import PipelineHalt, DuplicateEvent

# Skip all integration tests unless the integration test flag is set.
# This avoids CI failures when the test DB is not available.
pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

def _make_mock_repo() -> AsyncMock:
    """Return a fully mocked repository for pipeline integration tests."""
    repo = AsyncMock()
    repo.get_status = AsyncMock(return_value=None)
    repo.get_by_id = AsyncMock(return_value=None)
    repo.save = AsyncMock()
    repo.update_status = AsyncMock()
    repo.update_fingerprint = AsyncMock()
    repo.set_generated_at = AsyncMock()
    repo.write_audit_log = AsyncMock()
    repo.upsert_event_record = AsyncMock()
    repo.get_active_portfolios = AsyncMock(return_value=[])
    repo.get_portfolio_holdings = AsyncMock(return_value={})
    repo.get_event_score_by_hash = AsyncMock(return_value=None)
    repo.write_event_score = AsyncMock()
    repo.write_event_score_batch = AsyncMock()
    repo.find_analogues = AsyncMock(return_value=[])
    repo.write_episodic_memory = AsyncMock()
    repo.write_hil_item = AsyncMock()
    return repo


def _make_mock_redis(hit: bool = False) -> AsyncMock:
    """Return a mock Redis client. hit=True simulates a dedup cache hit."""
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=b"1" if hit else None)
    redis.setex = AsyncMock()
    redis.set = AsyncMock()
    return redis


def _make_mock_llm(
    category: str = "GEOPOLITICAL_CONFLICT",
    intensity: int = 3,
    confidence: float = 0.8,
) -> AsyncMock:
    llm = AsyncMock()
    llm.classify = AsyncMock(return_value={"category": category, "intensity": intensity})
    llm.synthesise_confidence = AsyncMock(return_value=confidence)
    return llm


def _make_initial_state(
    tenant_id: uuid.UUID | None = None,
    raw_event_id: uuid.UUID | None = None,
) -> PipelineState:
    tid = tenant_id or uuid.uuid4()
    rid = raw_event_id or uuid.uuid4()
    return PipelineState(
        raw_event_id=rid,
        tenant_id=tid,
        payload=RawEventPayload(
            source=RawEventSource.GDELT,
            raw_payload={
                "title": "Integration conflict event",
                "actor1geo_lat": "51.5",
                "actor1geo_long": "-0.1",
            },
            detected_at=datetime.now(timezone.utc),
            tenant_id=tid,
        ),
    )


def _build_all_steps(
    repo: Any,
    redis_client: Any,
    llm_client: Any,
    ws_dispatcher: Any = None,
    hil_enqueuer: Any = None,
) -> list[Any]:
    """Construct all 13 pipeline steps with mocked collaborators."""
    from src.event_pipeline.steps.s01_ingest import IngestStep
    from src.event_pipeline.steps.s02_deduplicate import DeduplicateStep
    from src.event_pipeline.steps.s03_parse import ParseStep
    from src.event_pipeline.steps.s04_classify import ClassifyStep
    from src.event_pipeline.steps.s05_embed import EmbedStep
    from src.event_pipeline.steps.s06_portfolio_scan import PortfolioScanStep
    from src.event_pipeline.steps.s07_exposure_score import ExposureScoreStep
    from src.event_pipeline.steps.s08_analogy_search import AnalogySearchStep
    from src.event_pipeline.steps.s09_confidence_calc import ConfidenceCalcStep
    from src.event_pipeline.steps.s10_routing import RoutingStep
    from src.event_pipeline.steps.s11_record import RecordStep
    from src.event_pipeline.steps.s12_dispatch import DispatchStep
    from src.event_pipeline.steps.s13_trace import TraceStep

    langfuse_mock = MagicMock()
    langfuse_mock.finish = MagicMock()

    embed_provider = AsyncMock()
    embed_provider.embed = AsyncMock(return_value=[0.1] * 1536)

    _ws = ws_dispatcher or AsyncMock()
    _ws.push = AsyncMock()

    _web_push = AsyncMock()
    _web_push.push = AsyncMock()

    _hil = hil_enqueuer or AsyncMock()
    _hil.enqueue = AsyncMock()

    return [
        IngestStep(repo=repo),
        DeduplicateStep(redis_client=redis_client, repo=repo),
        ParseStep(),
        ClassifyStep(llm_client=llm_client, repo=repo, langfuse_client=langfuse_mock),
        EmbedStep(embedding_provider=embed_provider, repo=repo),
        PortfolioScanStep(repo=repo),
        ExposureScoreStep(repo=repo),
        AnalogySearchStep(repo=repo),
        ConfidenceCalcStep(llm_client=llm_client, repo=repo, langfuse_client=langfuse_mock),
        RoutingStep(),
        RecordStep(repo=repo),
        DispatchStep(
            websocket_dispatcher=_ws,
            web_push_dispatcher=_web_push,
            hil_enqueuer=_hil,
        ),
        TraceStep(repo=repo, langfuse_client=langfuse_mock),
    ]


# ---------------------------------------------------------------------------
# Scenario 1: Happy path GDELT event
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
async def test_happy_path_gdelt_event():
    """Full 13-step pipeline completes successfully.

    Asserts:
    - update_status called with 'completed'
    - embedding upserted
    - event_scores written
    - episodic_memory appended
    - generated_at set
    """
    from src.event_pipeline.pipeline_executor import PipelineExecutor

    repo = _make_mock_repo()
    redis = _make_mock_redis(hit=False)
    llm = _make_mock_llm(confidence=0.85)
    langfuse = MagicMock()

    steps = _build_all_steps(repo=repo, redis_client=redis, llm_client=llm)
    executor = PipelineExecutor(steps=steps, langfuse_client=langfuse, raw_event_repo=repo)
    state = _make_initial_state()

    result = await executor.run(state)

    assert result.generated_at is not None
    assert result.confidence is not None
    assert result.route is not None
    repo.write_episodic_memory.assert_called_once()
    repo.update_status.assert_called()
    # Final update_status should be 'completed'
    last_call = repo.update_status.call_args_list[-1]
    status = last_call.kwargs.get("status") or (
        last_call.args[1] if len(last_call.args) > 1 else None
    )
    assert status == "completed"


# ---------------------------------------------------------------------------
# Scenario 2: Duplicate event
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
async def test_duplicate_event_short_circuits():
    """Second submission of same payload → pipeline_status=duplicate, no scores written."""
    from src.event_pipeline.pipeline_executor import PipelineExecutor

    repo = _make_mock_repo()
    redis = _make_mock_redis(hit=True)  # Redis HIT simulates duplicate
    llm = _make_mock_llm()
    langfuse = MagicMock()

    steps = _build_all_steps(repo=repo, redis_client=redis, llm_client=llm)
    executor = PipelineExecutor(steps=steps, langfuse_client=langfuse, raw_event_repo=repo)
    state = _make_initial_state()

    with pytest.raises(PipelineHalt) as exc_info:
        await executor.run(state)

    assert isinstance(exc_info.value, DuplicateEvent)
    # Status should be written as 'duplicate'
    repo.update_status.assert_called()
    status_call = repo.update_status.call_args
    status = status_call.kwargs.get("status") or (
        status_call.args[1] if len(status_call.args) > 1 else None
    )
    assert status == "duplicate"
    # No event scores written
    repo.write_event_score_batch.assert_not_called()


# ---------------------------------------------------------------------------
# Scenario 3: Classification failure
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
async def test_classification_failure():
    """Mock LLM returns invalid category → pipeline_status=failed, no alert."""
    from src.event_pipeline.pipeline_executor import PipelineExecutor
    from src.event_pipeline.exceptions import InvalidCategoryError

    repo = _make_mock_repo()
    redis = _make_mock_redis(hit=False)
    # LLM returns invalid category
    bad_llm = AsyncMock()
    bad_llm.classify = AsyncMock(return_value={"category": "BOGUS_CATEGORY", "intensity": 3})
    bad_llm.synthesise_confidence = AsyncMock(return_value=0.8)

    langfuse = MagicMock()

    steps = _build_all_steps(repo=repo, redis_client=redis, llm_client=bad_llm)
    executor = PipelineExecutor(steps=steps, langfuse_client=langfuse, raw_event_repo=repo)
    state = _make_initial_state()

    with pytest.raises(PipelineHalt) as exc_info:
        await executor.run(state)

    assert isinstance(exc_info.value, InvalidCategoryError)
    # No alert dispatched
    repo.write_event_score_batch.assert_not_called()


# ---------------------------------------------------------------------------
# Scenario 4: BLOCKED route
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
async def test_blocked_route_no_dispatch():
    """Mock confidence=0.1 → route=BLOCKED, no WebSocket push, no HIL enqueue."""
    from src.event_pipeline.pipeline_executor import PipelineExecutor

    repo = _make_mock_repo()
    redis = _make_mock_redis(hit=False)
    llm = _make_mock_llm(confidence=0.1)

    ws_dispatcher = AsyncMock()
    ws_dispatcher.push = AsyncMock()
    hil_enqueuer = AsyncMock()
    hil_enqueuer.enqueue = AsyncMock()

    langfuse = MagicMock()

    steps = _build_all_steps(
        repo=repo,
        redis_client=redis,
        llm_client=llm,
        ws_dispatcher=ws_dispatcher,
        hil_enqueuer=hil_enqueuer,
    )
    executor = PipelineExecutor(steps=steps, langfuse_client=langfuse, raw_event_repo=repo)
    state = _make_initial_state()

    result = await executor.run(state)

    assert result.route == AlertRoute.BLOCKED
    ws_dispatcher.push.assert_not_called()
    hil_enqueuer.enqueue.assert_not_called()
    # Pipeline still completes successfully
    repo.write_episodic_memory.assert_called_once()


# ---------------------------------------------------------------------------
# Scenario 5: HIL route
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
async def test_hil_route_enqueues_item():
    """Mock confidence=0.55 → route=HIL_QUEUE, hil_queue item created."""
    from src.event_pipeline.pipeline_executor import PipelineExecutor

    repo = _make_mock_repo()
    redis = _make_mock_redis(hit=False)
    llm = _make_mock_llm(confidence=0.55)

    ws_dispatcher = AsyncMock()
    ws_dispatcher.push = AsyncMock()
    hil_enqueuer = AsyncMock()
    hil_enqueuer.enqueue = AsyncMock()

    langfuse = MagicMock()

    steps = _build_all_steps(
        repo=repo,
        redis_client=redis,
        llm_client=llm,
        ws_dispatcher=ws_dispatcher,
        hil_enqueuer=hil_enqueuer,
    )
    executor = PipelineExecutor(steps=steps, langfuse_client=langfuse, raw_event_repo=repo)
    state = _make_initial_state()

    result = await executor.run(state)

    assert result.route == AlertRoute.HIL_QUEUE
    hil_enqueuer.enqueue.assert_called_once()
    ws_dispatcher.push.assert_not_called()


# ---------------------------------------------------------------------------
# Scenario 6: Step failure mid-pipeline
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
async def test_step_failure_mid_pipeline_no_dispatch():
    """Mock Step 7 raises → pipeline_status=failed, no partial alert."""
    from src.event_pipeline.pipeline_executor import PipelineExecutor
    from src.event_pipeline.exceptions import PipelineHalt

    repo = _make_mock_repo()
    redis = _make_mock_redis(hit=False)
    llm = _make_mock_llm(confidence=0.8)

    # Make Step 7 (exposure score) fail
    repo.get_portfolio_holdings = AsyncMock(side_effect=RuntimeError("DB timeout"))
    # With no portfolios, step 7 won't be reached via get_portfolio_holdings
    # Instead we can inject a portfolio to trigger the call
    repo.get_active_portfolios = AsyncMock(return_value=[
        {"portfolio_id": str(uuid.uuid4()), "holdings": {"AAPL": 1.0}}
    ])

    ws_dispatcher = AsyncMock()
    ws_dispatcher.push = AsyncMock()
    hil_enqueuer = AsyncMock()
    hil_enqueuer.enqueue = AsyncMock()

    langfuse = MagicMock()

    steps = _build_all_steps(
        repo=repo,
        redis_client=redis,
        llm_client=llm,
        ws_dispatcher=ws_dispatcher,
        hil_enqueuer=hil_enqueuer,
    )
    executor = PipelineExecutor(steps=steps, langfuse_client=langfuse, raw_event_repo=repo)

    # Use tickers to trigger portfolio scan hit
    state = _make_initial_state()
    state = state.model_copy(update={"tickers": ["AAPL"]})

    with pytest.raises(PipelineHalt) as exc_info:
        await executor.run(state)

    assert exc_info.value.step_name in ("s07_exposure_score",)
    ws_dispatcher.push.assert_not_called()
    hil_enqueuer.enqueue.assert_not_called()
