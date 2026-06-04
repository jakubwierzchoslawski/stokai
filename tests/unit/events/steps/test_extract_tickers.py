"""
Unit tests for the extract_tickers step.

All LLM and Langfuse calls are mocked. No real API calls made.
Tests follow TDD: they specify the required behaviour of the implementation.
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
from src.events.models import ClassificationResult, PipelineContext, RawEvent, TickerExtractionResult
from src.events.steps.extract_tickers import extract_tickers

# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------

_PROMPT_CONTENT = "You are a ticker extractor.\n\nEVENT TEXT:\n{{event_text}}"


def _make_ctx(event_text: str = "Apple and Microsoft reported earnings.") -> PipelineContext:
    acc = CostAccumulator()
    classification = ClassificationResult(
        category=["economic_policy"],
        intensity=2,
        sentiment=0.3,
        geo_regions=["North America"],
        affected_sectors=["technology"],
        cameo_code="040",
    )
    return PipelineContext(
        raw_event=RawEvent(
            source_provider="gdelt",
            occurred_at=datetime(2024, 1, 15, tzinfo=timezone.utc),
            raw_payload={"text": event_text},
        ),
        event_id=uuid.uuid4(),
        cost_accumulator=acc,
        langfuse_trace_id="trace-002",
        classification=classification,
    )


def _make_llm(return_json: dict | None = None, side_effect=None) -> AsyncMock:
    llm = AsyncMock()
    if side_effect is not None:
        llm.complete = AsyncMock(side_effect=side_effect)
    else:
        payload = return_json if return_json is not None else {"tickers": ["AAPL", "MSFT"]}
        llm.complete = AsyncMock(return_value=(json.dumps(payload), 60, 20))
    return llm


def _make_tracer(span_id: str = "span-002") -> MagicMock:
    tracer = MagicMock()
    tracer.start_span.return_value = span_id
    return tracer


def _tmp_prompt_path(tmp_path: Path) -> Path:
    p = tmp_path / "ticker_extractor.md"
    p.write_text(_PROMPT_CONTENT, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestExtractTickers:
    """Tests for extract_tickers step."""

    async def test_valid_json_with_tickers_stores_tickers_on_ctx(
        self, tmp_path: Path
    ) -> None:
        """AC-002: Valid LLM JSON with populated tickers → stored on ctx.tickers."""
        ctx = _make_ctx()
        llm = _make_llm(return_json={"tickers": ["AAPL", "MSFT"]})
        tracer = _make_tracer()
        prompt_path = _tmp_prompt_path(tmp_path)

        result = await extract_tickers(ctx, llm, tracer, prompt_path=prompt_path)

        assert result.tickers == ["AAPL", "MSFT"]

    async def test_valid_json_with_empty_tickers_stores_empty_list_no_error(
        self, tmp_path: Path
    ) -> None:
        """AC-003: Empty tickers array → ctx.tickers = [] and no exception raised."""
        ctx = _make_ctx(event_text="The central bank held rates unchanged.")
        llm = _make_llm(return_json={"tickers": []})
        tracer = _make_tracer()
        prompt_path = _tmp_prompt_path(tmp_path)

        result = await extract_tickers(ctx, llm, tracer, prompt_path=prompt_path)

        assert result.tickers == []

    async def test_malformed_json_raises_pipeline_error_without_leaking_raw_output(
        self, tmp_path: Path
    ) -> None:
        """AC-004: Non-JSON LLM response → PipelineError; raw content must not appear in message."""
        raw_garbage = "Sorry, I cannot find any tickers in this text."
        ctx = _make_ctx()
        llm = AsyncMock()
        llm.complete = AsyncMock(return_value=(raw_garbage, 50, 15))
        tracer = _make_tracer()
        prompt_path = _tmp_prompt_path(tmp_path)

        with pytest.raises(PipelineError) as exc_info:
            await extract_tickers(ctx, llm, tracer, prompt_path=prompt_path)

        assert raw_garbage not in str(exc_info.value)

    async def test_step_timeout_propagates_as_step_timeout_error(
        self, tmp_path: Path
    ) -> None:
        """REQ-N-001: StepTimeoutError from llm.complete propagates unchanged."""
        ctx = _make_ctx()
        llm = _make_llm(side_effect=StepTimeoutError("extract_tickers exceeded 3s"))
        tracer = _make_tracer()
        prompt_path = _tmp_prompt_path(tmp_path)

        with pytest.raises(StepTimeoutError):
            await extract_tickers(ctx, llm, tracer, prompt_path=prompt_path)

    async def test_cost_added_to_accumulator_and_ceiling_checked(
        self, tmp_path: Path
    ) -> None:
        """REQ-N-003 / AC-004: Cost is added and check_ceiling(0.05) is called."""
        ctx = _make_ctx()
        original_add = ctx.cost_accumulator.add
        original_check = ctx.cost_accumulator.check_ceiling
        add_calls: list[float] = []
        ceiling_calls: list[float] = []

        def spy_add(cost: float) -> None:
            add_calls.append(cost)
            original_add(cost)

        def spy_check(ceiling: float) -> None:
            ceiling_calls.append(ceiling)
            original_check(ceiling)

        ctx.cost_accumulator.add = spy_add  # type: ignore[method-assign]
        ctx.cost_accumulator.check_ceiling = spy_check  # type: ignore[method-assign]

        llm = _make_llm()
        tracer = _make_tracer()
        prompt_path = _tmp_prompt_path(tmp_path)

        await extract_tickers(ctx, llm, tracer, prompt_path=prompt_path)

        assert len(add_calls) == 1
        assert add_calls[0] > 0
        assert len(ceiling_calls) == 1
        assert ceiling_calls[0] == pytest.approx(0.05)

    async def test_langfuse_start_and_end_span_called_once_with_prompt_version(
        self, tmp_path: Path
    ) -> None:
        """REQ-N-008: start_span and end_span each called once; prompt_version is non-empty SHA."""
        ctx = _make_ctx()
        llm = _make_llm()
        tracer = _make_tracer()
        prompt_path = _tmp_prompt_path(tmp_path)

        await extract_tickers(ctx, llm, tracer, prompt_path=prompt_path)

        tracer.start_span.assert_called_once()
        tracer.end_span.assert_called_once()

        start_call_kwargs = tracer.start_span.call_args
        span_input = start_call_kwargs[1].get("input") or start_call_kwargs[0][2]
        assert "prompt_version" in span_input
        assert len(span_input["prompt_version"]) > 0

    async def test_ticker_extraction_result_validator_rejects_lowercase_ticker(self) -> None:
        """TickerExtractionResult @field_validator must reject non-uppercase ticker."""
        with pytest.raises(Exception):  # Pydantic ValidationError
            TickerExtractionResult(tickers=["aapl"])

    async def test_ticker_extraction_result_validator_rejects_empty_string_ticker(self) -> None:
        """TickerExtractionResult @field_validator must reject empty string."""
        with pytest.raises(Exception):  # Pydantic ValidationError
            TickerExtractionResult(tickers=[""])

    async def test_ticker_extraction_result_accepts_valid_uppercase_tickers(self) -> None:
        """TickerExtractionResult accepts valid uppercase tickers including empty list."""
        result = TickerExtractionResult(tickers=["AAPL", "MSFT", "XOM"])
        assert result.tickers == ["AAPL", "MSFT", "XOM"]

        empty_result = TickerExtractionResult(tickers=[])
        assert empty_result.tickers == []
