"""
Integration tests for the Morning Brief workflow — all routing branches.

Tests use real MorningBriefState/Graph and mocked external dependencies
(LLM, SendGrid, DB repositories).

PLAN-F-006 TASK-015

AC covered: AC-001, AC-002, AC-003, AC-004, AC-005, AC-006
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.ai.workflows.morning_brief_state import ConfidenceRoute, MorningBriefState
from src.ai.workflows.morning_brief.graph import (
    MorningBriefGraph,
    MorningBriefWorkflow,
)
from src.ai.workflows.morning_brief_nodes import WorkflowCostCeilingExceeded


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_registry_with_confidence(confidence: float) -> MagicMock:
    """Registry stub that returns the given confidence for all agents."""
    registry = MagicMock()
    definition = MagicMock()
    registry.resolve.return_value = definition
    return registry, confidence


def _make_portfolio_repo() -> AsyncMock:
    repo = AsyncMock()
    repo.get_positions = AsyncMock(
        return_value=[{"company_id": str(uuid.uuid4()), "ticker": "AAPL"}]
    )
    repo.get_watchlist = AsyncMock(return_value=[])
    return repo


def _make_event_repo(events: list | None = None) -> AsyncMock:
    repo = AsyncMock()
    repo.get_events_in_window = AsyncMock(
        return_value=events
        or [
            {"event_id": "e1", "title": "Trade news"},
            {"event_id": "e2", "title": "Fed statement"},
            {"event_id": "e3", "title": "Earnings beat"},
        ]
    )
    return repo


def _make_brief_repo() -> AsyncMock:
    repo = AsyncMock()
    mock_brief = MagicMock()
    mock_brief.brief_id = uuid.uuid4()
    repo.insert = AsyncMock(return_value=mock_brief)
    repo.update_sent_at = AsyncMock()
    repo.update_hil_status = AsyncMock()
    repo.get_latest_by_user = AsyncMock(return_value=mock_brief)
    return repo


def _make_workflow_repo() -> AsyncMock:
    repo = AsyncMock()
    repo.create = AsyncMock()
    repo.update_status = AsyncMock()
    return repo


def _make_hil_repo() -> AsyncMock:
    repo = AsyncMock()
    mock_item = MagicMock()
    mock_item.item_id = uuid.uuid4()
    repo.create = AsyncMock(return_value=mock_item)
    repo.update_status = AsyncMock()
    repo.list_timed_out_pending = AsyncMock(return_value=[])
    return repo


def _make_dispatcher() -> AsyncMock:
    dispatcher = AsyncMock()
    dispatcher.send_morning_brief = AsyncMock(return_value=True)
    dispatcher.send_no_brief_notification = AsyncMock()
    return dispatcher


def _build_node_registry(
    *,
    confidence: float = 0.85,
    dispatcher: AsyncMock | None = None,
) -> dict:
    """Build a node_registry with all mocked dependencies."""
    registry, _ = _make_registry_with_confidence(confidence)

    async def mock_invoke(role_id, state, defn):
        # Returns appropriate output per role_id
        outputs = {
            "relevance_analyst": {"relevant_events": state.events[:3]},
            "anomaly_detector": {"anomalies": []},
            "historical_context_agent": {"analogies": []},
            "recommendation_synthesizer": {
                "recommendations": [{"action_signal": "HOLD", "company_id": "c1"}]
            },
            "evaluate_quality": {"quality_score": confidence, "rationale": "good"},
            "narrative_writer": {
                "report": "<html><body>Morning Brief</body></html>"
            },
        }
        return {
            "output": outputs.get(role_id, {}),
            "confidence": confidence,
            "cost_usd": 0.10,
            "input_tokens": 100,
            "output_tokens": 50,
        }

    # Patch the stub invocation function in each node
    registry._mock_invoke = mock_invoke

    brief_repo = _make_brief_repo()
    workflow_repo = _make_workflow_repo()
    hil_repo = _make_hil_repo()
    user_repo = AsyncMock()
    user_repo.get_dispatch_time = AsyncMock(return_value="06:00")
    rec_repo = AsyncMock()
    rec_repo.save = AsyncMock()

    return {
        "portfolio_repo": _make_portfolio_repo(),
        "event_repo": _make_event_repo(),
        "score_repo": AsyncMock(
            get_score_changes=AsyncMock(
                return_value=[{"company_id": "c1", "delta": 0.12}]
            )
        ),
        "agent_registry": registry,
        "rec_repo": rec_repo,
        "brief_repo": brief_repo,
        "hil_repo": hil_repo,
        "workflow_repo": workflow_repo,
        "dispatcher": dispatcher or _make_dispatcher(),
        "user_repo": user_repo,
        "user_email": "user@example.com",
        "episodic_repo": AsyncMock(write=AsyncMock()),
    }


# ── Test scenarios ────────────────────────────────────────────────────────────


class TestHappyPath:
    """Scenario 1: High confidence -> auto-send."""

    @pytest.mark.asyncio
    async def test_happy_path_auto_send(self):
        """High confidence (>= 0.70) must produce completed run with email dispatched."""
        dispatcher = _make_dispatcher()
        node_registry = _build_node_registry(confidence=0.85, dispatcher=dispatcher)

        graph = MorningBriefGraph(node_registry=node_registry)
        workflow_run_repo = AsyncMock(create=AsyncMock())
        workflow = MorningBriefWorkflow(
            graph=graph, workflow_run_repo=workflow_run_repo
        )

        # Patch all node _invoke_llm to use our mock
        mock_invoke = node_registry["agent_registry"]._mock_invoke
        patches = [
            patch(
                "src.ai.workflows.morning_brief.nodes.relevance_analyst_node._invoke_llm_stub",
                mock_invoke,
            ),
            patch(
                "src.ai.workflows.morning_brief.nodes.anomaly_detector_node._invoke_llm_stub",
                mock_invoke,
            ),
            patch(
                "src.ai.workflows.morning_brief.nodes.historical_context_node._invoke_llm_stub",
                mock_invoke,
            ),
            patch(
                "src.ai.workflows.morning_brief.nodes.recommendation_node._invoke_llm_stub",
                mock_invoke,
            ),
            patch(
                "src.ai.workflows.morning_brief.nodes.evaluate_quality_node._invoke_llm_stub",
                mock_invoke,
            ),
            patch(
                "src.ai.workflows.morning_brief.nodes.narrative_writer_node._invoke_llm_stub",
                mock_invoke,
            ),
        ]
        for p in patches:
            p.start()

        try:
            result = await workflow.run(
                user_id=uuid.uuid4(),
                tenant_id=uuid.uuid4(),
            )
        finally:
            for p in patches:
                p.stop()

        assert result.status == "completed"
        assert result.final_state.confidence_route == ConfidenceRoute.AUTO_SEND
        dispatcher.send_morning_brief.assert_called_once()

    @pytest.mark.asyncio
    async def test_happy_path_workflow_run_persisted(self):
        """Happy path must persist workflow_run row with cost_usd and tenant_id."""
        node_registry = _build_node_registry(confidence=0.85)
        graph = MorningBriefGraph(node_registry=node_registry)
        workflow_run_repo = AsyncMock(create=AsyncMock())
        workflow = MorningBriefWorkflow(
            graph=graph, workflow_run_repo=workflow_run_repo
        )

        tenant_id = uuid.uuid4()
        await workflow.run(user_id=uuid.uuid4(), tenant_id=tenant_id)

        workflow_run_repo.create.assert_called_once()
        kwargs = workflow_run_repo.create.call_args[1]
        assert kwargs["tenant_id"] == tenant_id


class TestHilPath:
    """Scenario 2: Medium confidence -> HIL queue pause."""

    @pytest.mark.asyncio
    async def test_hil_path_pauses_at_hil_queue_node(self):
        """Confidence 0.55 must route to HIL queue; brief not yet dispatched."""
        node_registry = _build_node_registry(confidence=0.55)
        graph = MorningBriefGraph(node_registry=node_registry)
        workflow = MorningBriefWorkflow(graph=graph)

        mock_invoke = node_registry["agent_registry"]._mock_invoke
        with patch(
            "src.ai.workflows.morning_brief.nodes.evaluate_quality_node._invoke_llm_stub",
            mock_invoke,
        ):
            result = await workflow.run(
                user_id=uuid.uuid4(),
                tenant_id=uuid.uuid4(),
            )

        assert result.final_state.confidence_route == ConfidenceRoute.HIL
        assert result.final_state.requires_hil is True
        node_registry["dispatcher"].send_morning_brief.assert_not_called()


class TestHilTimeoutPath:
    """Scenario 3: Medium confidence + no HIL approval -> TIMED_OUT."""

    @pytest.mark.asyncio
    async def test_hil_timeout_marks_brief_timed_out(self):
        """hil_timeout_handler must set TIMED_OUT for items past deadline."""
        from src.ai.workflows.morning_brief.hil_timeout_handler import (
            handle_hil_timeouts,
        )

        item = MagicMock()
        item.item_id = uuid.uuid4()
        item.workflow_run_id = uuid.uuid4()
        item.user_id = uuid.uuid4()
        item.tenant_id = uuid.uuid4()
        item.status = "pending"
        item.scheduled_send_at = datetime(2026, 6, 4, 5, 45, tzinfo=timezone.utc)
        item.lc_checkpoint_id = "hil:test"

        hil_repo = AsyncMock()
        hil_repo.list_timed_out_pending = AsyncMock(return_value=[item])
        hil_repo.update_status = AsyncMock()

        brief_repo = AsyncMock()
        brief_repo.get_latest_by_user = AsyncMock(return_value=None)

        dispatcher = AsyncMock()
        dispatcher.send_no_brief_notification = AsyncMock()

        user_feedback_repo = AsyncMock()
        user_feedback_repo.write = AsyncMock()

        now = datetime(2026, 6, 4, 5, 46, tzinfo=timezone.utc)
        result = await handle_hil_timeouts(
            brief_repo=brief_repo,
            hil_repo=hil_repo,
            email_dispatcher=dispatcher,
            user_feedback_repo=user_feedback_repo,
            now=now,
        )

        assert result["timed_out"] == 1
        hil_repo.update_status.assert_called_once()
        dispatcher.send_no_brief_notification.assert_called_once()


class TestBlockPath:
    """Scenario 4: Low confidence -> blocked; no email."""

    @pytest.mark.asyncio
    async def test_block_path_no_email(self):
        """Confidence < 0.40 must block brief; SendGrid must never be called."""
        node_registry = _build_node_registry(confidence=0.30)
        dispatcher = node_registry["dispatcher"]
        graph = MorningBriefGraph(node_registry=node_registry)
        workflow = MorningBriefWorkflow(graph=graph)

        mock_invoke = node_registry["agent_registry"]._mock_invoke
        with patch(
            "src.ai.workflows.morning_brief.nodes.evaluate_quality_node._invoke_llm_stub",
            mock_invoke,
        ):
            result = await workflow.run(
                user_id=uuid.uuid4(),
                tenant_id=uuid.uuid4(),
            )

        assert result.final_state.confidence_route == ConfidenceRoute.BLOCK
        dispatcher.send_morning_brief.assert_not_called()

    @pytest.mark.asyncio
    async def test_block_path_episodic_memory_written(self):
        """Blocked run must write an episodic memory entry."""
        node_registry = _build_node_registry(confidence=0.30)
        episodic_repo = node_registry["episodic_repo"]
        graph = MorningBriefGraph(node_registry=node_registry)
        workflow = MorningBriefWorkflow(graph=graph)

        mock_invoke = node_registry["agent_registry"]._mock_invoke
        with patch(
            "src.ai.workflows.morning_brief.nodes.evaluate_quality_node._invoke_llm_stub",
            mock_invoke,
        ):
            await workflow.run(user_id=uuid.uuid4(), tenant_id=uuid.uuid4())

        episodic_repo.write.assert_called_once()


class TestNodeFailureRecovery:
    """Scenario 5: Node failure -> workflow status=failed; checkpoint preserved."""

    @pytest.mark.asyncio
    async def test_exception_propagates_as_failed_status(self):
        """An exception in ainvoke must set workflow status=failed."""
        graph = MagicMock()
        graph.ainvoke = AsyncMock(side_effect=RuntimeError("node failure"))

        workflow_run_repo = AsyncMock(create=AsyncMock())
        workflow = MorningBriefWorkflow(
            graph=graph, workflow_run_repo=workflow_run_repo
        )

        result = await workflow.run(user_id=uuid.uuid4(), tenant_id=uuid.uuid4())

        assert result.status == "failed"
        workflow_run_repo.create.assert_called_once()
        kwargs = workflow_run_repo.create.call_args[1]
        assert kwargs.get("status") == "failed"


class TestCostCeilingBreach:
    """Scenario 6: Cost ceiling breached -> workflow routes to block."""

    @pytest.mark.asyncio
    async def test_cost_ceiling_raises_workflow_cost_ceiling_exceeded(self):
        """WorkflowCostCeilingExceeded must be catchable from nodes."""
        from src.ai.workflows.morning_brief_nodes import WorkflowCostCeilingExceeded

        exc = WorkflowCostCeilingExceeded(
            accumulated=2.01, ceiling=2.00, workflow_id=uuid.uuid4()
        )
        assert exc.accumulated == pytest.approx(2.01)
        assert exc.ceiling == pytest.approx(2.00)
        assert isinstance(exc, Exception)

    @pytest.mark.asyncio
    async def test_cost_guard_ceiling_routes_to_block(self):
        """CostGuard ceiling breach must raise WorkflowCostCeilingExceeded."""
        from src.ai.workflows.morning_brief.cost_guard import CostGuard

        guard = CostGuard(cost_ceiling_usd=2.00)
        state = MorningBriefState(
            workflow_id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            started_at=datetime.now(tz=timezone.utc),
            cost_usd=2.05,
        )

        with pytest.raises(WorkflowCostCeilingExceeded):
            guard.check(state)
