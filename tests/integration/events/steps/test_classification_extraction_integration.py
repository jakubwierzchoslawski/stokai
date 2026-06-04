"""
Integration tests — classify_event and extract_tickers run sequentially.

Uses mocked ILLMClient and ILangfuseTracer (via unittest.mock). No real API
calls. No database dependency. Exercises both steps on the same PipelineContext
and verifies that shared state (cost accumulator, tickers, classification) is
correctly threaded through.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.events.cost_accumulator import CostAccumulator
from src.events.exceptions import PipelineError, StepTimeoutError
from src.events.models import ClassificationResult, PipelineContext, RawEvent
from src.events.steps.classify_event import classify_event
from src.events.steps.extract_tickers import extract_tickers

# ---------------------------------------------------------------------------
# Shared prompt fixtures written to tmp_path per test
# ---------------------------------------------------------------------------

_CLASSIFIER_PROMPT = "System: classify.\n\nEVENT TEXT:\n{{event_text}}"
_EXTRACTOR_PROMPT = "System: extract tickers.\n\nEVENT TEXT:\n{{event_text}}"

_VALID_CLASSIFICATION = {
    "category": ["sanctions", "trade"],
    "intensity": 3,
    "sentiment": -0.5,
    "geo_regions": ["North America", "APAC"],
    "affected_sectors": ["technology", "industrials"],
    "cameo_code": "163",
}
_VALID_TICKERS = {"tickers": ["AAPL", "INTC", "NVDA"]}
_EMPTY_TICKERS = {"tickers": []}


def _make_ctx(event_text: str = "US imposed semiconductor export controls on China.") -> PipelineContext:
    acc = CostAccumulator()
    return PipelineContext(
        raw_event=RawEvent(
            source_provider="gdelt",
            occurred_at=datetime(2024, 3, 1, tzinfo=timezone.utc),
            raw_payload={"text": event_text},
        ),
        event_id=uuid.uuid4(),
        cost_accumulator=acc,
        langfuse_trace_id="trace-integration-001",
    )


def _make_prompts(tmp_path: Path) -> tuple[Path, Path]:
    classifier_path = tmp_path / "event_classifier.md"
    extractor_path = tmp_path / "ticker_extractor.md"
    classifier_path.write_text(_CLASSIFIER_PROMPT, encoding="utf-8")
    extractor_path.write_text(_EXTRACTOR_PROMPT, encoding="utf-8")
    return classifier_path, extractor_path


def _make_tracer() -> MagicMock:
    tracer = MagicMock()
    tracer.start_span.side_effect = lambda trace_id, name, input: f"span-{name}"
    return tracer


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestClassificationExtractionIntegration:
    """Integration tests: classify_event → extract_tickers on same PipelineContext."""

    async def test_both_steps_run_sequentially_classification_populated_before_extraction(
        self, tmp_path: Path
    ) -> None:
        """Both steps share one PipelineContext; classification is set before extraction runs."""
        ctx = _make_ctx()
        classifier_path, extractor_path = _make_prompts(tmp_path)

        classify_llm = AsyncMock()
        classify_llm.complete = AsyncMock(
            return_value=(json.dumps(_VALID_CLASSIFICATION), 100, 50)
        )
        extract_llm = AsyncMock()
        extract_llm.complete = AsyncMock(
            return_value=(json.dumps(_VALID_TICKERS), 60, 20)
        )
        tracer = _make_tracer()

        ctx = await classify_event(ctx, classify_llm, tracer, prompt_path=classifier_path)
        assert ctx.classification is not None  # populated before extraction
        ctx = await extract_tickers(ctx, extract_llm, tracer, prompt_path=extractor_path)

        assert ctx.classification is not None
        assert ctx.tickers == ["AAPL", "INTC", "NVDA"]

    async def test_after_both_steps_ctx_has_valid_classification_and_tickers(
        self, tmp_path: Path
    ) -> None:
        """AC-001 + AC-002: After both steps, ctx.classification is ClassificationResult and ctx.tickers is list[str]."""
        ctx = _make_ctx()
        classifier_path, extractor_path = _make_prompts(tmp_path)

        classify_llm = AsyncMock()
        classify_llm.complete = AsyncMock(
            return_value=(json.dumps(_VALID_CLASSIFICATION), 100, 50)
        )
        extract_llm = AsyncMock()
        extract_llm.complete = AsyncMock(
            return_value=(json.dumps(_VALID_TICKERS), 60, 20)
        )
        tracer = _make_tracer()

        ctx = await classify_event(ctx, classify_llm, tracer, prompt_path=classifier_path)
        ctx = await extract_tickers(ctx, extract_llm, tracer, prompt_path=extractor_path)

        assert isinstance(ctx.classification, ClassificationResult)
        assert isinstance(ctx.tickers, list)
        assert all(isinstance(t, str) for t in ctx.tickers)

    async def test_cost_accumulator_reflects_combined_cost_of_both_llm_calls(
        self, tmp_path: Path
    ) -> None:
        """AC-004: ctx.cost_accumulator reflects cost from both classify_event and extract_tickers."""
        ctx = _make_ctx()
        classifier_path, extractor_path = _make_prompts(tmp_path)

        # classify_event: 100 in, 50 out
        # extract_tickers: 60 in, 20 out
        classify_llm = AsyncMock()
        classify_llm.complete = AsyncMock(
            return_value=(json.dumps(_VALID_CLASSIFICATION), 100, 50)
        )
        extract_llm = AsyncMock()
        extract_llm.complete = AsyncMock(
            return_value=(json.dumps(_VALID_TICKERS), 60, 20)
        )
        tracer = _make_tracer()

        ctx = await classify_event(ctx, classify_llm, tracer, prompt_path=classifier_path)
        after_classify_cost = ctx.cost_accumulator.total
        ctx = await extract_tickers(ctx, extract_llm, tracer, prompt_path=extractor_path)
        after_extract_cost = ctx.cost_accumulator.total

        assert after_classify_cost > 0
        assert after_extract_cost > after_classify_cost

    async def test_classification_timeout_raises_error_before_extract_tickers_invoked(
        self, tmp_path: Path
    ) -> None:
        """AC-004: When classify_event times out, PipelineError propagates; extract_tickers not called."""
        ctx = _make_ctx()
        classifier_path, extractor_path = _make_prompts(tmp_path)

        classify_llm = AsyncMock()
        classify_llm.complete = AsyncMock(
            side_effect=StepTimeoutError("classify_event exceeded 5s")
        )
        extract_llm = AsyncMock()
        tracer = _make_tracer()

        with pytest.raises(StepTimeoutError):
            ctx = await classify_event(ctx, classify_llm, tracer, prompt_path=classifier_path)

        # extract_tickers never invoked because we stopped at classify_event
        extract_llm.complete.assert_not_called()

    async def test_extraction_with_empty_tickers_carries_empty_list_no_exception(
        self, tmp_path: Path
    ) -> None:
        """AC-003: Empty tickers from extract_tickers → ctx.tickers = []; pipeline can continue."""
        ctx = _make_ctx(event_text="The European Central Bank held rates unchanged.")
        classifier_path, extractor_path = _make_prompts(tmp_path)

        classify_llm = AsyncMock()
        classify_llm.complete = AsyncMock(
            return_value=(json.dumps(_VALID_CLASSIFICATION), 80, 40)
        )
        extract_llm = AsyncMock()
        extract_llm.complete = AsyncMock(
            return_value=(json.dumps(_EMPTY_TICKERS), 50, 10)
        )
        tracer = _make_tracer()

        ctx = await classify_event(ctx, classify_llm, tracer, prompt_path=classifier_path)
        ctx = await extract_tickers(ctx, extract_llm, tracer, prompt_path=extractor_path)

        assert ctx.tickers == []
        assert ctx.classification is not None  # pipeline can continue

    async def test_langfuse_spans_created_and_closed_with_non_empty_sha_for_both_steps(
        self, tmp_path: Path
    ) -> None:
        """REQ-N-008: Both steps create and close spans with prompt_version set to non-empty SHA."""
        ctx = _make_ctx()
        classifier_path, extractor_path = _make_prompts(tmp_path)

        classify_llm = AsyncMock()
        classify_llm.complete = AsyncMock(
            return_value=(json.dumps(_VALID_CLASSIFICATION), 100, 50)
        )
        extract_llm = AsyncMock()
        extract_llm.complete = AsyncMock(
            return_value=(json.dumps(_VALID_TICKERS), 60, 20)
        )
        tracer = _make_tracer()

        await classify_event(ctx, classify_llm, tracer, prompt_path=classifier_path)
        await extract_tickers(ctx, extract_llm, tracer, prompt_path=extractor_path)

        # Both steps must have called start_span and end_span
        assert tracer.start_span.call_count == 2
        assert tracer.end_span.call_count == 2

        # Each start_span call must include prompt_version (non-empty SHA)
        for call in tracer.start_span.call_args_list:
            span_input = call[1].get("input") or call[0][2]
            assert "prompt_version" in span_input
            assert len(span_input["prompt_version"]) > 0
