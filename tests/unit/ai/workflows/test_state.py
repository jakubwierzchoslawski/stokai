"""
Unit tests for WorkflowState Pydantic v2 model and WorkflowStatus enum.

TDD: these tests were written before the implementation and drove the model design.
"""
import json
import uuid
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from src.ai.workflows.state import WorkflowState, WorkflowStatus, WorkflowType


@pytest.fixture()
def minimal_state_kwargs() -> dict:
    """Minimal valid kwargs for constructing a WorkflowState."""
    return {
        "workflow_id": uuid.uuid4(),
        "workflow_type": WorkflowType.ON_DEMAND,
        "tenant_id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "company_id": uuid.uuid4(),
        "started_at": datetime.now(tz=timezone.utc),
    }


class TestWorkflowStateValidation:
    def test_workflow_state_requires_company_id(self, minimal_state_kwargs):
        """WorkflowState with no company_id must raise ValidationError."""
        del minimal_state_kwargs["company_id"]
        with pytest.raises(ValidationError):
            WorkflowState(**minimal_state_kwargs)

    def test_workflow_state_cost_usd_defaults_to_zero(self, minimal_state_kwargs):
        state = WorkflowState(**minimal_state_kwargs)
        assert state.cost_usd == 0.0

    def test_workflow_state_status_defaults_to_running(self, minimal_state_kwargs):
        state = WorkflowState(**minimal_state_kwargs)
        assert state.status == WorkflowStatus.RUNNING

    def test_workflow_state_active_events_defaults_to_empty_list(
        self, minimal_state_kwargs
    ):
        state = WorkflowState(**minimal_state_kwargs)
        assert state.active_events == []

    def test_workflow_state_confidence_scores_defaults_to_empty_dict(
        self, minimal_state_kwargs
    ):
        state = WorkflowState(**minimal_state_kwargs)
        assert state.confidence_scores == {}

    def test_workflow_state_tokens_consumed_defaults_to_empty_dict(
        self, minimal_state_kwargs
    ):
        state = WorkflowState(**minimal_state_kwargs)
        assert state.tokens_consumed == {}

    def test_workflow_state_requires_hil_defaults_to_false(
        self, minimal_state_kwargs
    ):
        state = WorkflowState(**minimal_state_kwargs)
        assert state.requires_hil is False


class TestWorkflowStatusEnum:
    def test_workflow_status_invalid_literal_raises(self):
        """WorkflowStatus('NONSENSE') must raise ValueError."""
        with pytest.raises(ValueError):
            WorkflowStatus("NONSENSE")

    def test_workflow_status_all_valid_values(self):
        for val in ("RUNNING", "COMPLETED", "COST_LIMIT", "TIMEOUT", "BLOCKED", "HIL_PENDING", "FAILED"):
            status = WorkflowStatus(val)
            assert status.value == val


class TestWorkflowStateSerialization:
    def test_workflow_state_serialises_to_json(self, minimal_state_kwargs):
        """model_dump_json() must not raise; UUID fields serialize as strings."""
        state = WorkflowState(**minimal_state_kwargs)
        raw = state.model_dump_json()
        assert isinstance(raw, str)
        parsed = json.loads(raw)

        # UUID fields must be strings in JSON
        assert isinstance(parsed["workflow_id"], str)
        assert isinstance(parsed["tenant_id"], str)
        assert isinstance(parsed["user_id"], str)
        assert isinstance(parsed["company_id"], str)

    def test_workflow_state_round_trips_through_json(self, minimal_state_kwargs):
        state = WorkflowState(**minimal_state_kwargs)
        raw = state.model_dump_json()
        restored = WorkflowState.model_validate_json(raw)
        assert restored.workflow_id == state.workflow_id
        assert restored.tenant_id == state.tenant_id
        assert restored.cost_usd == state.cost_usd

    def test_workflow_state_confidence_scores_serialise(self, minimal_state_kwargs):
        minimal_state_kwargs["confidence_scores"] = {"exposure": 0.85}
        state = WorkflowState(**minimal_state_kwargs)
        parsed = json.loads(state.model_dump_json())
        assert parsed["confidence_scores"]["exposure"] == 0.85
