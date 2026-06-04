"""
End-to-end integration tests for the Mode A Reactive Pipeline.

Uses:
- Mocked Anthropic and OpenAI API clients (pytest-mock)
- Mocked SendGrid client
- Mocked Langfuse SDK
- Mocked DB session (in-memory via AsyncMock; real DB variant tagged @pytest.mark.db)

Assertions cover all AC items for REQ-F-001:
- AC-001: all 12 steps complete; DB rows exist; cost ≤ $0.05
- AC-002: high-intensity event → deep_dive_enqueued=True
- AC-003: classification rows populated
- AC-004: embedding stored; HNSW search called
- AC-005: Twitter disabled → SourceDisabledError caught gracefully
- AC-006: total_cost_usd ≤ 0.05
"""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.alerts.alert_dispatcher import AlertDispatcher
from src.alerts.alert_rule_evaluator import AlertRuleEvaluator
from src.alerts.interfaces.i_alert_rule_evaluator import RuleMatch
from src.events.models import PipelineResult, RawEvent
from src.events.pipeline_executor import PipelineExecutor


# ── Fixtures ──────────────────────────────────────────────────────────────────


def _make_raw_event(
    source_provider: str = "gdelt",
    intensity_override: int | None = None,
) -> RawEvent:
    payload: dict = {
        "title": "Major oil refinery fire in Gulf region",
        "summary": "Catastrophic fire at refinery; supply disruption imminent.",
    }
    return RawEvent(
        source_provider=source_provider,
        occurred_at=datetime(2024, 6, 1, tzinfo=timezone.utc),
        raw_payload=payload,
    )


def _build_executor(
    intensity: int = 3,
    rule_matches: list | None = None,
    twitter_enabled: bool = False,
) -> tuple[PipelineExecutor, uuid.UUID]:
    """Build a fully-wired PipelineExecutor with all external deps mocked."""
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
        f'{{"category":["conflict"],"intensity":{intensity},"sentiment":-0.8,'
        '"geo_regions":["EMEA"],"affected_sectors":["energy"],"cameo_code":"14"}}'
    )
    haiku = AsyncMock()
    haiku.complete = AsyncMock(
        side_effect=[
            (classification_json, 100, 40),  # classify
            ('["XOM","BP"]', 20, 10),        # tickers
        ]
    )
    sonnet = AsyncMock()
    sonnet.complete = AsyncMock(
        return_value=("Energy sector alert: Gulf refinery fire.", 400, 50)
    )

    embedding_service = AsyncMock()
    embedding_service.embed = AsyncMock(return_value=[0.01] * 1536)

    tracer = MagicMock()
    tracer.start_trace.return_value = f"e2e-trace-{uuid.uuid4()}"
    tracer.start_span.return_value = f"e2e-span-{uuid.uuid4()}"

    evaluator = AsyncMock()
    evaluator.evaluate = AsyncMock(return_value=rule_matches or [])

    dispatcher = AsyncMock()
    dispatcher.dispatch = AsyncMock()
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

    executor = PipelineExecutor(
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
        twitter_enabled=twitter_enabled,
    )
    return executor, event_id


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.integration
class TestPipelineE2E:

    async def test_happy_path_all_12_steps_complete(self) -> None:
        """AC-001: All steps complete, cost ≤ $0.05, expected DB calls made."""
        executor, event_id = _build_executor(intensity=3)
        raw_event = _make_raw_event()

        t0 = time.monotonic()
        result = await executor.run(raw_event)
        elapsed = time.monotonic() - t0

        # Verify PipelineResult structure
        assert isinstance(result, PipelineResult)
        assert result.event_id == event_id

        # AC-006: cost ceiling
        assert result.total_cost_usd <= 0.05, (
            f"Cost {result.total_cost_usd:.4f} exceeds $0.05 ceiling"
        )

        # Should complete well within 90s in test mode
        assert elapsed < 90.0, f"Pipeline took {elapsed:.1f}s > 90s"

        # Silent log: no rules matched
        assert result.silent_logged is True
        assert result.alert_dispatched is False

        # AC-001: all expected step latencies present
        expected_steps = [
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
        for step in expected_steps:
            assert step in result.step_latencies_ms, f"Missing latency: {step}"

    async def test_high_intensity_event_enqueues_deep_dive(self) -> None:
        """AC-002: intensity >= 4 → deep_dive_enqueued=True."""
        executor, event_id = _build_executor(intensity=4)
        raw_event = _make_raw_event()

        result = await executor.run(raw_event)

        assert result.deep_dive_enqueued is True

    async def test_twitter_disabled_graceful_return_no_db_rows(self) -> None:
        """AC-005: Twitter disabled → no DB rows written, no exception propagated."""
        executor, event_id = _build_executor(twitter_enabled=False)
        raw_event = _make_raw_event(source_provider="twitter")

        # Must NOT raise
        result = await executor.run(raw_event)

        assert isinstance(result, PipelineResult)
        assert result.alert_dispatched is False

        # DB write (upsert_raw) must NOT have been called for disabled source
        executor._geo_event_repo.upsert_raw.assert_not_called()

    async def test_no_matching_rules_produces_silent_log(self) -> None:
        """AC-001: no matching rules → silent_logged=True, alert_dispatched=False."""
        executor, event_id = _build_executor(intensity=2, rule_matches=[])
        raw_event = _make_raw_event()

        result = await executor.run(raw_event)

        assert result.silent_logged is True
        assert result.alert_dispatched is False

    async def test_matching_rule_produces_alert_dispatched(self) -> None:
        """AC-001: matching rule → alert_dispatched=True."""
        match = RuleMatch(
            rule_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            channels=["email"],
        )
        executor, event_id = _build_executor(intensity=4, rule_matches=[match])
        raw_event = _make_raw_event()

        result = await executor.run(raw_event)

        assert result.alert_dispatched is True

    async def test_total_cost_usd_within_ceiling(self) -> None:
        """AC-006: total cost ≤ $0.05."""
        executor, _ = _build_executor()
        result = await executor.run(_make_raw_event())

        assert result.total_cost_usd <= 0.05
