"""
Unit tests for WorkflowTimeoutConfig registry and WorkflowState timeout fields.

PLAN-N-002 TASK-001 — TDD: tests written before implementation.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from src.ai.workflows.state import WorkflowState, WorkflowType
from src.ai.workflows.timeout_guard import WORKFLOW_TIMEOUT_CONFIGS, WorkflowTimeoutConfig


class TestWorkflowTimeoutConfigs:
    def test_workflow_timeout_configs_covers_all_five_workflow_types(self):
        assert len(WORKFLOW_TIMEOUT_CONFIGS) == 5

    def test_morning_brief_hard_limit_is_600s(self):
        cfg = WORKFLOW_TIMEOUT_CONFIGS[WorkflowType.MORNING_BRIEF]
        assert cfg.hard_limit_seconds == 600

    def test_on_demand_hard_limit_is_360s(self):
        cfg = WORKFLOW_TIMEOUT_CONFIGS[WorkflowType.ON_DEMAND]
        assert cfg.hard_limit_seconds == 360

    def test_watchlist_scan_hard_limit_is_480s(self):
        cfg = WORKFLOW_TIMEOUT_CONFIGS[WorkflowType.WATCHLIST_SCAN]
        assert cfg.hard_limit_seconds == 480

    def test_earnings_brief_hard_limit_is_600s(self):
        cfg = WORKFLOW_TIMEOUT_CONFIGS[WorkflowType.EARNINGS_BRIEF]
        assert cfg.hard_limit_seconds == 600

    def test_event_deep_dive_hard_limit_is_900s(self):
        cfg = WORKFLOW_TIMEOUT_CONFIGS[WorkflowType.EVENT_DEEP_DIVE]
        assert cfg.hard_limit_seconds == 900

    def test_soft_limits_leave_30s_grace_window(self):
        for wf_type, cfg in WORKFLOW_TIMEOUT_CONFIGS.items():
            assert cfg.hard_limit_seconds - cfg.soft_limit_seconds == 30, (
                f"{wf_type}: expected 30s grace window, "
                f"got {cfg.hard_limit_seconds - cfg.soft_limit_seconds}"
            )

    def test_p95_targets_within_hard_limits(self):
        for wf_type, cfg in WORKFLOW_TIMEOUT_CONFIGS.items():
            assert cfg.target_seconds_p95 < cfg.hard_limit_seconds, (
                f"{wf_type}: p95={cfg.target_seconds_p95} >= hard={cfg.hard_limit_seconds}"
            )

    def test_morning_brief_soft_limit_is_570s(self):
        cfg = WORKFLOW_TIMEOUT_CONFIGS[WorkflowType.MORNING_BRIEF]
        assert cfg.soft_limit_seconds == 570

    def test_on_demand_soft_limit_is_330s(self):
        cfg = WORKFLOW_TIMEOUT_CONFIGS[WorkflowType.ON_DEMAND]
        assert cfg.soft_limit_seconds == 330

    def test_morning_brief_p95_is_300s(self):
        cfg = WORKFLOW_TIMEOUT_CONFIGS[WorkflowType.MORNING_BRIEF]
        assert cfg.target_seconds_p95 == 300

    def test_on_demand_p95_is_240s(self):
        cfg = WORKFLOW_TIMEOUT_CONFIGS[WorkflowType.ON_DEMAND]
        assert cfg.target_seconds_p95 == 240

    def test_watchlist_scan_p95_is_180s(self):
        cfg = WORKFLOW_TIMEOUT_CONFIGS[WorkflowType.WATCHLIST_SCAN]
        assert cfg.target_seconds_p95 == 180

    def test_earnings_brief_p95_is_240s(self):
        cfg = WORKFLOW_TIMEOUT_CONFIGS[WorkflowType.EARNINGS_BRIEF]
        assert cfg.target_seconds_p95 == 240

    def test_event_deep_dive_p95_is_420s(self):
        cfg = WORKFLOW_TIMEOUT_CONFIGS[WorkflowType.EVENT_DEEP_DIVE]
        assert cfg.target_seconds_p95 == 420

    def test_workflow_timeout_config_is_frozen(self):
        cfg = WORKFLOW_TIMEOUT_CONFIGS[WorkflowType.MORNING_BRIEF]
        with pytest.raises((AttributeError, TypeError)):
            cfg.hard_limit_seconds = 999  # type: ignore[misc]

    def test_all_configs_have_correct_workflow_type_field(self):
        for wf_type, cfg in WORKFLOW_TIMEOUT_CONFIGS.items():
            assert cfg.workflow_type == wf_type


class TestWorkflowStateTimeoutFields:
    def _make_state(self, **kwargs) -> WorkflowState:
        return WorkflowState(
            workflow_id=uuid4(),
            workflow_type=WorkflowType.ON_DEMAND,
            tenant_id=uuid4(),
            user_id=uuid4(),
            started_at=datetime.now(tz=timezone.utc),
            **kwargs,
        )

    def test_workflow_state_timeout_at_defaults_none(self):
        state = self._make_state()
        assert state.timeout_at is None

    def test_workflow_state_partial_result_defaults_false(self):
        state = self._make_state()
        assert state.partial_result is False

    def test_workflow_state_timeout_fields_serialize_to_json(self):
        now = datetime.now(tz=timezone.utc)
        state = self._make_state(timeout_at=now, partial_result=True)
        json_str = state.model_dump_json()
        parsed = json.loads(json_str)
        assert parsed["partial_result"] is True
        # timeout_at serialized as ISO-8601 string
        assert isinstance(parsed["timeout_at"], str)
        assert "T" in parsed["timeout_at"]

    def test_workflow_state_timeout_at_accepts_datetime(self):
        now = datetime.now(tz=timezone.utc)
        state = self._make_state(timeout_at=now)
        assert state.timeout_at == now

    def test_workflow_state_partial_result_can_be_set_true(self):
        state = self._make_state(partial_result=True)
        assert state.partial_result is True

    def test_workflow_state_model_dump_includes_timeout_at_none(self):
        state = self._make_state()
        dumped = state.model_dump()
        assert "timeout_at" in dumped
        assert dumped["timeout_at"] is None

    def test_workflow_state_model_dump_includes_partial_result_false(self):
        state = self._make_state()
        dumped = state.model_dump()
        assert "partial_result" in dumped
        assert dumped["partial_result"] is False

    def test_workflow_state_roundtrip_json_timeout_at_none(self):
        state = self._make_state()
        json_str = state.model_dump_json()
        parsed = json.loads(json_str)
        assert parsed["timeout_at"] is None
