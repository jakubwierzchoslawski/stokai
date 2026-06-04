"""
Unit tests for the classify_event step.

All LLM and Langfuse calls are mocked. No real API calls made.
Tests follow TDD: they specify the required behaviour of the implementation.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.events.cost_accumulator import CostAccumulator
from src.events.exceptions import PipelineError, StepTimeoutError
from src.events.models import PipelineContext, RawEvent
from src.events.steps.classify_event import classify_event

# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------

_VALID_CLASSIFICATION = {
    "category": ["conflict", "sanctions"],
    "intensity": 4,
    "sentiment": -0.8,
    "geo_regions": ["EMEA"],
    "affected_sectors": ["energy"],
    "cameo_code": "190",
}

_PROMPT_CONTENT = "You are a classifier.\n\nEVENT TEXT:\n{{event_text}}"


def _make_ctx(event_text: str = "Oil refinery fire in Gulf region.") -> PipelineContext:
    acc = CostAccumulator()
    return PipelineContext(
        raw_event=RawEvent(
            source_provider="gdelt",
            occurred_at=datetime(2024, 1, 15, tzinfo=timezone.utc),
            raw_payload={"text": event_text},
        ),
        event_id=uuid.uuid4(),
        cost_accumulator=acc,
        langfuse_trace_id="trace-001",
    )


def _make_llm(return_json: dict | None = None, side_effect=None) -> AsyncMock:
    llm = AsyncMock()
    if side_effect is not None:
        llm.complete = AsyncMock(side_effect=side_effect)
    else:
        content = json.dumps(return_json or _VALID_CLASSIFICATION)
        llm.complete = AsyncMock(return_value=(content, 80, 40))
    return llm


def _make_tracer(span_id: str = "span-001") -> MagicMock:
    tracer = MagicMock()
    tracer.start_span.return_value = span_id
    return tracer


def _tmp_prompt_path(tmp_path: Path) -> Path:
    p = tmp_path / "event_classifier.md"
    p.write_text(_PROMPT_CONTENT, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestClassifyEvent:
    """Tests for classify_event step."""

    async def test_valid_json_produces_classification_result_on_ctx(
        self, tmp_path: Path
    ) -> None:
        """AC-001: Valid 6-field LLM JSON → ClassificationResult stored on ctx.classification."""
        ctx = _make_ctx()
        llm = _make_llm()
        tracer = _make_tracer()
        prompt_path = _tmp_prompt_path(tmp_path)

        result = await classify_event(ctx, llm, tracer, prompt_path=prompt_path)

        assert result.classification is not None
        assert result.classification.intensity == 4
        assert result.classification.sentiment == -0.8
        assert "energy" in result.classification.affected_sectors
        assert result.classification.cameo_code == "190"
        assert "conflict" in result.classification.category

    async def test_intensity_outside_range_raises_pipeline_error(
        self, tmp_path: Path
    ) -> None:
        """AC-001: intensity = 6 (out of [1,5]) must raise PipelineError via Pydantic."""
        bad = {**_VALID_CLASSIFICATION, "intensity": 6}
        ctx = _make_ctx()
        llm = _make_llm(return_json=bad)
        tracer = _make_tracer()
        prompt_path = _tmp_prompt_path(tmp_path)

        with pytest.raises(PipelineError):
            await classify_event(ctx, llm, tracer, prompt_path=prompt_path)

    async def test_sentiment_outside_range_raises_pipeline_error(
        self, tmp_path: Path
    ) -> None:
        """AC-001: sentiment = 1.5 (out of [-1.0, 1.0]) must raise PipelineError."""
        bad = {**_VALID_CLASSIFICATION, "sentiment": 1.5}
        ctx = _make_ctx()
        llm = _make_llm(return_json=bad)
        tracer = _make_tracer()
        prompt_path = _tmp_prompt_path(tmp_path)

        with pytest.raises(PipelineError):
            await classify_event(ctx, llm, tracer, prompt_path=prompt_path)

    async def test_malformed_json_raises_pipeline_error_without_leaking_raw_output(
        self, tmp_path: Path
    ) -> None:
        """AC-004: Non-JSON LLM response → PipelineError; raw content must not appear in message."""
        raw_garbage = "I cannot classify this event, sorry."
        ctx = _make_ctx()
        llm = AsyncMock()
        llm.complete = AsyncMock(return_value=(raw_garbage, 50, 20))
        tracer = _make_tracer()
        prompt_path = _tmp_prompt_path(tmp_path)

        with pytest.raises(PipelineError) as exc_info:
            await classify_event(ctx, llm, tracer, prompt_path=prompt_path)

        assert raw_garbage not in str(exc_info.value)

    async def test_step_timeout_propagates_as_step_timeout_error(
        self, tmp_path: Path
    ) -> None:
        """REQ-N-001: StepTimeoutError from llm.complete propagates unchanged."""
        ctx = _make_ctx()
        llm = _make_llm(side_effect=StepTimeoutError("classify_event exceeded 5s"))
        tracer = _make_tracer()
        prompt_path = _tmp_prompt_path(tmp_path)

        with pytest.raises(StepTimeoutError):
            await classify_event(ctx, llm, tracer, prompt_path=prompt_path)

    async def test_cost_added_to_accumulator_and_ceiling_checked(
        self, tmp_path: Path
    ) -> None:
        """REQ-N-003 / AC-004: Cost is added and check_ceiling(0.05) is called."""
        ctx = _make_ctx()
        # Spy on cost_accumulator
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

        await classify_event(ctx, llm, tracer, prompt_path=prompt_path)

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

        await classify_event(ctx, llm, tracer, prompt_path=prompt_path)

        tracer.start_span.assert_called_once()
        tracer.end_span.assert_called_once()

        # prompt_version must be present and non-empty in the start_span input
        start_call_kwargs = tracer.start_span.call_args
        span_input = start_call_kwargs[1].get("input") or start_call_kwargs[0][2]
        assert "prompt_version" in span_input
        assert len(span_input["prompt_version"]) > 0

    async def test_empty_event_text_raises_pipeline_error_before_llm_call(
        self, tmp_path: Path
    ) -> None:
        """AC-004: Empty event text raises PipelineError; LLM must not be called."""
        ctx = _make_ctx(event_text="")
        llm = _make_llm()
        tracer = _make_tracer()
        prompt_path = _tmp_prompt_path(tmp_path)

        with pytest.raises(PipelineError, match="empty event text"):
            await classify_event(ctx, llm, tracer, prompt_path=prompt_path)

        llm.complete.assert_not_called()
