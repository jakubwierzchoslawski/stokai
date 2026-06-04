"""
Unit tests for the generate_alert_text step.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.events.cost_accumulator import CostAccumulator
from src.events.exceptions import StepTimeoutError
from src.events.models import ClassificationResult, ExposureCandidate, PipelineContext, RawEvent
from src.events.steps.generate_alert_text import generate_alert_text


def _make_ctx(
    analogies: list | None = None,
    exposures: list | None = None,
) -> PipelineContext:
    return PipelineContext(
        raw_event=RawEvent(
            source_provider="gdelt",
            occurred_at=datetime(2024, 1, 15, tzinfo=timezone.utc),
            raw_payload={"title": "Oil Sanctions", "summary": "New sanctions on oil"},
        ),
        event_id=uuid.uuid4(),
        classification=ClassificationResult(
            category=["sanctions"],
            intensity=4,
            sentiment="negative",
            geo_regions=["EMEA"],
            affected_sectors=["energy"],
            cameo_code="163",
        ),
        exposures=exposures or [],
        analogies=analogies or [],
        cost_accumulator=CostAccumulator(),
        langfuse_trace_id="trace-001",
    )


@pytest.mark.asyncio
class TestGenerateAlertText:

    async def test_llm_response_stored_verbatim_in_ctx(self) -> None:
        ctx = _make_ctx()
        expected_text = "Energy sector warning: sanctions imposed on EMEA oil supply."
        llm = AsyncMock()
        llm.complete = AsyncMock(return_value=(expected_text, 200, 40))
        tracer = MagicMock()
        tracer.start_span.return_value = "span-001"

        result = await generate_alert_text(ctx, llm, tracer)

        assert result.alert_text == expected_text

    async def test_timeout_raises_step_timeout_error(self) -> None:
        ctx = _make_ctx()
        llm = AsyncMock()
        llm.complete = AsyncMock(side_effect=StepTimeoutError("timeout"))
        tracer = MagicMock()
        tracer.start_span.return_value = "span-001"

        with pytest.raises(StepTimeoutError):
            await generate_alert_text(ctx, llm, tracer)

    async def test_cost_added_to_accumulator(self) -> None:
        ctx = _make_ctx()
        initial_total = ctx.cost_accumulator.total
        llm = AsyncMock()
        llm.complete = AsyncMock(return_value=("Alert text here.", 500, 50))
        tracer = MagicMock()
        tracer.start_span.return_value = "span-001"

        result = await generate_alert_text(ctx, llm, tracer)

        assert result.cost_accumulator.total > initial_total

    async def test_prompt_includes_analogies_when_non_empty(self) -> None:
        analogies = [
            {
                "event_id": uuid.uuid4(),
                "title": "2014 Crimea crisis",
                "occurred_at": datetime(2014, 3, 1, tzinfo=timezone.utc),
                "cosine_distance": 0.12,
            }
        ]
        ctx = _make_ctx(analogies=analogies)
        llm = AsyncMock()
        llm.complete = AsyncMock(return_value=("Alert.", 300, 30))
        tracer = MagicMock()
        tracer.start_span.return_value = "span-001"

        await generate_alert_text(ctx, llm, tracer)

        call_kwargs = llm.complete.call_args
        user_message = call_kwargs[1].get("user_message") or call_kwargs[0][1]
        assert "2014 Crimea crisis" in user_message

    async def test_prompt_omits_analogy_section_when_empty(self) -> None:
        ctx = _make_ctx(analogies=[])
        llm = AsyncMock()
        llm.complete = AsyncMock(return_value=("Alert.", 200, 20))
        tracer = MagicMock()
        tracer.start_span.return_value = "span-001"

        await generate_alert_text(ctx, llm, tracer)

        call_kwargs = llm.complete.call_args
        user_message = call_kwargs[1].get("user_message") or call_kwargs[0][1]
        assert "Historical analogies" not in user_message
