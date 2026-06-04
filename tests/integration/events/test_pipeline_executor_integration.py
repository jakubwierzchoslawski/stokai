"""
Integration tests for PipelineExecutor.

Uses mocked LLM clients and a mocked DB session (no real PostgreSQL required
for CI — the full DB integration is in test_pipeline_e2e.py).
"""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.events.models import PipelineResult, RawEvent
from src.events.pipeline_executor import PipelineExecutor


def _make_raw_event() -> RawEvent:
    return RawEvent(
        source_provider="edgar",
        occurred_at=datetime(2024, 3, 10, tzinfo=timezone.utc),
        raw_payload={
            "title": "Quarterly earnings miss signals sector headwinds",
            "summary": "Company reports 20% below-consensus earnings; sector sentiment negative.",
        },
    )


def _make_executor() -> PipelineExecutor:
    event_id = uuid.uuid4()

    geo_repo = AsyncMock()
    geo_repo.upsert_raw = AsyncMock(return_value=event_id)
    geo_repo.persist_classified = AsyncMock()

    exposure_repo = AsyncMock()
    exposure_repo.bulk_insert = AsyncMock()

    embedding_repo = AsyncMock()
    embedding_repo.get_by_event_id = AsyncMock(return_value=None)
    embedding_repo.save = AsyncMock()
    embedding_repo.search_similar = AsyncMock(return_value=[])

    alert_repo = AsyncMock()
    alert_repo.insert_alert = AsyncMock(return_value=uuid.uuid4())
    alert_repo.insert_silent_log = AsyncMock()

    classification_json = (
        '{"category":["earnings"],"intensity":2,"sentiment":-0.8,'
        '"geo_regions":["North America"],"affected_sectors":["technology"],"cameo_code":"012"}'
    )
    haiku = AsyncMock()
    haiku.complete = AsyncMock(
        side_effect=[
            (classification_json, 100, 50),
            ('["AAPL"]', 30, 10),
        ]
    )
    sonnet = AsyncMock()
    sonnet.complete = AsyncMock(
        return_value=("Tech earnings miss creates headwinds.", 400, 60)
    )

    embedding_service = AsyncMock()
    embedding_service.embed = AsyncMock(return_value=[0.02] * 1536)

    tracer = MagicMock()
    tracer.start_trace.return_value = "integration-trace-001"
    tracer.start_span.return_value = "integration-span-001"

    evaluator = AsyncMock()
    evaluator.evaluate = AsyncMock(return_value=[])

    dispatcher = AsyncMock()
    dispatcher.log_silent = AsyncMock()

    workflow_queue = MagicMock()

    session = AsyncMock()
    session.execute = AsyncMock(
        return_value=MagicMock(
            mappings=MagicMock(return_value=[]),
            scalar_one=MagicMock(return_value=event_id),
            scalar_one_or_none=MagicMock(return_value=None),
        )
    )
    session.flush = AsyncMock()

    mock_settings = MagicMock()
    mock_settings.ANALOGY_K = 5

    return PipelineExecutor(
        geo_event_repo=geo_repo,
        event_exposure_repo=exposure_repo,
        event_embedding_repo=embedding_repo,
        alert_repo=alert_repo,
        llm_client_haiku=haiku,
        llm_client_sonnet=sonnet,
        embedding_service=embedding_service,
        tracer=tracer,
        alert_rule_evaluator=evaluator,
        alert_dispatcher=dispatcher,
        workflow_queue=workflow_queue,
        db_session=session,
        settings=mock_settings,
        twitter_enabled=False,
    )


@pytest.mark.asyncio
@pytest.mark.integration
class TestPipelineExecutorIntegration:

    async def test_full_12_step_run_completes_without_exception(self) -> None:
        executor = _make_executor()
        result = await executor.run(_make_raw_event())

        assert isinstance(result, PipelineResult)
        assert result.event_id is not None
        assert result.langfuse_trace_id == "integration-trace-001"

    async def test_total_cost_within_ceiling(self) -> None:
        executor = _make_executor()
        result = await executor.run(_make_raw_event())

        assert result.total_cost_usd <= 0.05, (
            f"Cost ceiling exceeded: {result.total_cost_usd:.4f} > 0.05"
        )

    async def test_all_12_step_latencies_present(self) -> None:
        executor = _make_executor()
        result = await executor.run(_make_raw_event())

        expected = [
            "persist_raw_event",
            "classify_event",
            "extract_tickers",
            "compute_exposure_map",
            "persist_event_record",
            "embed_event",
            "find_historical_analogies",
            "generate_alert_text",
            "evaluate_alert_rules",
            "dispatch_or_log_silent",
            "enqueue_deep_dive",
        ]
        for step in expected:
            assert step in result.step_latencies_ms, f"Missing latency for step: {step}"
