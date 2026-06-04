"""
Unit tests for evaluate_quality DeterministicNode (PLAN-F-010 TASK-008).

TDD: written before implementation.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from src.ai.workflows.event_deep_dive.state import DeepDiveWorkflowState, GeoEvent
from src.ai.workflows.state import WorkflowType, WorkflowStatus


def _make_state(confidence_scores: dict, cost_limited: bool = False) -> DeepDiveWorkflowState:
    event_id = uuid.uuid4()
    return DeepDiveWorkflowState(
        workflow_id=uuid.uuid4(),
        workflow_type=WorkflowType.EVENT_DEEP_DIVE,
        tenant_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        started_at=datetime.now(tz=timezone.utc),
        inputs={"event_id": str(event_id)},
        confidence_scores=confidence_scores,
        cost_limited=cost_limited,
    )


class TestEvaluateQualityDeepDive:
    def test_high_confidence_sets_workflow_confidence(self):
        from src.ai.workflows.event_deep_dive.nodes.evaluate_quality import (
            evaluate_quality,
        )

        state = _make_state({"agent-a": 0.8, "agent-b": 0.9})
        result = evaluate_quality(state)
        assert result.confidence_scores["workflow"] == pytest.approx(0.8)

    def test_high_confidence_does_not_set_requires_hil(self):
        from src.ai.workflows.event_deep_dive.nodes.evaluate_quality import (
            evaluate_quality,
        )

        state = _make_state({"agent-a": 0.75, "agent-b": 0.9})
        result = evaluate_quality(state)
        assert result.requires_hil is False

    def test_mid_confidence_sets_requires_hil(self):
        from src.ai.workflows.event_deep_dive.nodes.evaluate_quality import (
            evaluate_quality,
        )

        state = _make_state({"agent-a": 0.55, "agent-b": 0.9})
        result = evaluate_quality(state)
        assert result.requires_hil is True

    def test_low_confidence_sets_blocked_in_confidence_scores(self):
        from src.ai.workflows.event_deep_dive.nodes.evaluate_quality import (
            evaluate_quality,
        )

        state = _make_state({"agent-a": 0.2, "agent-b": 0.9})
        result = evaluate_quality(state)
        assert result.confidence_scores["workflow"] < 0.40

    def test_cost_limited_propagated_from_state(self):
        from src.ai.workflows.event_deep_dive.nodes.evaluate_quality import (
            evaluate_quality,
        )

        state = _make_state({"agent-a": 0.8}, cost_limited=True)
        result = evaluate_quality(state)
        assert result.cost_limited is True

    def test_cost_limited_false_when_not_set(self):
        from src.ai.workflows.event_deep_dive.nodes.evaluate_quality import (
            evaluate_quality,
        )

        state = _make_state({"agent-a": 0.8}, cost_limited=False)
        result = evaluate_quality(state)
        assert result.cost_limited is False


class TestRouteAfterEvaluate:
    def test_auto_store_when_confidence_above_0_7(self):
        from src.ai.workflows.event_deep_dive.routing import route_after_evaluate
        from src.ai.workflows.event_deep_dive.state import DeepDiveWorkflowState

        state = _make_state({"workflow": 0.75})
        result = route_after_evaluate(state)
        assert result == "auto_store"

    def test_auto_store_at_exactly_0_7(self):
        from src.ai.workflows.event_deep_dive.routing import route_after_evaluate

        state = _make_state({"workflow": 0.70})
        result = route_after_evaluate(state)
        assert result == "auto_store"

    def test_hil_queue_when_confidence_between_0_4_and_0_69(self):
        from src.ai.workflows.event_deep_dive.routing import route_after_evaluate

        state = _make_state({"workflow": 0.55})
        result = route_after_evaluate(state)
        assert result == "hil_queue"

    def test_hil_queue_at_exactly_0_4(self):
        from src.ai.workflows.event_deep_dive.routing import route_after_evaluate

        state = _make_state({"workflow": 0.40})
        result = route_after_evaluate(state)
        assert result == "hil_queue"

    def test_blocked_when_confidence_below_0_4(self):
        from src.ai.workflows.event_deep_dive.routing import route_after_evaluate

        state = _make_state({"workflow": 0.25})
        result = route_after_evaluate(state)
        assert result == "blocked"
