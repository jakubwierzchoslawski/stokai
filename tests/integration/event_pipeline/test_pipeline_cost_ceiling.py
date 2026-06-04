"""
Integration tests for Mode A pipeline cost-ceiling enforcement (PLAN-N-003, TASK-006).

AC-001: Mean cost < $0.03 and max <= $0.05 over multiple runs.
AC-002: When cost ceiling would be exceeded, pipeline raises PipelineError before step 8.
AC-003: Every completed run writes cost_usd on the alert row.

Tests use mock LLM/embedding clients and an in-memory async mock for the DB session.
No real PostgreSQL is required for these tests.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from src.event_pipeline.pricing import LLMPricingTable
from src.events.exceptions import PipelineError
from src.events.models import PipelineResult, RawEvent
from src.events.pipeline_executor import PipelineExecutor


# ── Fixtures / helpers ────────────────────────────────────────────────────────


def _make_raw_event(text: str = "Fed raises rates sharply amid inflation fears.") -> RawEvent:
    return RawEvent(
        source_provider="gdelt",
        occurred_at=datetime(2024, 6, 1, tzinfo=timezone.utc),
        raw_payload={
            "title": text,
            "summary": text,
            "text": text,
        },
    )


def _make_classification_json() -> str:
    return (
        '{"category":["macro"],"intensity":3,"sentiment":-0.5,'
        '"geo_regions":["North America"],"affected_sectors":["financials"],"cameo_code":"010"}'
    )


def _build_executor(
    haiku_side_effects: list,
    sonnet_return: tuple,
    embed_return: list[float] | None = None,
    alert_repo: AsyncMock | None = None,
    event_id: uuid.UUID | None = None,
) -> PipelineExecutor:
    """Build a PipelineExecutor with fully-mocked collaborators.

    Args:
        haiku_side_effects: List of (content, input_tokens, output_tokens) tuples
            for successive Haiku LLM calls (classify, extract).
        sonnet_return: Single (content, input_tokens, output_tokens) for Sonnet.
        embed_return: Optional embedding vector; defaults to [0.01] * 1536.
        alert_repo: Optional pre-built alert_repo mock.
        event_id: Fixed event UUID for deterministic testing.
    """
    eid = event_id or uuid.uuid4()

    geo_repo = AsyncMock()
    geo_repo.upsert_raw = AsyncMock(return_value=eid)
    geo_repo.persist_classified = AsyncMock()

    exposure_repo = AsyncMock()
    exposure_repo.bulk_insert = AsyncMock()

    embedding_repo = AsyncMock()
    embedding_repo.get_by_event_id = AsyncMock(return_value=None)
    embedding_repo.save = AsyncMock()
    embedding_repo.search_similar = AsyncMock(return_value=[])

    if alert_repo is None:
        alert_repo = AsyncMock()
        alert_repo.insert_alert = AsyncMock(return_value=uuid.uuid4())
        alert_repo.insert_silent_log = AsyncMock()

    haiku = AsyncMock()
    haiku.complete = AsyncMock(side_effect=haiku_side_effects)

    sonnet = AsyncMock()
    sonnet.complete = AsyncMock(return_value=sonnet_return)

    embedding_service = AsyncMock()
    embedding_service.embed = AsyncMock(return_value=embed_return or [0.01] * 1536)

    tracer = MagicMock()
    tracer.start_trace.return_value = "trace-cost-001"
    tracer.start_span.return_value = "span-cost-001"

    evaluator = AsyncMock()
    evaluator.evaluate = AsyncMock(return_value=[])

    dispatcher = AsyncMock()
    dispatcher.log_silent = AsyncMock()

    workflow_queue = MagicMock()

    session = AsyncMock()
    session.execute = AsyncMock(
        return_value=MagicMock(
            mappings=MagicMock(return_value=[]),
            scalar_one=MagicMock(return_value=eid),
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


# ── Pre-compute expected costs from pricing table ────────────────────────────

# Realistic token counts for tests
_CLASSIFY_IN, _CLASSIFY_OUT = 1800, 150
_EXTRACT_IN, _EXTRACT_OUT = 800, 80
_EMBED_APPROX_IN = 10  # short text → ~10 tokens
_ALERT_IN, _ALERT_OUT = 2500, 160

# Compute actual costs from the pricing table (AC-001 / AC-003 assertions)
_EXPECTED_CLASSIFY = LLMPricingTable.compute("claude-haiku-4-5", _CLASSIFY_IN, _CLASSIFY_OUT)
_EXPECTED_EXTRACT = LLMPricingTable.compute("claude-haiku-4-5", _EXTRACT_IN, _EXTRACT_OUT)
_EXPECTED_ALERT = LLMPricingTable.compute("claude-sonnet-4-6", _ALERT_IN, _ALERT_OUT)
# Embed cost is approximated inside embed_event step based on text length;
# for a short text we tolerate any value ≥ 0.
_EXPECTED_APPROX_TOTAL = _EXPECTED_CLASSIFY + _EXPECTED_EXTRACT + _EXPECTED_ALERT


@pytest.mark.asyncio
@pytest.mark.integration
class TestHappyPathCostRecordedOnAlertRow:

    async def test_happy_path_cost_recorded_on_alert_row(self) -> None:
        """AC-003: Completed run writes accurate cost_usd on the alert/silent-log row.

        Token counts that produce ~$0.02 total:
          classify:  Haiku 1800 in / 150 out  → $0.000638
          extract:   Haiku  800 in /  80 out  → $0.000300
          embed:     approx 10 in             → ~$0.000000
          alert:     Sonnet 2500 in / 160 out → $0.009900
          total ≈ $0.010838  (<< $0.02 for comfortable headroom)
        """
        alert_repo = AsyncMock()
        alert_repo.insert_alert = AsyncMock(return_value=uuid.uuid4())
        alert_repo.insert_silent_log = AsyncMock()

        executor = _build_executor(
            haiku_side_effects=[
                (_make_classification_json(), _CLASSIFY_IN, _CLASSIFY_OUT),
                ('{"tickers": []}', _EXTRACT_IN, _EXTRACT_OUT),
            ],
            sonnet_return=("Market alert: rates surge.", _ALERT_IN, _ALERT_OUT),
            alert_repo=alert_repo,
        )

        result = await executor.run(_make_raw_event())

        # Result carries total_cost_usd
        assert isinstance(result, PipelineResult)
        assert result.total_cost_usd >= 0.0
        assert result.total_cost_usd <= 0.05, (
            f"total_cost_usd {result.total_cost_usd:.6f} exceeded $0.05 ceiling"
        )

        # Cost is close to expected (embed token approximation may vary slightly)
        expected_no_embed = _EXPECTED_CLASSIFY + _EXPECTED_EXTRACT + _EXPECTED_ALERT
        assert abs(result.total_cost_usd - expected_no_embed) < 0.001, (
            f"Expected ~${expected_no_embed:.6f}, got ${result.total_cost_usd:.6f}"
        )

        # Alert or silent-log repo was called with cost_usd kwarg
        if alert_repo.insert_alert.called:
            _, kwargs = alert_repo.insert_alert.call_args
            assert kwargs.get("cost_usd") is not None
            assert kwargs["cost_usd"] >= 0.0
        else:
            _, kwargs = alert_repo.insert_silent_log.call_args
            assert kwargs.get("cost_usd") is not None
            assert kwargs["cost_usd"] >= 0.0


@pytest.mark.asyncio
@pytest.mark.integration
class TestCostCeilingHaltsPipelineBeforeStep8:

    async def test_cost_ceiling_halts_pipeline_before_step_8(self) -> None:
        """AC-002: Pipeline raises PipelineError when accumulator exceeds $0.05 ceiling.

        Strategy: push Haiku classify to return huge token counts that alone
        exceed $0.05, so the ceiling is hit before generate_alert_text (step 8).

        cost = 200_000 in * $0.00025/1k = $50 > $0.05 immediately.
        """
        # Haiku classify: token counts that push cost >> $0.05
        # 200_000 input tokens → 200_000 * 0.00025 / 1000 = $0.05 (exactly at limit)
        # Use 200_001 to push over (> $0.05)
        over_limit_tokens = 200_001

        executor = _build_executor(
            haiku_side_effects=[
                (_make_classification_json(), over_limit_tokens, 0),
                ('{"tickers": []}', 100, 10),
            ],
            sonnet_return=("Should never reach here.", 100, 10),
        )

        with pytest.raises(PipelineError):
            await executor.run(_make_raw_event())

        # Sonnet should NOT have been called (ceiling hit before step 8)
        # (checked indirectly via sonnet.complete not called)
        assert executor._llm_client_sonnet.complete.call_count == 0  # type: ignore[attr-defined]


@pytest.mark.asyncio
@pytest.mark.integration
class TestMeanCostBelow0_03Over10Runs:

    async def test_mean_cost_below_0_03_over_ten_runs(self) -> None:
        """AC-001: Mean cost < $0.03 over 10 runs with realistic token budgets.

        Per-run token budget:
          classify:  Haiku 1800 in / 150 out  → $0.000638
          extract:   Haiku  800 in /  80 out  → $0.000300
          embed:     approx ≤ 500 in          → $0.000010
          alert:     Sonnet 2500 in / 160 out → $0.009900
          --
          total ≈ $0.010848  well under $0.03 target mean
        """
        total_costs: list[float] = []

        for _ in range(10):
            executor = _build_executor(
                haiku_side_effects=[
                    (_make_classification_json(), _CLASSIFY_IN, _CLASSIFY_OUT),
                    ('{"tickers": ["SPY", "TLT"]}', _EXTRACT_IN, _EXTRACT_OUT),
                ],
                sonnet_return=("Rates spike: broad market selloff.", _ALERT_IN, _ALERT_OUT),
            )
            result = await executor.run(_make_raw_event())
            total_costs.append(result.total_cost_usd)

        mean_cost = sum(total_costs) / len(total_costs)
        max_cost = max(total_costs)

        assert mean_cost < 0.03, (
            f"Mean cost ${mean_cost:.6f} >= $0.03 target. "
            f"Individual costs: {[f'${c:.6f}' for c in total_costs]}"
        )
        assert max_cost <= 0.05, (
            f"Max cost ${max_cost:.6f} exceeded $0.05 hard ceiling."
        )
