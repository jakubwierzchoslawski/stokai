"""
Unit tests for WatchlistScanState and route_after_quality.

TDD: written before implementation — PLAN-F-008 TASK-001.

AC covered: route returns dispatch/hil_enqueue/block_and_notify at correct
thresholds; scoped_company_ids is union of watchlist+portfolio.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from src.ai.workflows.watchlist_scan_state import (
    WatchlistScanState,
    route_after_quality,
)


def _make_state(**kwargs) -> WatchlistScanState:
    defaults = {
        "workflow_id": uuid.uuid4(),
        "tenant_id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "started_at": datetime.now(tz=timezone.utc),
    }
    defaults.update(kwargs)
    return WatchlistScanState(**defaults)


class TestRouteAfterQuality:
    def test_route_returns_dispatch_when_confidence_gte_0_70(self):
        """overall_confidence >= 0.70 must route to dispatch (auto-send)."""
        state = _make_state(overall_confidence=0.70)
        assert route_after_quality(state) == "dispatch"

    def test_route_returns_dispatch_when_confidence_high(self):
        """overall_confidence = 0.90 routes to dispatch."""
        state = _make_state(overall_confidence=0.90)
        assert route_after_quality(state) == "dispatch"

    def test_route_returns_dispatch_exactly_at_0_70(self):
        """Boundary: overall_confidence == 0.70 must route to dispatch."""
        state = _make_state(overall_confidence=0.70)
        assert route_after_quality(state) == "dispatch"

    def test_route_returns_hil_enqueue_when_confidence_between_0_40_and_0_69(self):
        """overall_confidence in [0.40, 0.70) must route to hil_enqueue."""
        state = _make_state(overall_confidence=0.55)
        assert route_after_quality(state) == "hil_enqueue"

    def test_route_returns_hil_enqueue_exactly_at_0_40(self):
        """Boundary: overall_confidence == 0.40 must route to hil_enqueue."""
        state = _make_state(overall_confidence=0.40)
        assert route_after_quality(state) == "hil_enqueue"

    def test_route_returns_hil_enqueue_just_below_0_70(self):
        """overall_confidence = 0.69 must route to hil_enqueue, not dispatch."""
        state = _make_state(overall_confidence=0.69)
        assert route_after_quality(state) == "hil_enqueue"

    def test_route_returns_block_and_notify_when_confidence_below_0_40(self):
        """overall_confidence < 0.40 must route to block_and_notify."""
        state = _make_state(overall_confidence=0.35)
        assert route_after_quality(state) == "block_and_notify"

    def test_route_returns_block_and_notify_at_zero(self):
        """overall_confidence = 0.0 (default) routes to block_and_notify."""
        state = _make_state()
        assert route_after_quality(state) == "block_and_notify"

    def test_route_returns_block_and_notify_at_0_39(self):
        """overall_confidence = 0.39 (just below threshold) routes to block_and_notify."""
        state = _make_state(overall_confidence=0.39)
        assert route_after_quality(state) == "block_and_notify"


class TestWatchlistScanStateDefaults:
    def test_state_serializes_with_all_default_values(self):
        """State must serialize to dict without errors using default values."""
        state = _make_state()
        data = state.model_dump()

        assert data["workflow_type"] == "watchlist_scan"
        assert data["watchlist_companies"] == []
        assert data["portfolio_companies"] == []
        assert data["scoped_company_ids"] == []
        assert data["today_events"] == []
        assert data["relevant_events"] == []
        assert data["score_changes"] == []
        assert data["anomalies"] == []
        assert data["high_anomaly_company_ids"] == []
        assert data["analogies"] == {}
        assert data["recommendations"] == []
        assert data["report"] is None
        assert data["overall_confidence"] == 0.0
        assert data["confidence_scores"] == {}
        assert data["requires_hil"] is False
        assert data["hil_reason"] is None
        assert data["cost_usd"] == 0.0
        assert data["langfuse_trace_id"] is None
        assert data["brief_id"] is None
        assert data["dispatch_time"] == "18:00"

    def test_state_accepts_workflow_id_as_uuid(self):
        """workflow_id must accept a UUID."""
        wf_id = uuid.uuid4()
        state = _make_state(workflow_id=wf_id)
        assert state.workflow_id == wf_id

    def test_state_can_set_scoped_company_ids(self):
        """scoped_company_ids must accept a list of UUIDs."""
        ids = [uuid.uuid4(), uuid.uuid4()]
        state = _make_state(scoped_company_ids=ids)
        assert state.scoped_company_ids == ids

    def test_state_model_copy_works_for_updates(self):
        """model_copy(update=...) must return a new state with updated fields."""
        state = _make_state()
        updated = state.model_copy(update={"overall_confidence": 0.80, "requires_hil": True})
        assert updated.overall_confidence == 0.80
        assert updated.requires_hil is True
        # Original unchanged
        assert state.overall_confidence == 0.0
        assert state.requires_hil is False

    def test_scoped_company_ids_is_list_not_set(self):
        """scoped_company_ids must be list (serializable to JSON)."""
        ids = [uuid.uuid4(), uuid.uuid4()]
        state = _make_state(scoped_company_ids=ids)
        data = state.model_dump()
        assert isinstance(data["scoped_company_ids"], list)

    def test_high_anomaly_company_ids_is_list(self):
        """high_anomaly_company_ids must be list for JSON serialization."""
        ids = [uuid.uuid4()]
        state = _make_state(high_anomaly_company_ids=ids)
        data = state.model_dump()
        assert isinstance(data["high_anomaly_company_ids"], list)
