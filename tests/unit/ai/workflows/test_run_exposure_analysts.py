"""
Unit tests for run_exposure_analysts DeterministicNode (PLAN-F-010 TASK-006).

TDD: written before implementation.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.ai.workflows.event_deep_dive.state import (
    DeepDiveWorkflowState,
    GeoEvent,
    WorkflowState,
)
from src.ai.workflows.state import WorkflowType, WorkflowStatus


def _make_state(exposures: list[dict] | None = None, **kwargs) -> DeepDiveWorkflowState:
    event_id = uuid.uuid4()
    geo = GeoEvent(
        event_id=event_id,
        exposures=exposures or [],
    )
    defaults = {
        "workflow_id": uuid.uuid4(),
        "workflow_type": WorkflowType.EVENT_DEEP_DIVE,
        "tenant_id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "company_id": uuid.uuid4(),
        "started_at": datetime.now(tz=timezone.utc),
        "status": WorkflowStatus.RUNNING,
        "inputs": {"event_id": str(event_id)},
        "event_full": geo,
    }
    defaults.update(kwargs)
    return DeepDiveWorkflowState(**defaults)


def _make_registry(mock_result: dict | None = None) -> MagicMock:
    defn = MagicMock()
    defn.role_id = "exposure-analyst"
    defn.limits = MagicMock()
    defn.limits.cost_ceiling_usd = 5.0

    registry = MagicMock()
    registry.resolve.return_value = defn
    return registry


async def _fake_analyst_call(company_id, **kwargs):
    return {
        "company_id": str(company_id),
        "exposure_type": "direct",
        "direction": "negative",
        "magnitude": 0.7,
        "reasoning": "test",
        "confidence": 0.8,
        "cost_usd": 0.05,
    }


class TestRunExposureAnalysts:
    @pytest.mark.asyncio
    async def test_fan_out_produces_one_analysis_per_company(self):
        """One ExposureAnalysis per company in event_full.exposures."""
        from src.ai.workflows.event_deep_dive.nodes.run_exposure_analysts import (
            run_exposure_analysts,
        )
        from src.ai.workflows.event_deep_dive.cost_accumulator import CostAccumulator

        cid1, cid2 = uuid.uuid4(), uuid.uuid4()
        state = _make_state(
            exposures=[
                {"company_id": str(cid1), "exposure_type": "direct"},
                {"company_id": str(cid2), "exposure_type": "sector"},
            ]
        )
        registry = _make_registry()
        accumulator = CostAccumulator(ceiling_usd=10.0)

        with patch(
            "src.ai.workflows.event_deep_dive.nodes.run_exposure_analysts._invoke_analyst",
            side_effect=_fake_analyst_call,
        ):
            result = await run_exposure_analysts(
                state, registry=registry, cost_accumulator=accumulator
            )

        assert len(result.exposure_analyses) == 2

    @pytest.mark.asyncio
    async def test_fan_out_with_empty_exposures_returns_empty_list(self):
        """Empty exposure list → empty exposure_analyses (not an error)."""
        from src.ai.workflows.event_deep_dive.nodes.run_exposure_analysts import (
            run_exposure_analysts,
        )
        from src.ai.workflows.event_deep_dive.cost_accumulator import CostAccumulator

        state = _make_state(exposures=[])
        registry = _make_registry()
        accumulator = CostAccumulator(ceiling_usd=10.0)

        result = await run_exposure_analysts(
            state, registry=registry, cost_accumulator=accumulator
        )

        assert result.exposure_analyses == []

    @pytest.mark.asyncio
    async def test_fan_out_propagates_cost_ceiling_exceeded(self):
        """CostCeilingExceededError from accumulator propagates out of the node."""
        from src.ai.workflows.event_deep_dive.nodes.run_exposure_analysts import (
            run_exposure_analysts,
        )
        from src.ai.workflows.event_deep_dive.cost_accumulator import CostAccumulator
        from src.ai.workflows.event_deep_dive.exceptions import CostCeilingExceededError

        cid = uuid.uuid4()
        state = _make_state(
            exposures=[{"company_id": str(cid), "exposure_type": "direct"}]
        )
        registry = _make_registry()
        # Very low ceiling — first add will fail
        accumulator = CostAccumulator(ceiling_usd=0.001)

        with patch(
            "src.ai.workflows.event_deep_dive.nodes.run_exposure_analysts._invoke_analyst",
            side_effect=_fake_analyst_call,
        ):
            with pytest.raises(CostCeilingExceededError):
                await run_exposure_analysts(
                    state, registry=registry, cost_accumulator=accumulator
                )

    @pytest.mark.asyncio
    async def test_each_coroutine_receives_sibling_span_context(self):
        """Each analyst invocation receives parent_trace_id for Langfuse sibling spans."""
        from src.ai.workflows.event_deep_dive.nodes.run_exposure_analysts import (
            run_exposure_analysts,
        )
        from src.ai.workflows.event_deep_dive.cost_accumulator import CostAccumulator

        cid1, cid2 = uuid.uuid4(), uuid.uuid4()
        state = _make_state(
            exposures=[
                {"company_id": str(cid1), "exposure_type": "direct"},
                {"company_id": str(cid2), "exposure_type": "sector"},
            ],
            langfuse_trace_id="trace-abc-123",
        )
        registry = _make_registry()
        accumulator = CostAccumulator(ceiling_usd=10.0)

        captured_kwargs = []

        async def capturing_analyst(company_id, **kwargs):
            captured_kwargs.append(kwargs)
            return await _fake_analyst_call(company_id, **kwargs)

        with patch(
            "src.ai.workflows.event_deep_dive.nodes.run_exposure_analysts._invoke_analyst",
            side_effect=capturing_analyst,
        ):
            await run_exposure_analysts(
                state, registry=registry, cost_accumulator=accumulator
            )

        # Each invocation should have received parent_trace_id
        assert len(captured_kwargs) == 2
        for kwargs in captured_kwargs:
            assert "parent_trace_id" in kwargs
            assert kwargs["parent_trace_id"] == "trace-abc-123"
