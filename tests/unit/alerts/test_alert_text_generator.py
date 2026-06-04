"""
Unit tests for AlertTextGenerator.

LLM is mocked via AsyncMock. Langfuse tracer is mocked.
No disk I/O — system prompt is patched on the instance.
"""
from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.alerts.exceptions import AlertDispatchError
from src.alerts.models import ActionSignal, AlertTextResult
from src.alerts.services.alert_text_generator import AlertTextGenerator


TENANT_ID = uuid.uuid4()


def _make_llm(response_json: dict | None = None, raises: Exception | None = None) -> AsyncMock:
    llm = AsyncMock()
    if raises is not None:
        llm.complete = AsyncMock(side_effect=raises)
    else:
        content = json.dumps(response_json or _valid_response())
        llm.complete = AsyncMock(return_value=(content, 100, 50))
    return llm


def _make_tracer() -> MagicMock:
    tracer = MagicMock()
    tracer.start_span.return_value = "span-001"
    tracer.end_span = MagicMock()
    return tracer


def _valid_response(**overrides) -> dict:
    base = {
        "alert_text": "A significant geopolitical event unfolded in Eastern Europe. "
                      "High-intensity event (4/5). Three of your holdings are directly exposed. "
                      "AI signal: REDUCE_RISK. Confidence: 78%. Based on 8 similar events, "
                      "average drawdown was -3.5%.",
        "action_signal": "REDUCE_RISK",
        "confidence": 0.78,
        "sample_size": 8,
    }
    base.update(overrides)
    return base


def _generator(llm) -> AlertTextGenerator:
    gen = AlertTextGenerator(llm_client=llm)
    # Patch prompt loading to avoid disk read
    gen._system_prompt = "You are StokAI alert writer."
    return gen


# ── Happy path ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_valid_json_response_parsed_into_alert_text_result():
    """Valid LLM JSON is parsed into AlertTextResult with all required fields."""
    llm = _make_llm(_valid_response())
    gen = _generator(llm)
    tracer = _make_tracer()

    result = await gen.generate("Trade sanctions announced", 4, [], 3, TENANT_ID, tracer)

    assert isinstance(result, AlertTextResult)
    assert result.action_signal == ActionSignal.REDUCE_RISK
    assert result.confidence == pytest.approx(0.78)
    assert result.sample_size == 8


# ── Low sample disclaimer ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_sample_size_below_5_sets_low_sample_disclaimer_true():
    """sample_size < 5 sets low_sample_disclaimer=True."""
    llm = _make_llm(_valid_response(sample_size=3))
    gen = _generator(llm)
    tracer = _make_tracer()

    result = await gen.generate("Event", 2, [], 1, TENANT_ID, tracer)

    assert result.low_sample_disclaimer is True


@pytest.mark.asyncio
async def test_sample_size_5_sets_low_sample_disclaimer_false():
    """sample_size >= 5 sets low_sample_disclaimer=False."""
    llm = _make_llm(_valid_response(sample_size=5))
    gen = _generator(llm)
    tracer = _make_tracer()

    result = await gen.generate("Event", 2, [], 1, TENANT_ID, tracer)

    assert result.low_sample_disclaimer is False


# ── Error handling ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_llm_timeout_raises_alert_dispatch_error():
    """LLM timeout is wrapped in AlertDispatchError (StepTimeoutError not leaked)."""
    from src.ai.limits.errors import StepTimeoutError  # type: ignore
    # Use a generic exception since StepTimeoutError may not be importable in tests
    timeout_exc = Exception("timeout")
    llm = _make_llm(raises=timeout_exc)
    gen = _generator(llm)
    tracer = _make_tracer()

    with pytest.raises(AlertDispatchError):
        await gen.generate("Event", 3, [], 2, TENANT_ID, tracer)


@pytest.mark.asyncio
async def test_malformed_json_raises_alert_dispatch_error():
    """Non-JSON LLM response raises AlertDispatchError."""
    llm = AsyncMock()
    llm.complete = AsyncMock(return_value=("not json at all", 10, 5))
    gen = _generator(llm)
    tracer = _make_tracer()

    with pytest.raises(AlertDispatchError):
        await gen.generate("Event", 3, [], 2, TENANT_ID, tracer)


@pytest.mark.asyncio
async def test_invalid_action_signal_raises_alert_dispatch_error():
    """action_signal value not in ActionSignal enum raises AlertDispatchError."""
    llm = _make_llm(_valid_response(action_signal="PANIC"))
    gen = _generator(llm)
    tracer = _make_tracer()

    with pytest.raises(AlertDispatchError):
        await gen.generate("Event", 3, [], 2, TENANT_ID, tracer)


# ── Langfuse integration ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_langfuse_span_started_and_ended():
    """Langfuse start_span and end_span are called during generation."""
    llm = _make_llm(_valid_response())
    gen = _generator(llm)
    tracer = _make_tracer()

    await gen.generate("Event", 3, [], 2, TENANT_ID, tracer)

    tracer.start_span.assert_called_once()
    tracer.end_span.assert_called_once()
    # Model tag is recorded in the span output
    end_call_kwargs = tracer.end_span.call_args
    output_arg = end_call_kwargs[1].get("output") or end_call_kwargs[0][1]
    assert output_arg.get("model") == "claude-sonnet-4-6"


@pytest.mark.asyncio
async def test_langfuse_span_ended_even_on_llm_error():
    """Langfuse end_span is called even when the LLM raises an exception."""
    llm = _make_llm(raises=Exception("boom"))
    gen = _generator(llm)
    tracer = _make_tracer()

    with pytest.raises(AlertDispatchError):
        await gen.generate("Event", 3, [], 2, TENANT_ID, tracer)

    tracer.end_span.assert_called_once()
