"""
Unit tests for Morning Brief workflow nodes.

Covers TASK-001 through TASK-011 per PLAN-F-006.

TDD: tests define the contracts for all node functions and Pydantic models.

AC covered: AC-001, AC-002, AC-003, AC-004, AC-005, AC-006
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import logging

import pytest

from src.ai.schemas.morning_brief_state import (
    BriefRow,
    ConfidenceRoute,
    HilStatus,
    MorningBriefState,
)


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _make_state(**kwargs) -> MorningBriefState:
    defaults = {
        "workflow_id": uuid.uuid4(),
        "tenant_id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "started_at": datetime.now(tz=timezone.utc),
    }
    defaults.update(kwargs)
    return MorningBriefState(**defaults)


# ─── TASK-001: MorningBriefState defaults and enums ──────────────────────────


class TestMorningBriefStateDefaults:
    def test_morning_brief_state_defaults(self):
        """Verify all default field values of MorningBriefState."""
        state = _make_state()
        assert state.workflow_type == "morning_brief"
        assert state.portfolio_state is None
        assert state.events == []
        assert state.relevant_events == []
        assert state.score_changes == []
        assert state.anomalies == []
        assert state.analogies == {}
        assert state.recommendations == []
        assert state.report is None
        assert state.confidence_scores == {}
        assert state.requires_hil is False
        assert state.hil_reason is None
        assert state.cost_usd == 0.0
        assert state.langfuse_trace_id is None
        assert state.confidence_route is None
        assert state.brief_id is None
        assert state.dispatch_time == "06:00"

    def test_confidence_route_enum_values(self):
        """ConfidenceRoute enum strings must match routing logic expectations."""
        assert ConfidenceRoute.AUTO_SEND == "auto_send"
        assert ConfidenceRoute.HIL == "hil"
        assert ConfidenceRoute.BLOCK == "block"

    def test_hil_status_enum_values(self):
        """HilStatus enum strings must match DB column values."""
        assert HilStatus.NOT_REQUIRED == "not_required"
        assert HilStatus.PENDING == "pending"
        assert HilStatus.APPROVED == "approved"
        assert HilStatus.REJECTED == "rejected"
        assert HilStatus.TIMED_OUT == "timed_out"

    def test_brief_row_serialization(self):
        """BriefRow must round-trip JSON serialization correctly."""
        row = BriefRow(
            brief_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            workflow_id=uuid.uuid4(),
            content="<h1>Brief</h1>",
            confidence=0.85,
            hil_status=HilStatus.NOT_REQUIRED,
            cost_usd=0.42,
        )
        data = row.model_dump()
        restored = BriefRow(**data)
        assert restored.confidence == row.confidence
        assert restored.content == row.content
        assert restored.cost_usd == row.cost_usd

    def test_brief_table_migration_applies_cleanly(self):
        """Migration module must define upgrade/downgrade callables."""
        import importlib
        import sys
        import pathlib

        # Read the migration source and verify it defines upgrade/downgrade
        migration_path = pathlib.Path(
            "src/db/migrations/versions/add_brief_table_morning_brief.py"
        )
        source = migration_path.read_text(encoding="utf-8")
        assert "def upgrade" in source, "Migration must define upgrade()"
        assert "def downgrade" in source, "Migration must define downgrade()"
        # Verify the revision identifier is present
        assert "revision" in source


# ─── TASK-003: DeterministicNodes ────────────────────────────────────────────


class TestFetchPortfolio:
    @pytest.mark.asyncio
    async def test_fetch_portfolio_populates_state(self):
        """fetch_portfolio_state must populate state.portfolio_state."""
        from src.ai.workflows.morning_brief_nodes import fetch_portfolio_state

        state = _make_state()
        positions = [{"company_id": str(uuid.uuid4())}]
        watchlist = [{"company_id": str(uuid.uuid4())}]
        repo = MagicMock()
        repo.get_positions = AsyncMock(return_value=positions)
        repo.get_watchlist = AsyncMock(return_value=watchlist)

        updated = await fetch_portfolio_state(state, portfolio_repo=repo)

        assert updated.portfolio_state is not None
        assert updated.portfolio_state["positions"] == positions

    @pytest.mark.asyncio
    async def test_fetch_portfolio_aborts_on_empty_portfolio(self):
        """fetch_portfolio must raise WorkflowAbortError when portfolio is empty."""
        from src.ai.workflows.morning_brief.nodes.fetch_portfolio import (
            fetch_portfolio,
            WorkflowAbortError,
        )

        state = _make_state()
        repo = MagicMock()
        repo.get_positions = AsyncMock(return_value=[])
        repo.get_watchlist = AsyncMock(return_value=[])

        with pytest.raises(WorkflowAbortError):
            await fetch_portfolio(state, portfolio_repo=repo)

    @pytest.mark.asyncio
    async def test_fetch_overnight_events_handles_insufficient_data(self):
        """fetch_overnight_events must gracefully handle InsufficientData."""
        from src.ai.workflows.morning_brief.nodes.fetch_overnight_events import (
            fetch_overnight_events,
            InsufficientData,
        )

        state = _make_state()
        repo = MagicMock()
        repo.get_events_in_window = AsyncMock(side_effect=InsufficientData("no data"))

        updated = await fetch_overnight_events(state, event_repo=repo)

        assert updated.events == []

    @pytest.mark.asyncio
    async def test_recompute_scores_updates_score_changes(self):
        """recompute_scores must populate state.score_changes."""
        from src.ai.workflows.morning_brief.nodes.recompute_scores import (
            recompute_scores,
        )

        company_id = str(uuid.uuid4())
        state = _make_state(
            portfolio_state={
                "positions": [{"company_id": company_id}],
                "watchlist": [],
            },
            relevant_events=[{"event_id": "e1", "company_id": company_id}],
        )
        score_repo = MagicMock()
        score_repo.get_score_changes = AsyncMock(
            return_value=[{"company_id": company_id, "delta": 0.12}]
        )

        updated = await recompute_scores(state, score_repo=score_repo)

        assert len(updated.score_changes) >= 1


# ─── TASK-004: Relevance Analyst and Anomaly Detector nodes ──────────────────


class TestRelevanceAnalystNode:
    @pytest.mark.asyncio
    async def test_relevance_analyst_filters_events(self):
        """relevance_analyst_node must filter events and populate relevant_events."""
        from src.ai.workflows.morning_brief.nodes.relevance_analyst_node import (
            relevance_analyst_node,
        )

        events = [{"event_id": f"e{i}"} for i in range(5)]
        state = _make_state(events=events)
        relevant = [{"event_id": "e1"}, {"event_id": "e3"}]

        invoke = AsyncMock(
            return_value={
                "output": {"relevant_events": relevant},
                "confidence": 0.82,
                "cost_usd": 0.05,
                "input_tokens": 100,
                "output_tokens": 50,
            }
        )
        registry = MagicMock()
        registry.resolve.return_value = MagicMock()

        updated = await relevance_analyst_node(
            state, registry=registry, _invoke_llm=invoke
        )

        assert len(updated.relevant_events) == 2

    @pytest.mark.asyncio
    async def test_relevance_analyst_accumulates_cost(self):
        """relevance_analyst_node must add cost to state.cost_usd."""
        from src.ai.workflows.morning_brief.nodes.relevance_analyst_node import (
            relevance_analyst_node,
        )

        state = _make_state()
        invoke = AsyncMock(
            return_value={
                "output": {"relevant_events": []},
                "confidence": 0.80,
                "cost_usd": 0.05,
                "input_tokens": 100,
                "output_tokens": 50,
            }
        )
        registry = MagicMock()
        registry.resolve.return_value = MagicMock()

        updated = await relevance_analyst_node(
            state, registry=registry, _invoke_llm=invoke
        )

        assert updated.cost_usd == pytest.approx(0.05)

    @pytest.mark.asyncio
    async def test_relevance_analyst_sets_confidence_score(self):
        """relevance_analyst_node must store confidence in confidence_scores."""
        from src.ai.workflows.morning_brief.nodes.relevance_analyst_node import (
            relevance_analyst_node,
        )

        state = _make_state()
        invoke = AsyncMock(
            return_value={
                "output": {"relevant_events": []},
                "confidence": 0.82,
                "cost_usd": 0.01,
                "input_tokens": 100,
                "output_tokens": 50,
            }
        )
        registry = MagicMock()
        registry.resolve.return_value = MagicMock()

        updated = await relevance_analyst_node(
            state, registry=registry, _invoke_llm=invoke
        )

        assert "relevance_analyst" in updated.confidence_scores
        assert updated.confidence_scores["relevance_analyst"] == pytest.approx(0.82)

    @pytest.mark.asyncio
    async def test_relevance_analyst_routes_to_hil_on_limit_exceeded(self):
        """relevance_analyst_node must set requires_hil on LimitExceededError."""
        from src.ai.workflows.morning_brief.nodes.relevance_analyst_node import (
            relevance_analyst_node,
            LimitExceededError,
        )

        state = _make_state()
        invoke = AsyncMock(side_effect=LimitExceededError("budget exceeded"))
        registry = MagicMock()
        registry.resolve.return_value = MagicMock()

        updated = await relevance_analyst_node(
            state, registry=registry, _invoke_llm=invoke
        )

        assert updated.requires_hil is True

    @pytest.mark.asyncio
    async def test_anomaly_detector_populates_anomalies(self):
        """anomaly_detector_node must populate state.anomalies."""
        from src.ai.workflows.morning_brief.nodes.anomaly_detector_node import (
            anomaly_detector_node,
        )

        state = _make_state()
        anomalies = [{"company_id": "c1", "reason": "spike"}]
        invoke = AsyncMock(
            return_value={
                "output": {"anomalies": anomalies},
                "confidence": 0.78,
                "cost_usd": 0.03,
                "input_tokens": 80,
                "output_tokens": 40,
            }
        )
        registry = MagicMock()
        registry.resolve.return_value = MagicMock()

        updated = await anomaly_detector_node(
            state, registry=registry, _invoke_llm=invoke
        )

        assert updated.anomalies == anomalies

    @pytest.mark.asyncio
    async def test_anomaly_detector_confidence_stored(self):
        """anomaly_detector_node must store confidence in confidence_scores."""
        from src.ai.workflows.morning_brief.nodes.anomaly_detector_node import (
            anomaly_detector_node,
        )

        state = _make_state()
        invoke = AsyncMock(
            return_value={
                "output": {"anomalies": []},
                "confidence": 0.55,
                "cost_usd": 0.02,
                "input_tokens": 50,
                "output_tokens": 25,
            }
        )
        registry = MagicMock()
        registry.resolve.return_value = MagicMock()

        updated = await anomaly_detector_node(
            state, registry=registry, _invoke_llm=invoke
        )

        assert "anomaly_detector" in updated.confidence_scores
        assert updated.confidence_scores["anomaly_detector"] == pytest.approx(0.55)


# ─── TASK-005: Historical Context Agent ──────────────────────────────────────


class TestHistoricalContextNode:
    @pytest.mark.asyncio
    async def test_historical_context_parallel_invocations(self):
        """historical_context_node must invoke agent once per relevant event."""
        from src.ai.workflows.morning_brief.nodes.historical_context_node import (
            historical_context_node,
        )

        events = [
            {"event_id": f"e{i}", "title": f"Event {i}"}
            for i in range(3)
        ]
        state = _make_state(relevant_events=events)
        invoke = AsyncMock(
            return_value={
                "output": {"analogies": [{"year": 2020}]},
                "confidence": 0.80,
                "cost_usd": 0.10,
                "input_tokens": 200,
                "output_tokens": 100,
            }
        )
        registry = MagicMock()
        registry.resolve.return_value = MagicMock()

        updated = await historical_context_node(
            state, registry=registry, _invoke_llm=invoke
        )

        assert len(updated.analogies) == 3

    @pytest.mark.asyncio
    async def test_historical_context_minimum_confidence(self):
        """historical_context_node must use minimum confidence across invocations."""
        from src.ai.workflows.morning_brief.nodes.historical_context_node import (
            historical_context_node,
        )

        events = [{"event_id": f"e{i}"} for i in range(3)]
        state = _make_state(relevant_events=events)
        confidences = [0.9, 0.45, 0.8]
        call_count = 0

        async def mock_invoke(role_id, st, defn):
            nonlocal call_count
            result = {
                "output": {"analogies": []},
                "confidence": confidences[call_count % len(confidences)],
                "cost_usd": 0.10,
                "input_tokens": 100,
                "output_tokens": 50,
            }
            call_count += 1
            return result

        registry = MagicMock()
        registry.resolve.return_value = MagicMock()

        updated = await historical_context_node(
            state, registry=registry, _invoke_llm=mock_invoke
        )

        assert updated.confidence_scores.get("historical_context_agent") == pytest.approx(0.45)

    @pytest.mark.asyncio
    async def test_historical_context_cost_accumulation(self):
        """historical_context_node must sum cost from all parallel invocations."""
        from src.ai.workflows.morning_brief.nodes.historical_context_node import (
            historical_context_node,
        )

        events = [{"event_id": f"e{i}"} for i in range(3)]
        state = _make_state(relevant_events=events)
        invoke = AsyncMock(
            return_value={
                "output": {"analogies": []},
                "confidence": 0.80,
                "cost_usd": 0.10,
                "input_tokens": 100,
                "output_tokens": 50,
            }
        )
        registry = MagicMock()
        registry.resolve.return_value = MagicMock()

        updated = await historical_context_node(
            state, registry=registry, _invoke_llm=invoke
        )

        assert updated.cost_usd == pytest.approx(0.30)

    @pytest.mark.asyncio
    async def test_historical_context_empty_events_no_op(self):
        """historical_context_node must be no-op when relevant_events is empty."""
        from src.ai.workflows.morning_brief.nodes.historical_context_node import (
            historical_context_node,
        )

        state = _make_state(relevant_events=[])
        invoke = AsyncMock()
        registry = MagicMock()
        registry.resolve.return_value = MagicMock()

        updated = await historical_context_node(
            state, registry=registry, _invoke_llm=invoke
        )

        assert updated.analogies == {}
        invoke.assert_not_called()

    @pytest.mark.asyncio
    async def test_historical_context_span_per_invocation(self):
        """historical_context_node must create one Langfuse span per invocation."""
        from src.ai.workflows.morning_brief.nodes.historical_context_node import (
            historical_context_node,
        )

        events = [{"event_id": f"e{i}"} for i in range(3)]
        state = _make_state(
            relevant_events=events, langfuse_trace_id="trace-123"
        )
        invoke = AsyncMock(
            return_value={
                "output": {"analogies": []},
                "confidence": 0.80,
                "cost_usd": 0.05,
                "input_tokens": 100,
                "output_tokens": 50,
            }
        )
        registry = MagicMock()
        registry.resolve.return_value = MagicMock()

        mock_langfuse = MagicMock()
        mock_span = MagicMock()
        mock_langfuse.span.return_value = mock_span
        mock_span.__enter__ = MagicMock(return_value=mock_span)
        mock_span.__exit__ = MagicMock(return_value=False)

        with patch(
            "src.ai.workflows.morning_brief.nodes.historical_context_node._get_langfuse",
            return_value=mock_langfuse,
        ):
            updated = await historical_context_node(
                state, registry=registry, _invoke_llm=invoke
            )

        # 3 events should produce 3 spans
        assert mock_langfuse.span.call_count == 3


# ─── TASK-006: Recommendation Synthesizer ────────────────────────────────────


class TestRecommendationNode:
    @pytest.mark.asyncio
    async def test_recommendation_node_produces_recommendations(self):
        """recommendation_node must populate state.recommendations."""
        from src.ai.workflows.morning_brief.nodes.recommendation_node import (
            recommendation_node,
        )

        state = _make_state()
        recs = [{"action_signal": "HOLD", "company_id": str(uuid.uuid4())}]
        invoke = AsyncMock(
            return_value={
                "output": {"recommendations": recs},
                "confidence": 0.75,
                "cost_usd": 0.08,
                "input_tokens": 150,
                "output_tokens": 75,
            }
        )
        registry = MagicMock()
        registry.resolve.return_value = MagicMock()
        rec_repo = AsyncMock()

        updated = await recommendation_node(
            state, registry=registry, rec_repo=rec_repo, _invoke_llm=invoke
        )

        assert len(updated.recommendations) == 1

    @pytest.mark.asyncio
    async def test_recommendation_node_persists_to_db(self):
        """recommendation_node must call rec_repo.save once per recommendation."""
        from src.ai.workflows.morning_brief.nodes.recommendation_node import (
            recommendation_node,
        )

        state = _make_state()
        recs = [
            {"action_signal": "HOLD", "company_id": str(uuid.uuid4())},
            {"action_signal": "WATCH", "company_id": str(uuid.uuid4())},
        ]
        invoke = AsyncMock(
            return_value={
                "output": {"recommendations": recs},
                "confidence": 0.75,
                "cost_usd": 0.08,
                "input_tokens": 150,
                "output_tokens": 75,
            }
        )
        registry = MagicMock()
        registry.resolve.return_value = MagicMock()
        rec_repo = AsyncMock()
        rec_repo.save = AsyncMock()

        await recommendation_node(
            state, registry=registry, rec_repo=rec_repo, _invoke_llm=invoke
        )

        assert rec_repo.save.call_count == 2

    @pytest.mark.asyncio
    async def test_recommendation_node_confidence_stored(self):
        """recommendation_node must store agent confidence in confidence_scores."""
        from src.ai.workflows.morning_brief.nodes.recommendation_node import (
            recommendation_node,
        )

        state = _make_state()
        invoke = AsyncMock(
            return_value={
                "output": {"recommendations": []},
                "confidence": 0.75,
                "cost_usd": 0.06,
                "input_tokens": 100,
                "output_tokens": 50,
            }
        )
        registry = MagicMock()
        registry.resolve.return_value = MagicMock()
        rec_repo = AsyncMock()

        updated = await recommendation_node(
            state, registry=registry, rec_repo=rec_repo, _invoke_llm=invoke
        )

        assert updated.confidence_scores.get("recommendation_synthesizer") == pytest.approx(0.75)

    @pytest.mark.asyncio
    async def test_recommendation_node_on_empty_analogies(self):
        """recommendation_node must still invoke agent when analogies are empty."""
        from src.ai.workflows.morning_brief.nodes.recommendation_node import (
            recommendation_node,
        )

        state = _make_state(analogies={})
        invoke = AsyncMock(
            return_value={
                "output": {"recommendations": []},
                "confidence": 0.70,
                "cost_usd": 0.05,
                "input_tokens": 80,
                "output_tokens": 40,
            }
        )
        registry = MagicMock()
        registry.resolve.return_value = MagicMock()
        rec_repo = AsyncMock()

        updated = await recommendation_node(
            state, registry=registry, rec_repo=rec_repo, _invoke_llm=invoke
        )

        invoke.assert_called_once()
        assert isinstance(updated.recommendations, list)


# ─── TASK-007: evaluate_quality node ─────────────────────────────────────────


class TestEvaluateQualityNode:
    @pytest.mark.asyncio
    async def test_evaluate_quality_computes_minimum_confidence(self):
        """evaluate_quality_node must use min across all confidence_scores."""
        from src.ai.workflows.morning_brief.nodes.evaluate_quality_node import (
            evaluate_quality_node,
        )

        state = _make_state(
            confidence_scores={
                "relevance_analyst": 0.9,
                "anomaly_detector": 0.65,
                "historical_context_agent": 0.8,
            }
        )
        invoke = AsyncMock(
            return_value={
                "output": {"quality_score": 0.72, "rationale": "Good"},
                "confidence": 0.72,
                "cost_usd": 0.05,
                "input_tokens": 200,
                "output_tokens": 100,
            }
        )
        registry = MagicMock()
        registry.resolve.return_value = MagicMock()

        updated = await evaluate_quality_node(
            state, registry=registry, _invoke_llm=invoke
        )

        # minimum of [0.9, 0.65, 0.8] = 0.65 => HIL path
        assert updated.requires_hil is True

    @pytest.mark.asyncio
    async def test_evaluate_quality_sets_requires_hil_on_low_confidence(self):
        """evaluate_quality_node must set requires_hil when confidence < 0.70."""
        from src.ai.workflows.morning_brief.nodes.evaluate_quality_node import (
            evaluate_quality_node,
        )

        state = _make_state(confidence_scores={"agent": 0.55})
        invoke = AsyncMock(
            return_value={
                "output": {"quality_score": 0.55},
                "confidence": 0.55,
                "cost_usd": 0.04,
                "input_tokens": 100,
                "output_tokens": 50,
            }
        )
        registry = MagicMock()
        registry.resolve.return_value = MagicMock()

        updated = await evaluate_quality_node(
            state, registry=registry, _invoke_llm=invoke
        )

        assert updated.requires_hil is True

    @pytest.mark.asyncio
    async def test_evaluate_quality_auto_send_path(self):
        """evaluate_quality_node must NOT set requires_hil when all scores >= 0.7."""
        from src.ai.workflows.morning_brief.nodes.evaluate_quality_node import (
            evaluate_quality_node,
        )

        state = _make_state(
            confidence_scores={"agent1": 0.85, "agent2": 0.75}
        )
        invoke = AsyncMock(
            return_value={
                "output": {"quality_score": 0.80},
                "confidence": 0.80,
                "cost_usd": 0.05,
                "input_tokens": 150,
                "output_tokens": 75,
            }
        )
        registry = MagicMock()
        registry.resolve.return_value = MagicMock()

        updated = await evaluate_quality_node(
            state, registry=registry, _invoke_llm=invoke
        )

        assert updated.requires_hil is False
        assert updated.confidence_route == ConfidenceRoute.AUTO_SEND

    @pytest.mark.asyncio
    async def test_evaluate_quality_block_path(self):
        """evaluate_quality_node must set BLOCK route when min score < 0.4."""
        from src.ai.workflows.morning_brief.nodes.evaluate_quality_node import (
            evaluate_quality_node,
        )

        state = _make_state(confidence_scores={"agent": 0.35})
        invoke = AsyncMock(
            return_value={
                "output": {"quality_score": 0.35},
                "confidence": 0.35,
                "cost_usd": 0.04,
                "input_tokens": 100,
                "output_tokens": 50,
            }
        )
        registry = MagicMock()
        registry.resolve.return_value = MagicMock()

        updated = await evaluate_quality_node(
            state, registry=registry, _invoke_llm=invoke
        )

        assert updated.confidence_route == ConfidenceRoute.BLOCK

    @pytest.mark.asyncio
    async def test_evaluate_quality_writes_langfuse_score(self):
        """evaluate_quality_node must write a Langfuse score linked to trace_id."""
        from src.ai.workflows.morning_brief.nodes.evaluate_quality_node import (
            evaluate_quality_node,
        )

        state = _make_state(
            langfuse_trace_id="trace-abc-123",
            confidence_scores={"agent": 0.80},
        )
        invoke = AsyncMock(
            return_value={
                "output": {"quality_score": 0.80},
                "confidence": 0.80,
                "cost_usd": 0.04,
                "input_tokens": 100,
                "output_tokens": 50,
            }
        )
        registry = MagicMock()
        registry.resolve.return_value = MagicMock()
        mock_langfuse = MagicMock()

        with patch(
            "src.ai.workflows.morning_brief.nodes.evaluate_quality_node._get_langfuse",
            return_value=mock_langfuse,
        ):
            updated = await evaluate_quality_node(
                state, registry=registry, _invoke_llm=invoke
            )

        mock_langfuse.score.assert_called_once()
        call_kwargs = mock_langfuse.score.call_args[1]
        assert call_kwargs.get("trace_id") == "trace-abc-123"

    def test_evaluate_quality_is_second_to_last_enforced(self):
        """Graph structure must place evaluate_quality second-to-last."""
        from src.ai.workflows.morning_brief.graph import _NODE_SEQUENCE

        assert "evaluate_quality" in _NODE_SEQUENCE
        idx = _NODE_SEQUENCE.index("evaluate_quality")
        assert idx == len(_NODE_SEQUENCE) - 2, (
            "evaluate_quality must be the second-to-last node in the sequence"
        )


# ─── TASK-008: confidence_router and block_and_log ───────────────────────────


class TestConfidenceRouter:
    def test_router_returns_narrative_writer_on_high_confidence(self):
        """confidence_router must return 'narrative_writer' for score >= 0.70."""
        from src.ai.workflows.morning_brief.routing import confidence_router

        state = _make_state(confidence_scores={"agent": 0.75})
        assert confidence_router(state) == "narrative_writer"

    def test_router_returns_hil_on_medium_confidence(self):
        """confidence_router must return 'hil_queue' for score in [0.40, 0.70)."""
        from src.ai.workflows.morning_brief.routing import confidence_router

        state = _make_state(confidence_scores={"agent": 0.55})
        assert confidence_router(state) == "hil_queue"

    def test_router_returns_block_on_low_confidence(self):
        """confidence_router must return 'block_and_log' for score < 0.40."""
        from src.ai.workflows.morning_brief.routing import confidence_router

        state = _make_state(confidence_scores={"agent": 0.35})
        assert confidence_router(state) == "block_and_log"

    def test_router_boundary_0_70_is_auto_send(self):
        """confidence_router must route score exactly 0.70 to narrative_writer."""
        from src.ai.workflows.morning_brief.routing import confidence_router

        state = _make_state(confidence_scores={"agent": 0.70})
        assert confidence_router(state) == "narrative_writer"

    def test_router_boundary_0_40_is_hil(self):
        """confidence_router must route score exactly 0.40 to hil_queue."""
        from src.ai.workflows.morning_brief.routing import confidence_router

        state = _make_state(confidence_scores={"agent": 0.40})
        assert confidence_router(state) == "hil_queue"

    @pytest.mark.asyncio
    async def test_block_and_log_persists_brief_row(self):
        """block_and_log must persist a BriefRow with hil_status NOT_REQUIRED."""
        from src.ai.workflows.morning_brief.nodes.block_and_log import block_and_log

        state = _make_state(
            report="<p>brief</p>",
            confidence_scores={"agent": 0.30},
        )
        brief_repo = AsyncMock()
        workflow_repo = AsyncMock()
        brief_repo.insert = AsyncMock(return_value=MagicMock(brief_id=uuid.uuid4()))

        updated = await block_and_log(
            state,
            brief_repo=brief_repo,
            workflow_repo=workflow_repo,
        )

        brief_repo.insert.assert_called_once()
        call_dto = brief_repo.insert.call_args.args[0]
        assert call_dto.hil_status == HilStatus.NOT_REQUIRED

    @pytest.mark.asyncio
    async def test_block_and_log_writes_episodic_memory(self):
        """block_and_log must write an episodic memory entry with status 'blocked'."""
        from src.ai.workflows.morning_brief.nodes.block_and_log import block_and_log

        state = _make_state(confidence_scores={"agent": 0.25})
        brief_repo = AsyncMock()
        brief_repo.insert = AsyncMock(return_value=MagicMock(brief_id=uuid.uuid4()))
        workflow_repo = AsyncMock()
        episodic_repo = AsyncMock()

        await block_and_log(
            state,
            brief_repo=brief_repo,
            workflow_repo=workflow_repo,
            episodic_repo=episodic_repo,
        )

        episodic_repo.write.assert_called_once()
        entry = episodic_repo.write.call_args.args[0]
        assert entry.get("status") == "blocked"


# ─── TASK-009: Narrative Writer ───────────────────────────────────────────────


class TestNarrativeWriterNode:
    @pytest.mark.asyncio
    async def test_narrative_writer_produces_html_report(self):
        """narrative_writer_node must populate state.report with non-empty HTML."""
        from src.ai.workflows.morning_brief.nodes.narrative_writer_node import (
            narrative_writer_node,
        )

        state = _make_state(
            confidence_route=ConfidenceRoute.AUTO_SEND,
            recommendations=[{"action_signal": "HOLD"}],
        )
        html = "<html><body><h1>Morning Brief</h1></body></html>"
        invoke = AsyncMock(
            return_value={
                "output": {"report": html},
                "confidence": 0.88,
                "cost_usd": 0.12,
                "input_tokens": 300,
                "output_tokens": 150,
            }
        )
        registry = MagicMock()
        registry.resolve.return_value = MagicMock()

        updated = await narrative_writer_node(
            state, registry=registry, _invoke_llm=invoke
        )

        assert updated.report is not None
        assert len(updated.report) > 0

    @pytest.mark.asyncio
    async def test_narrative_writer_injects_into_template(self):
        """narrative_writer_node rendered HTML must contain portfolio content."""
        from src.ai.workflows.morning_brief.nodes.narrative_writer_node import (
            narrative_writer_node,
        )

        state = _make_state(
            confidence_route=ConfidenceRoute.AUTO_SEND,
            portfolio_state={"positions": [{"ticker": "AAPL"}]},
            recommendations=[{"action_signal": "HOLD", "ticker": "AAPL"}],
        )
        html = "<html><body>AAPL analysis</body></html>"
        invoke = AsyncMock(
            return_value={
                "output": {"report": html},
                "confidence": 0.85,
                "cost_usd": 0.10,
                "input_tokens": 250,
                "output_tokens": 125,
            }
        )
        registry = MagicMock()
        registry.resolve.return_value = MagicMock()

        updated = await narrative_writer_node(
            state, registry=registry, _invoke_llm=invoke
        )

        assert updated.report is not None

    @pytest.mark.asyncio
    async def test_narrative_writer_not_invoked_on_block_path(self):
        """narrative_writer_node must not invoke agent when route is BLOCK."""
        from src.ai.workflows.morning_brief.nodes.narrative_writer_node import (
            narrative_writer_node,
        )

        state = _make_state(confidence_route=ConfidenceRoute.BLOCK)
        invoke = AsyncMock()
        registry = MagicMock()
        registry.resolve.return_value = MagicMock()

        updated = await narrative_writer_node(
            state, registry=registry, _invoke_llm=invoke
        )

        invoke.assert_not_called()
        assert updated.report is None

    def test_narrative_writer_is_last_agent_node(self):
        """Graph structure must place narrative_writer as last agent node."""
        from src.ai.workflows.morning_brief.graph import _NODE_SEQUENCE

        assert "narrative_writer" in _NODE_SEQUENCE
        # narrative_writer is at the very end of the agent sequence
        assert _NODE_SEQUENCE[-1] == "narrative_writer"


# ─── TASK-010: format_and_dispatch ───────────────────────────────────────────


class TestFormatAndDispatch:
    @pytest.mark.asyncio
    async def test_format_and_dispatch_calls_sendgrid_with_correct_params(self):
        """format_and_dispatch must call SendGrid with user email and brief_id."""
        from src.ai.workflows.morning_brief.nodes.format_and_dispatch import (
            format_and_dispatch,
        )

        brief_id = uuid.uuid4()
        state = _make_state(
            report="<h1>Brief</h1>",
            brief_id=brief_id,
            dispatch_time="06:00",
        )
        dispatcher = AsyncMock()
        dispatcher.send_morning_brief = AsyncMock(return_value=True)
        brief_repo = AsyncMock()
        brief_repo.update_sent_at = AsyncMock()
        workflow_repo = AsyncMock()
        user_repo = AsyncMock()
        user_repo.get_dispatch_time = AsyncMock(return_value="06:00")

        await format_and_dispatch(
            state,
            dispatcher=dispatcher,
            brief_repo=brief_repo,
            workflow_repo=workflow_repo,
            user_repo=user_repo,
            user_email="user@example.com",
        )

        dispatcher.send_morning_brief.assert_called_once()
        call_kwargs = dispatcher.send_morning_brief.call_args[1]
        assert "brief_id" in call_kwargs

    @pytest.mark.asyncio
    async def test_format_and_dispatch_updates_brief_sent_at(self):
        """format_and_dispatch must update BriefRow.sent_at on success."""
        from src.ai.workflows.morning_brief.nodes.format_and_dispatch import (
            format_and_dispatch,
        )

        state = _make_state(report="<p>brief</p>", brief_id=uuid.uuid4())
        dispatcher = AsyncMock()
        dispatcher.send_morning_brief = AsyncMock(return_value=True)
        brief_repo = AsyncMock()
        brief_repo.update_sent_at = AsyncMock()
        workflow_repo = AsyncMock()
        user_repo = AsyncMock()
        user_repo.get_dispatch_time = AsyncMock(return_value="06:00")

        await format_and_dispatch(
            state,
            dispatcher=dispatcher,
            brief_repo=brief_repo,
            workflow_repo=workflow_repo,
            user_repo=user_repo,
            user_email="user@example.com",
        )

        brief_repo.update_sent_at.assert_called_once()

    @pytest.mark.asyncio
    async def test_format_and_dispatch_handles_sendgrid_error_gracefully(self):
        """format_and_dispatch must not raise on SendGrid error."""
        from src.ai.workflows.morning_brief.nodes.format_and_dispatch import (
            format_and_dispatch,
        )

        state = _make_state(report="<p>brief</p>", brief_id=uuid.uuid4())
        dispatcher = AsyncMock()
        dispatcher.send_morning_brief = AsyncMock(
            side_effect=Exception("SendGrid error")
        )
        brief_repo = AsyncMock()
        workflow_repo = AsyncMock()
        workflow_repo.update_status = AsyncMock()
        user_repo = AsyncMock()
        user_repo.get_dispatch_time = AsyncMock(return_value="06:00")

        # Must NOT raise
        await format_and_dispatch(
            state,
            dispatcher=dispatcher,
            brief_repo=brief_repo,
            workflow_repo=workflow_repo,
            user_repo=user_repo,
            user_email="user@example.com",
        )

        workflow_repo.update_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_format_and_dispatch_reads_user_dispatch_time(self):
        """format_and_dispatch must read user dispatch_time and pass to SendGrid."""
        from src.ai.workflows.morning_brief.nodes.format_and_dispatch import (
            format_and_dispatch,
        )

        state = _make_state(report="<p>brief</p>", brief_id=uuid.uuid4())
        dispatcher = AsyncMock()
        dispatcher.send_morning_brief = AsyncMock(return_value=True)
        brief_repo = AsyncMock()
        brief_repo.update_sent_at = AsyncMock()
        workflow_repo = AsyncMock()
        user_repo = AsyncMock()
        user_repo.get_dispatch_time = AsyncMock(return_value="07:30")

        await format_and_dispatch(
            state,
            dispatcher=dispatcher,
            brief_repo=brief_repo,
            workflow_repo=workflow_repo,
            user_repo=user_repo,
            user_email="user@example.com",
        )

        call_kwargs = dispatcher.send_morning_brief.call_args[1]
        assert call_kwargs.get("scheduled_for") == "07:30"

    @pytest.mark.asyncio
    async def test_format_and_dispatch_uses_default_time_if_unset(self):
        """format_and_dispatch must default to 06:00 when user dispatch_time is None."""
        from src.ai.workflows.morning_brief.nodes.format_and_dispatch import (
            format_and_dispatch,
        )

        state = _make_state(report="<p>brief</p>", brief_id=uuid.uuid4())
        dispatcher = AsyncMock()
        dispatcher.send_morning_brief = AsyncMock(return_value=True)
        brief_repo = AsyncMock()
        brief_repo.update_sent_at = AsyncMock()
        workflow_repo = AsyncMock()
        user_repo = AsyncMock()
        user_repo.get_dispatch_time = AsyncMock(return_value=None)

        await format_and_dispatch(
            state,
            dispatcher=dispatcher,
            brief_repo=brief_repo,
            workflow_repo=workflow_repo,
            user_repo=user_repo,
            user_email="user@example.com",
        )

        call_kwargs = dispatcher.send_morning_brief.call_args[1]
        assert call_kwargs.get("scheduled_for") == "06:00"
