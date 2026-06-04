"""
Unit tests for MorningBriefState, ConfidenceRoute, and confidence_router.

TDD: written before implementation — PLAN-F-006 TASK-001.

AC covered: AC-003 (confidence routing thresholds)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from src.ai.workflows.morning_brief_state import (
    ConfidenceRoute,
    MorningBriefState,
    confidence_router,
)


def _make_state(**kwargs) -> MorningBriefState:
    defaults = {
        "workflow_id": uuid.uuid4(),
        "tenant_id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "started_at": datetime.now(tz=timezone.utc),
    }
    defaults.update(kwargs)
    return MorningBriefState(**defaults)


class TestConfidenceRouter:
    def test_confidence_router_returns_narrative_writer_when_min_score_gte_0_70(self):
        """Min confidence >= 0.70 must route to narrative_writer (auto-send)."""
        state = _make_state(
            confidence_scores={"analyst": 0.85, "anomaly": 0.70}
        )
        assert confidence_router(state) == "narrative_writer"

    def test_confidence_router_returns_narrative_writer_exactly_at_0_70(self):
        """Min confidence == 0.70 must route to narrative_writer (boundary inclusive)."""
        state = _make_state(confidence_scores={"analyst": 0.70})
        assert confidence_router(state) == "narrative_writer"

    def test_confidence_router_returns_hil_queue_when_min_score_between_0_40_and_0_69(self):
        """Min confidence in [0.40, 0.70) must route to hil_queue."""
        state = _make_state(
            confidence_scores={"analyst": 0.60, "anomaly": 0.55}
        )
        assert confidence_router(state) == "hil_queue"

    def test_confidence_router_returns_hil_queue_exactly_at_0_40(self):
        """Min confidence == 0.40 must route to hil_queue (boundary inclusive)."""
        state = _make_state(confidence_scores={"analyst": 0.40})
        assert confidence_router(state) == "hil_queue"

    def test_confidence_router_returns_hil_queue_just_below_0_70(self):
        """Min confidence 0.69 must route to hil_queue (not narrative_writer)."""
        state = _make_state(confidence_scores={"analyst": 0.69})
        assert confidence_router(state) == "hil_queue"

    def test_confidence_router_returns_block_and_log_when_min_score_below_0_40(self):
        """Min confidence < 0.40 must route to block_and_log."""
        state = _make_state(
            confidence_scores={"analyst": 0.35, "anomaly": 0.20}
        )
        assert confidence_router(state) == "block_and_log"

    def test_confidence_router_returns_block_when_no_scores(self):
        """Empty confidence_scores dict (overall=0.0) must route to block_and_log."""
        state = _make_state(confidence_scores={})
        assert confidence_router(state) == "block_and_log"

    def test_confidence_router_uses_minimum_score(self):
        """Router uses minimum score: one low score among many high ones still blocks."""
        state = _make_state(
            confidence_scores={"analyst": 0.95, "anomaly": 0.85, "narrative": 0.25}
        )
        assert confidence_router(state) == "block_and_log"

    def test_confidence_router_single_score_at_0_39_routes_block(self):
        """Single score 0.39 routes to block (just below 0.40 threshold)."""
        state = _make_state(confidence_scores={"analyst": 0.39})
        assert confidence_router(state) == "block_and_log"


class TestMorningBriefState:
    def test_state_serializes_with_all_default_values(self):
        """State must serialize to JSON without errors using default values."""
        state = _make_state()
        data = state.model_dump()

        assert data["workflow_type"] == "morning_brief"
        assert data["portfolio_state"] is None
        assert data["events"] == []
        assert data["relevant_events"] == []
        assert data["score_changes"] == []
        assert data["anomalies"] == []
        assert data["analogies"] == {}
        assert data["recommendations"] == []
        assert data["report"] is None
        assert data["confidence_scores"] == {}
        assert data["requires_hil"] is False
        assert data["hil_reason"] is None
        assert data["cost_usd"] == 0.0
        assert data["langfuse_trace_id"] is None
        assert data["confidence_route"] is None
        assert data["brief_id"] is None
        assert data["dispatch_time"] == "06:00"

    def test_state_accepts_workflow_id_as_uuid(self):
        """workflow_id field must accept a UUID."""
        wf_id = uuid.uuid4()
        state = _make_state(workflow_id=wf_id)
        assert state.workflow_id == wf_id

    def test_state_confidence_route_accepts_enum(self):
        """confidence_route field must accept ConfidenceRoute enum values."""
        state = _make_state(confidence_route=ConfidenceRoute.AUTO_SEND)
        assert state.confidence_route == ConfidenceRoute.AUTO_SEND

    def test_state_can_set_brief_id(self):
        """brief_id field must accept a UUID value."""
        brief_id = uuid.uuid4()
        state = _make_state(brief_id=brief_id)
        assert state.brief_id == brief_id

    def test_state_cost_usd_defaults_to_zero(self):
        """cost_usd must default to 0.0."""
        state = _make_state()
        assert state.cost_usd == 0.0

    def test_state_model_copy_works_for_updates(self):
        """model_copy(update=...) must return a new state with updated fields."""
        state = _make_state()
        updated = state.model_copy(update={"cost_usd": 1.50, "requires_hil": True})
        assert updated.cost_usd == 1.50
        assert updated.requires_hil is True
        # Original is unchanged (immutable pattern)
        assert state.cost_usd == 0.0
        assert state.requires_hil is False


class TestConfidenceRouteEnum:
    def test_confidence_route_values(self):
        """ConfidenceRoute must have AUTO_SEND, HIL, and BLOCK variants."""
        assert ConfidenceRoute.AUTO_SEND == "auto_send"
        assert ConfidenceRoute.HIL == "hil"
        assert ConfidenceRoute.BLOCK == "block"

    def test_confidence_route_is_string_enum(self):
        """ConfidenceRoute must be a string enum (serializable)."""
        route = ConfidenceRoute.AUTO_SEND
        assert isinstance(route, str)
        assert route == "auto_send"
