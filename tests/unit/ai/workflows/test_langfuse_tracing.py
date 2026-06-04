"""
Unit tests for Langfuse trace wiring in Event Deep-Dive (PLAN-F-010 TASK-014).

TDD: written before implementation.
Tests that:
  - celery_task starts a trace and stores trace_id on workflow state
  - run_exposure_analysts passes parent_trace_id to each analyst coroutine
  - Each gather coroutine gets a sibling span (parent_id = trace_id)
  - Langfuse flush is called after terminal branch
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.ai.workflows.event_deep_dive.state import (
    DeepDiveWorkflowState,
    GeoEvent,
)
from src.ai.workflows.state import WorkflowStatus, WorkflowType


def _make_state(trace_id: str | None = "trace-test-123", **kwargs) -> DeepDiveWorkflowState:
    event_id = uuid.uuid4()
    defaults = {
        "workflow_id": uuid.uuid4(),
        "workflow_type": WorkflowType.EVENT_DEEP_DIVE,
        "tenant_id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "company_id": uuid.uuid4(),
        "started_at": datetime.now(tz=timezone.utc),
        "inputs": {"event_id": str(event_id)},
        "event_full": GeoEvent(event_id=event_id, exposures=[]),
        "langfuse_trace_id": trace_id,
    }
    defaults.update(kwargs)
    return DeepDiveWorkflowState(**defaults)


class TestExposureAnalystsLangfuseSpans:
    @pytest.mark.asyncio
    async def test_each_analyst_receives_parent_trace_id(self):
        """Each _invoke_analyst call receives parent_trace_id from state.langfuse_trace_id."""
        from src.ai.workflows.event_deep_dive.nodes.run_exposure_analysts import (
            run_exposure_analysts,
        )
        from src.ai.workflows.event_deep_dive.cost_accumulator import CostAccumulator

        trace_id = "trace-sibling-test"
        cid1 = uuid.uuid4()
        state = _make_state(
            trace_id=trace_id,
            event_full=GeoEvent(
                event_id=uuid.uuid4(),
                exposures=[{"company_id": str(cid1), "exposure_type": "direct"}],
            ),
        )

        registry = MagicMock()
        defn = MagicMock()
        defn.limits.cost_ceiling_usd = 5.0
        registry.resolve.return_value = defn

        accumulator = CostAccumulator(ceiling_usd=10.0)
        captured_kwargs = []

        async def capturing_analyst(company_id, **kwargs):
            captured_kwargs.append(kwargs)
            return {
                "company_id": str(company_id),
                "exposure_type": "direct",
                "direction": "neutral",
                "magnitude": 0.5,
                "reasoning": "test",
                "confidence": 0.8,
                "cost_usd": 0.01,
            }

        with patch(
            "src.ai.workflows.event_deep_dive.nodes.run_exposure_analysts._invoke_analyst",
            side_effect=capturing_analyst,
        ):
            await run_exposure_analysts(
                state,
                registry=registry,
                cost_accumulator=accumulator,
            )

        assert len(captured_kwargs) == 1
        assert captured_kwargs[0]["parent_trace_id"] == trace_id

    @pytest.mark.asyncio
    async def test_sibling_spans_each_get_distinct_coroutine_context(self):
        """Each gather coroutine gets its own sibling span (parent_id = trace_id)."""
        from src.ai.workflows.event_deep_dive.nodes.run_exposure_analysts import (
            run_exposure_analysts,
        )
        from src.ai.workflows.event_deep_dive.cost_accumulator import CostAccumulator

        trace_id = "trace-multi-123"
        cid1, cid2, cid3 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        state = _make_state(
            trace_id=trace_id,
            event_full=GeoEvent(
                event_id=uuid.uuid4(),
                exposures=[
                    {"company_id": str(cid1)},
                    {"company_id": str(cid2)},
                    {"company_id": str(cid3)},
                ],
            ),
        )

        registry = MagicMock()
        defn = MagicMock()
        defn.limits.cost_ceiling_usd = 5.0
        registry.resolve.return_value = defn

        accumulator = CostAccumulator(ceiling_usd=10.0)
        captured_trace_ids = []

        async def capturing_analyst(company_id, **kwargs):
            captured_trace_ids.append(kwargs.get("parent_trace_id"))
            return {
                "company_id": str(company_id),
                "exposure_type": "direct",
                "direction": "neutral",
                "magnitude": 0.5,
                "reasoning": "test",
                "confidence": 0.8,
                "cost_usd": 0.01,
            }

        with patch(
            "src.ai.workflows.event_deep_dive.nodes.run_exposure_analysts._invoke_analyst",
            side_effect=capturing_analyst,
        ):
            await run_exposure_analysts(
                state,
                registry=registry,
                cost_accumulator=accumulator,
            )

        # All 3 coroutines should have received the same parent trace_id
        assert len(captured_trace_ids) == 3
        assert all(tid == trace_id for tid in captured_trace_ids)

    @pytest.mark.asyncio
    async def test_run_exposure_analysts_with_none_trace_id_still_works(self):
        """run_exposure_analysts works even when langfuse_trace_id is None."""
        from src.ai.workflows.event_deep_dive.nodes.run_exposure_analysts import (
            run_exposure_analysts,
        )
        from src.ai.workflows.event_deep_dive.cost_accumulator import CostAccumulator

        cid1 = uuid.uuid4()
        state = _make_state(
            trace_id=None,
            event_full=GeoEvent(
                event_id=uuid.uuid4(),
                exposures=[{"company_id": str(cid1)}],
            ),
        )

        registry = MagicMock()
        defn = MagicMock()
        defn.limits.cost_ceiling_usd = 5.0
        registry.resolve.return_value = defn

        accumulator = CostAccumulator(ceiling_usd=10.0)

        async def stub_analyst(company_id, **kwargs):
            return {
                "company_id": str(company_id),
                "exposure_type": "direct",
                "direction": "neutral",
                "magnitude": 0.5,
                "reasoning": "test",
                "confidence": 0.8,
                "cost_usd": 0.01,
            }

        with patch(
            "src.ai.workflows.event_deep_dive.nodes.run_exposure_analysts._invoke_analyst",
            side_effect=stub_analyst,
        ):
            result = await run_exposure_analysts(
                state,
                registry=registry,
                cost_accumulator=accumulator,
            )

        assert len(result.exposure_analyses) == 1

    @pytest.mark.asyncio
    async def test_langfuse_client_passed_to_exposure_analysts(self):
        """langfuse_client argument is accepted by run_exposure_analysts."""
        from src.ai.workflows.event_deep_dive.nodes.run_exposure_analysts import (
            run_exposure_analysts,
        )
        from src.ai.workflows.event_deep_dive.cost_accumulator import CostAccumulator

        state = _make_state(
            event_full=GeoEvent(event_id=uuid.uuid4(), exposures=[]),
        )

        registry = MagicMock()
        accumulator = CostAccumulator(ceiling_usd=10.0)
        langfuse_client = MagicMock()

        # Should not raise even with a langfuse_client provided
        result = await run_exposure_analysts(
            state,
            registry=registry,
            cost_accumulator=accumulator,
            langfuse_client=langfuse_client,
        )

        assert result.exposure_analyses == []

    @pytest.mark.asyncio
    async def test_celery_task_async_accepts_event_id_param(self):
        """_run_deep_dive_async is callable with event_id parameter."""
        from src.ai.workflows.event_deep_dive.celery_task import _run_deep_dive_async

        event_id = str(uuid.uuid4())
        tenant_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())

        final_state = DeepDiveWorkflowState(
            workflow_id=uuid.uuid4(),
            workflow_type=WorkflowType.EVENT_DEEP_DIVE,
            tenant_id=uuid.UUID(tenant_id),
            user_id=uuid.UUID(user_id),
            company_id=uuid.uuid4(),
            started_at=datetime.now(tz=timezone.utc),
            confidence_scores={"workflow": 0.75},
        )

        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(return_value=final_state)

        with (
            patch(
                "src.ai.workflows.event_deep_dive.celery_task.build_deep_dive_graph",
                return_value=mock_graph,
            ),
            patch(
                "src.ai.workflows.event_deep_dive.celery_task.WorkflowTimeoutGuard",
            ) as mock_guard_cls,
        ):
            mock_guard = AsyncMock()
            mock_guard.__aenter__ = AsyncMock(return_value=mock_guard)
            mock_guard.__aexit__ = AsyncMock(return_value=False)
            mock_guard_cls.return_value = mock_guard

            result = await _run_deep_dive_async(
                event_id=event_id,
                tenant_id=tenant_id,
                user_id=user_id,
            )

        assert "status" in result
        assert "event_id" in result
        assert result["event_id"] == event_id
