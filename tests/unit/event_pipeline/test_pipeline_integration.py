"""
Integration tests for PipelineExecutor steps 4 and 5 wiring.

Tests verify that:
  - compute_exposure_map is called after classification (step ordering)
  - persist_event_record is called after compute_exposure_map (step ordering)
  - pipeline short-circuits and re-raises when compute_exposure_map raises

Uses pytest-mock / unittest.mock to patch the private step helpers in
PipelineExecutor so no real DB or LLM calls are made.

PLAN-F-003 TASK-006.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.event_pipeline.exceptions import PipelineError
from src.event_pipeline.pipeline_executor import PipelineExecutor


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SAMPLE_EVENT: dict[str, Any] = {
    "id": "evt-001",
    "headline": "Conflict in EMEA",
    "intensity": 3,
    "category": "geopolitical",
    "tickers": ["BP", "SHEL"],
    "geo_regions": ["EMEA"],
    "sectors_affected": ["energy"],
    "sentiment": "negative",
}


def _make_executor() -> PipelineExecutor:
    """Create an executor with no Langfuse client (no observability side effects)."""
    return PipelineExecutor(langfuse_client=None, trace_id="test-trace")


def _patch_all_steps_except(
    executor: PipelineExecutor,
    keep: list[str],
) -> dict[str, AsyncMock]:
    """Patch every private step method on *executor* EXCEPT those in *keep*.

    Returns a dict of method_name → AsyncMock for introspection.
    """
    step_methods = [
        "_persist_raw_event",
        "_classify_event",
        "_extract_tickers",
        "_compute_exposure_map",
        "_persist_event_record",
        "_embed_event",
        "_find_historical_analogies",
        "_generate_alert_text",
        "_evaluate_alert_rules",
        "_dispatch_or_log_silent",
        "_enqueue_deep_dive",
        "_return_pipeline_result",
    ]
    mocks: dict[str, AsyncMock] = {}
    for name in step_methods:
        if name not in keep:
            mock = AsyncMock(return_value={f"{name}_result": True})
            setattr(executor, name, mock)
            mocks[name] = mock
    return mocks


@pytest.mark.asyncio
class TestPipelineStepOrdering:
    """Steps 4 and 5 are called in the correct order relative to step 3."""

    async def test_pipeline_calls_exposure_map_after_classification(self) -> None:
        """_compute_exposure_map is called after _classify_event and _extract_tickers."""
        executor = _make_executor()
        call_order: list[str] = []

        async def track_classify(*args: Any, **kwargs: Any) -> dict:
            call_order.append("classify_event")
            return {"intensity": 3, "category": "geopolitical"}

        async def track_extract(*args: Any, **kwargs: Any) -> list:
            call_order.append("extract_tickers")
            return []

        async def track_exposure(*args: Any, **kwargs: Any) -> dict:
            call_order.append("compute_exposure_map")
            return {}

        executor._persist_raw_event = AsyncMock(return_value={})
        executor._classify_event = AsyncMock(side_effect=track_classify)
        executor._extract_tickers = AsyncMock(side_effect=track_extract)
        executor._compute_exposure_map = AsyncMock(side_effect=track_exposure)
        executor._persist_event_record = AsyncMock(return_value={})
        executor._embed_event = AsyncMock(return_value=[])
        executor._find_historical_analogies = AsyncMock(return_value=[])
        executor._generate_alert_text = AsyncMock(return_value="")
        executor._evaluate_alert_rules = AsyncMock(return_value={"should_alert": False})
        executor._dispatch_or_log_silent = AsyncMock(return_value={})
        executor._enqueue_deep_dive = AsyncMock(return_value={})
        executor._return_pipeline_result = AsyncMock(return_value={})

        await executor.run(_SAMPLE_EVENT)

        classify_idx = call_order.index("classify_event")
        extract_idx = call_order.index("extract_tickers")
        exposure_idx = call_order.index("compute_exposure_map")

        assert classify_idx < exposure_idx, "classify_event must precede compute_exposure_map"
        assert extract_idx < exposure_idx, "extract_tickers must precede compute_exposure_map"

    async def test_pipeline_calls_persist_after_exposure_map(self) -> None:
        """_persist_event_record is called after _compute_exposure_map."""
        executor = _make_executor()
        call_order: list[str] = []

        async def track_exposure(*args: Any, **kwargs: Any) -> dict:
            call_order.append("compute_exposure_map")
            return {}

        async def track_persist(*args: Any, **kwargs: Any) -> dict:
            call_order.append("persist_event_record")
            return {}

        executor._persist_raw_event = AsyncMock(return_value={})
        executor._classify_event = AsyncMock(
            return_value={"intensity": 3, "category": "geopolitical"}
        )
        executor._extract_tickers = AsyncMock(return_value=[])
        executor._compute_exposure_map = AsyncMock(side_effect=track_exposure)
        executor._persist_event_record = AsyncMock(side_effect=track_persist)
        executor._embed_event = AsyncMock(return_value=[])
        executor._find_historical_analogies = AsyncMock(return_value=[])
        executor._generate_alert_text = AsyncMock(return_value="")
        executor._evaluate_alert_rules = AsyncMock(return_value={"should_alert": False})
        executor._dispatch_or_log_silent = AsyncMock(return_value={})
        executor._enqueue_deep_dive = AsyncMock(return_value={})
        executor._return_pipeline_result = AsyncMock(return_value={})

        await executor.run(_SAMPLE_EVENT)

        exposure_idx = call_order.index("compute_exposure_map")
        persist_idx = call_order.index("persist_event_record")

        assert exposure_idx < persist_idx, "compute_exposure_map must precede persist_event_record"


@pytest.mark.asyncio
class TestPipelineShortCircuit:
    """Pipeline propagates exceptions raised by steps 4 and 5."""

    async def test_pipeline_short_circuits_on_exposure_error(self) -> None:
        """If _compute_exposure_map raises PipelineError, run() re-raises it."""
        executor = _make_executor()

        executor._persist_raw_event = AsyncMock(return_value={})
        executor._classify_event = AsyncMock(
            return_value={"intensity": 3, "category": "geopolitical"}
        )
        executor._extract_tickers = AsyncMock(return_value=[])
        executor._compute_exposure_map = AsyncMock(
            side_effect=PipelineError("exposure mapping failed")
        )
        executor._persist_event_record = AsyncMock(return_value={})
        executor._embed_event = AsyncMock(return_value=[])
        executor._find_historical_analogies = AsyncMock(return_value=[])
        executor._generate_alert_text = AsyncMock(return_value="")
        executor._evaluate_alert_rules = AsyncMock(return_value={"should_alert": False})
        executor._dispatch_or_log_silent = AsyncMock(return_value={})
        executor._enqueue_deep_dive = AsyncMock(return_value={})
        executor._return_pipeline_result = AsyncMock(return_value={})

        with pytest.raises(PipelineError, match="exposure mapping failed"):
            await executor.run(_SAMPLE_EVENT)

        # persist_event_record must NOT be called after the error
        executor._persist_event_record.assert_not_called()

    async def test_pipeline_short_circuits_on_persist_error(self) -> None:
        """If _persist_event_record raises PipelineError, run() re-raises it."""
        executor = _make_executor()

        executor._persist_raw_event = AsyncMock(return_value={})
        executor._classify_event = AsyncMock(
            return_value={"intensity": 3, "category": "geopolitical"}
        )
        executor._extract_tickers = AsyncMock(return_value=[])
        executor._compute_exposure_map = AsyncMock(return_value={})
        executor._persist_event_record = AsyncMock(
            side_effect=PipelineError("persist failed")
        )
        executor._embed_event = AsyncMock(return_value=[])
        executor._find_historical_analogies = AsyncMock(return_value=[])
        executor._generate_alert_text = AsyncMock(return_value="")
        executor._evaluate_alert_rules = AsyncMock(return_value={"should_alert": False})
        executor._dispatch_or_log_silent = AsyncMock(return_value={})
        executor._enqueue_deep_dive = AsyncMock(return_value={})
        executor._return_pipeline_result = AsyncMock(return_value={})

        with pytest.raises(PipelineError, match="persist failed"):
            await executor.run(_SAMPLE_EVENT)

        # embed_event must NOT be called after the error
        executor._embed_event.assert_not_called()

    async def test_pipeline_completes_all_12_steps_on_success(self) -> None:
        """When all steps succeed, pipeline result contains all 12 step keys."""
        executor = _make_executor()

        executor._persist_raw_event = AsyncMock(return_value={"status": "ok"})
        executor._classify_event = AsyncMock(
            return_value={"intensity": 3, "category": "geopolitical"}
        )
        executor._extract_tickers = AsyncMock(return_value=["BP"])
        executor._compute_exposure_map = AsyncMock(return_value={"BP": 0.5})
        executor._persist_event_record = AsyncMock(return_value={"status": "stored"})
        executor._embed_event = AsyncMock(return_value=[0.1] * 128)
        executor._find_historical_analogies = AsyncMock(return_value=[])
        executor._generate_alert_text = AsyncMock(return_value="Alert: Conflict in EMEA")
        executor._evaluate_alert_rules = AsyncMock(return_value={"should_alert": True})
        executor._dispatch_or_log_silent = AsyncMock(return_value={"dispatched": True})
        executor._enqueue_deep_dive = AsyncMock(return_value={"enqueued": True})
        executor._return_pipeline_result = AsyncMock(return_value={"status": "completed"})

        result = await executor.run(_SAMPLE_EVENT)

        assert "steps" in result
        assert len(result["steps"]) == 12
