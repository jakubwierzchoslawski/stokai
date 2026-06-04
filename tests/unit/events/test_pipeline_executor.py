"""
Unit tests for PipelineExecutor.

All step-level dependencies are mocked. No real DB, LLM, or Langfuse calls.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.events.cost_accumulator import CostAccumulator
from src.events.exceptions import CostCeilingExceededError, PipelineError, StepTimeoutError
from src.events.models import (
    ClassificationResult,
    ExposureCandidate,
    PipelineResult,
    RawEvent,
)
from src.events.pipeline_executor import PipelineExecutor


def _make_raw_event(source_provider: str = "gdelt") -> RawEvent:
    return RawEvent(
        source_provider=source_provider,
        occurred_at=datetime(2024, 1, 15, tzinfo=timezone.utc),
        raw_payload={"title": "Test Event", "summary": "Test summary"},
    )


def _make_executor(**overrides) -> PipelineExecutor:
    """Build a PipelineExecutor with all deps mocked."""
    mock_settings = MagicMock()
    mock_settings.ANALOGY_K = 5
    defaults = {
        "geo_event_repo": AsyncMock(),
        "event_exposure_repo": AsyncMock(),
        "event_embedding_repo": AsyncMock(),
        "alert_repo": AsyncMock(),
        "llm_client_haiku": AsyncMock(),
        "llm_client_sonnet": AsyncMock(),
        "embedding_service": AsyncMock(),
        "tracer": MagicMock(),
        "alert_rule_evaluator": AsyncMock(),
        "alert_dispatcher": AsyncMock(),
        "workflow_queue": MagicMock(),
        "db_session": AsyncMock(),
        "settings": mock_settings,
        "twitter_enabled": False,
    }
    defaults.update(overrides)
    return PipelineExecutor(**defaults)


def _wire_happy_path(executor: PipelineExecutor) -> uuid.UUID:
    """Configure all mocks to return valid happy-path values."""
    event_id = uuid.uuid4()

    executor._geo_event_repo.upsert_raw = AsyncMock(return_value=event_id)
    executor._geo_event_repo.persist_classified = AsyncMock()
    executor._event_exposure_repo.bulk_insert = AsyncMock()
    executor._event_embedding_repo.get_by_event_id = AsyncMock(return_value=None)
    executor._event_embedding_repo.save = AsyncMock()
    executor._event_embedding_repo.search_similar = AsyncMock(return_value=[])
    executor._alert_repo.insert_alert = AsyncMock(return_value=uuid.uuid4())
    executor._alert_repo.insert_silent_log = AsyncMock()

    # LLM: classification response (sentiment is float -1.0 to 1.0 per updated models)
    classification_json = (
        '{"category":["conflict"],"intensity":3,"sentiment":-0.8,'
        '"geo_regions":["EMEA"],"affected_sectors":["energy"],"cameo_code":"14"}'
    )
    executor._llm_client_haiku.complete = AsyncMock(
        side_effect=[
            (classification_json, 80, 40),  # classify_event
            ('["XOM"]', 20, 10),            # extract_tickers
        ]
    )
    executor._llm_client_sonnet.complete = AsyncMock(
        return_value=("Energy alert: supply disruption.", 300, 50)
    )

    executor._embedding_service.embed = AsyncMock(return_value=[0.01] * 1536)
    executor._alert_rule_evaluator.evaluate = AsyncMock(return_value=[])
    executor._alert_dispatcher.log_silent = AsyncMock()
    executor._alert_dispatcher.dispatch = AsyncMock()

    executor._tracer.start_trace.return_value = "trace-001"
    executor._tracer.start_span.return_value = "span-001"
    executor._tracer.end_span.return_value = None
    executor._tracer.end_trace.return_value = None

    executor._db_session.execute = AsyncMock(
        return_value=MagicMock(mappings=MagicMock(return_value=[]))
    )
    executor._db_session.flush = AsyncMock()

    return event_id


@pytest.mark.asyncio
class TestPipelineExecutor:

    async def test_successful_run_returns_pipeline_result_with_event_id(self) -> None:
        executor = _make_executor()
        event_id = _wire_happy_path(executor)

        result = await executor.run(_make_raw_event())

        assert isinstance(result, PipelineResult)
        assert result.event_id == event_id

    async def test_step_timeout_error_raises_pipeline_error_and_flushes_trace(
        self,
    ) -> None:
        executor = _make_executor()
        _wire_happy_path(executor)

        # Override upsert_raw to raise StepTimeoutError
        executor._geo_event_repo.upsert_raw = AsyncMock(
            side_effect=StepTimeoutError("timeout in step 1")
        )

        with pytest.raises(PipelineError):
            await executor.run(_make_raw_event())

        # Langfuse trace must still be flushed
        executor._tracer.end_trace.assert_called()

    async def test_cost_ceiling_exceeded_halts_pipeline_raises_pipeline_error(
        self,
    ) -> None:
        executor = _make_executor()
        _wire_happy_path(executor)

        # Make classification add an enormous cost to trigger ceiling
        async def costly_complete(system_prompt, user_message, max_tokens, timeout_seconds):
            raise CostCeilingExceededError("cost ceiling exceeded", accumulated_usd=0.06, ceiling_usd=0.05)

        executor._llm_client_haiku.complete = costly_complete

        with pytest.raises(PipelineError):
            await executor.run(_make_raw_event())

    async def test_step_latencies_recorded_for_all_steps(self) -> None:
        executor = _make_executor()
        _wire_happy_path(executor)

        result = await executor.run(_make_raw_event())

        # At least a subset of expected step names should be present
        expected_steps = {
            "persist_raw_event",
            "classify_event",
            "extract_tickers",
            "compute_exposure_map",
        }
        for step in expected_steps:
            assert step in result.step_latencies_ms, f"Missing latency for {step}"
