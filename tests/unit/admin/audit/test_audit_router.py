"""Unit tests for the Admin AI Audit Console router.

Tests use FastAPI TestClient with dependency overrides.
All endpoints require admin role; non-admin gets 403.

PLAN-F-029 TASK-006
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.admin.audit.audit_router import (
    audit_router,
    _get_audit_service,
    get_current_admin_user,
)
from src.api.admin.audit.audit_api_schemas import (
    AdminOverrideResponse,
    CalibrationSummary,
    PerSignalAccuracy,
    PromptVersionEntry,
    RerunResponse,
    RollbackResponse,
    WorkflowRunDetail,
    WorkflowRunSummary,
)
from src.api.admin.audit.audit_service import AuditService, NotFoundError
from src.ai.decision_log.schemas.ai_decision_schemas import (
    AIDecisionDetail,
    AIDecisionRow,
)
from src.storage.models.user import User, UserRole


# ── Test app setup ─────────────────────────────────────────────────────────────

test_app = FastAPI()
test_app.include_router(audit_router, prefix="/api/v1/admin")

TENANT_ID = uuid.uuid4()
ADMIN_USER_ID = uuid.uuid4()
NON_ADMIN_USER_ID = uuid.uuid4()
DECISION_ID = uuid.uuid4()
WORKFLOW_ID = uuid.uuid4()


def _make_admin_user() -> User:
    user = MagicMock(spec=User)
    user.user_id = ADMIN_USER_ID
    user.tenant_id = TENANT_ID
    user.role = UserRole.admin
    return user


def _make_non_admin_user() -> User:
    user = MagicMock(spec=User)
    user.user_id = NON_ADMIN_USER_ID
    user.tenant_id = TENANT_ID
    user.role = UserRole.end_user
    return user


def _make_decision_row(**kwargs) -> AIDecisionRow:
    return AIDecisionRow(
        decision_id=kwargs.get("decision_id", DECISION_ID),
        agent_role=kwargs.get("agent_role", "narrative_writer"),
        model=kwargs.get("model", "claude-haiku"),
        prompt_version=kwargs.get("prompt_version", "abc1234"),
        confidence=kwargs.get("confidence", 0.85),
        inputs_summary="Summary",
        output_text_truncated="Truncated output",
        action_signal=None,
        company_ticker="AAPL",
        langfuse_trace_url="https://langfuse.example.com/trace/abc",
        workflow_run_id=None,
        created_at=datetime(2026, 6, 4, tzinfo=timezone.utc),
    )


def _make_decision_detail(**kwargs) -> AIDecisionDetail:
    return AIDecisionDetail(
        decision_id=kwargs.get("decision_id", DECISION_ID),
        agent_role="narrative_writer",
        model="claude-haiku",
        prompt_version="abc1234" * 5,
        confidence=0.85,
        inputs_summary="Summary",
        inputs_full='{"event": "full data"}',
        retrieved_analogs=[],
        action_signal=None,
        company_ticker="AAPL",
        output_text="Full output",
        langfuse_trace_url="https://langfuse.example.com/trace/abc",
        workflow_run_id=None,
        created_at=datetime(2026, 6, 4, tzinfo=timezone.utc),
    )


def _make_audit_service_mock() -> MagicMock:
    svc = MagicMock(spec=AuditService)
    return svc


# ── Decision log endpoint tests ────────────────────────────────────────────────

class TestDecisionLogEndpoints:
    def test_get_decisions_non_admin_returns_403(self):
        non_admin = _make_non_admin_user()
        test_app.dependency_overrides[get_current_admin_user] = lambda: (_ for _ in ()).throw(
            Exception("should not reach")
        )
        # Override the base auth to return non-admin
        from src.api.auth.dependencies import get_current_user
        test_app.dependency_overrides[get_current_user] = lambda: non_admin

        # Reset audit service dependency to avoid import errors
        svc = _make_audit_service_mock()
        test_app.dependency_overrides[_get_audit_service] = lambda: svc
        # Remove admin override to test real admin check
        if get_current_admin_user in test_app.dependency_overrides:
            del test_app.dependency_overrides[get_current_admin_user]

        client = TestClient(test_app, raise_server_exceptions=False)
        response = client.get("/api/v1/admin/audit/decisions")
        assert response.status_code == 403
        test_app.dependency_overrides.clear()

    def test_get_decisions_unauthenticated_returns_401(self):
        from src.api.auth.dependencies import get_current_user
        from fastapi import HTTPException, status

        def _raise_401():
            raise HTTPException(status_code=401, detail="Not authenticated")

        test_app.dependency_overrides[get_current_user] = _raise_401
        svc = _make_audit_service_mock()
        test_app.dependency_overrides[_get_audit_service] = lambda: svc

        client = TestClient(test_app, raise_server_exceptions=False)
        response = client.get("/api/v1/admin/audit/decisions")
        assert response.status_code == 401
        test_app.dependency_overrides.clear()

    def test_get_decisions_with_confidence_filter(self):
        admin = _make_admin_user()
        row = _make_decision_row(confidence=0.85)
        svc = _make_audit_service_mock()
        svc.list_decisions = AsyncMock(return_value=([row], None))

        test_app.dependency_overrides[get_current_admin_user] = lambda: admin
        test_app.dependency_overrides[_get_audit_service] = lambda: svc

        client = TestClient(test_app)
        response = client.get(
            "/api/v1/admin/audit/decisions", params={"confidence_min": "0.7"}
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) == 1
        assert data["data"][0]["confidence"] == 0.85
        test_app.dependency_overrides.clear()

    def test_get_decision_by_id_returns_langfuse_url(self):
        admin = _make_admin_user()
        detail = _make_decision_detail()
        svc = _make_audit_service_mock()
        svc.get_decision_detail = AsyncMock(return_value=detail)

        test_app.dependency_overrides[get_current_admin_user] = lambda: admin
        test_app.dependency_overrides[_get_audit_service] = lambda: svc

        client = TestClient(test_app)
        response = client.get(f"/api/v1/admin/audit/decisions/{DECISION_ID}")
        assert response.status_code == 200
        assert "langfuse_trace_url" in response.json()["data"]
        test_app.dependency_overrides.clear()

    def test_get_decision_unknown_id_returns_404(self):
        admin = _make_admin_user()
        svc = _make_audit_service_mock()
        svc.get_decision_detail = AsyncMock(side_effect=NotFoundError("not found"))

        test_app.dependency_overrides[get_current_admin_user] = lambda: admin
        test_app.dependency_overrides[_get_audit_service] = lambda: svc

        client = TestClient(test_app, raise_server_exceptions=False)
        response = client.get(f"/api/v1/admin/audit/decisions/{uuid.uuid4()}")
        assert response.status_code == 404
        test_app.dependency_overrides.clear()

    def test_post_override_returns_201_with_candidate_id(self):
        admin = _make_admin_user()
        override_resp = AdminOverrideResponse(
            decision_id=DECISION_ID,
            feedback_id=uuid.uuid4(),
            golden_dataset_candidate_id=uuid.uuid4(),
            proposed_prompt_adjustment="Review prompt for narrative_writer",
            status="pending_review",
        )
        svc = _make_audit_service_mock()
        svc.apply_override = AsyncMock(return_value=override_resp)

        test_app.dependency_overrides[get_current_admin_user] = lambda: admin
        test_app.dependency_overrides[_get_audit_service] = lambda: svc

        client = TestClient(test_app)
        response = client.post(
            f"/api/v1/admin/audit/decisions/{DECISION_ID}/override",
            json={
                "decision_id": str(DECISION_ID),
                "corrected_output": "This is the corrected output text",
                "override_reason": "The original was factually incorrect and needed correction",
            },
        )
        assert response.status_code == 201
        assert response.json()["data"]["golden_dataset_candidate_id"] is not None
        test_app.dependency_overrides.clear()


# ── Prompt history endpoints ───────────────────────────────────────────────────

class TestPromptHistoryEndpoints:
    def test_get_prompt_history_returns_version_entries(self):
        admin = _make_admin_user()
        entry = PromptVersionEntry(
            version_id="abc1234",
            agent_role="narrative_writer",
            label_applied="production",
            published_at=datetime(2026, 6, 4, tzinfo=timezone.utc),
        )
        svc = _make_audit_service_mock()
        svc.list_prompt_history = AsyncMock(return_value=[entry])

        test_app.dependency_overrides[get_current_admin_user] = lambda: admin
        test_app.dependency_overrides[_get_audit_service] = lambda: svc

        client = TestClient(test_app)
        response = client.get("/api/v1/admin/audit/prompts/narrative_writer/history")
        assert response.status_code == 200
        data = response.json()["data"]
        assert len(data) == 1
        assert data[0]["version_id"] == "abc1234"
        assert "published_at" in data[0]
        test_app.dependency_overrides.clear()

    def test_post_rollback_returns_200_with_effective_at(self):
        admin = _make_admin_user()
        rollback_resp = RollbackResponse(
            agent_role="narrative_writer",
            previous_version="old_sha_1234",
            rolled_back_to="abc1234def",
            effective_at=datetime(2026, 6, 4, 10, 1, tzinfo=timezone.utc),
        )
        svc = _make_audit_service_mock()
        svc.rollback_prompt = AsyncMock(return_value=rollback_resp)

        test_app.dependency_overrides[get_current_admin_user] = lambda: admin
        test_app.dependency_overrides[_get_audit_service] = lambda: svc

        client = TestClient(test_app)
        response = client.post(
            "/api/v1/admin/audit/prompts/narrative_writer/rollback",
            json={"agent_role": "narrative_writer", "to_version": "abc1234def"},
        )
        assert response.status_code == 200
        assert "effective_at" in response.json()["data"]
        test_app.dependency_overrides.clear()


# ── Calibration endpoints ──────────────────────────────────────────────────────

class TestCalibrationEndpoints:
    def test_get_calibration_summary_returns_below_threshold(self):
        admin = _make_admin_user()
        summary = CalibrationSummary(
            window_days=30,
            below_threshold=False,
            threshold=0.3,
            per_signal_accuracy=[
                PerSignalAccuracy(
                    action_signal="HOLD",
                    direction_correct_pct=0.72,
                    mean_confidence=0.8,
                    total_recommendations=100,
                )
            ],
            computed_at=datetime(2026, 6, 4, tzinfo=timezone.utc),
        )
        svc = _make_audit_service_mock()
        svc.get_calibration_summary = AsyncMock(return_value=summary)

        test_app.dependency_overrides[get_current_admin_user] = lambda: admin
        test_app.dependency_overrides[_get_audit_service] = lambda: svc

        client = TestClient(test_app)
        response = client.get("/api/v1/admin/audit/calibration/summary?days=30")
        assert response.status_code == 200
        assert "below_threshold" in response.json()["data"]
        test_app.dependency_overrides.clear()

    def test_get_calibration_with_days_90_delegates_correctly(self):
        admin = _make_admin_user()
        svc = _make_audit_service_mock()
        svc.get_calibration_time_series = AsyncMock(return_value=[])

        test_app.dependency_overrides[get_current_admin_user] = lambda: admin
        test_app.dependency_overrides[_get_audit_service] = lambda: svc

        client = TestClient(test_app)
        response = client.get("/api/v1/admin/audit/calibration?days=90")
        assert response.status_code == 200
        svc.get_calibration_time_series.assert_called_once_with(days=90, action_signal=None)
        test_app.dependency_overrides.clear()


# ── Workflow history endpoints ─────────────────────────────────────────────────

class TestWorkflowHistoryEndpoints:
    def test_get_workflows_returns_paginated_list(self):
        admin = _make_admin_user()
        run = WorkflowRunSummary(
            workflow_id=WORKFLOW_ID,
            workflow_type="mode_b_analysis",
            status="completed",
            started_at=datetime(2026, 6, 4, tzinfo=timezone.utc),
            cost_usd=0.05,
        )
        svc = _make_audit_service_mock()
        svc.list_workflow_runs = AsyncMock(return_value=([run], None))

        test_app.dependency_overrides[get_current_admin_user] = lambda: admin
        test_app.dependency_overrides[_get_audit_service] = lambda: svc

        client = TestClient(test_app)
        response = client.get("/api/v1/admin/audit/workflows")
        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) == 1
        assert data["next_cursor"] is None
        test_app.dependency_overrides.clear()

    def test_get_workflow_detail_returns_invocations_and_tool_calls(self):
        from src.api.admin.audit.audit_api_schemas import AgentInvocationSummary, ToolCallSummary

        admin = _make_admin_user()
        detail = WorkflowRunDetail(
            workflow_id=WORKFLOW_ID,
            workflow_type="mode_b_analysis",
            status="completed",
            started_at=datetime(2026, 6, 4, tzinfo=timezone.utc),
            cost_usd=0.05,
            agent_invocations=[
                AgentInvocationSummary(
                    invocation_id=uuid.uuid4(),
                    agent_role_id="narrative_writer",
                    model_used="claude-haiku",
                    prompt_version="abc1234",
                    cost_usd=0.01,
                    duration_ms=500,
                    input_tokens=100,
                    output_tokens=200,
                    tool_calls=[
                        ToolCallSummary(
                            tool_call_id=uuid.uuid4(),
                            tool_name="search_analogues",
                            duration_ms=100,
                        )
                    ],
                )
            ],
        )
        svc = _make_audit_service_mock()
        svc.get_workflow_detail = AsyncMock(return_value=detail)

        test_app.dependency_overrides[get_current_admin_user] = lambda: admin
        test_app.dependency_overrides[_get_audit_service] = lambda: svc

        client = TestClient(test_app)
        response = client.get(f"/api/v1/admin/audit/workflows/{WORKFLOW_ID}")
        assert response.status_code == 200
        data = response.json()["data"]
        assert len(data["agent_invocations"]) == 1
        assert len(data["agent_invocations"][0]["tool_calls"]) == 1
        test_app.dependency_overrides.clear()

    def test_post_rerun_returns_202_with_new_workflow_id(self):
        admin = _make_admin_user()
        new_wf_id = uuid.uuid4()
        rerun_resp = RerunResponse(
            new_workflow_id=new_wf_id,
            workflow_type="mode_b_analysis",
            dispatched_at=datetime(2026, 6, 4, tzinfo=timezone.utc),
        )
        svc = _make_audit_service_mock()
        svc.rerun_workflow = AsyncMock(return_value=rerun_resp)

        test_app.dependency_overrides[get_current_admin_user] = lambda: admin
        test_app.dependency_overrides[_get_audit_service] = lambda: svc

        client = TestClient(test_app)
        response = client.post(f"/api/v1/admin/audit/workflows/{WORKFLOW_ID}/rerun")
        assert response.status_code == 202
        assert str(new_wf_id) == response.json()["data"]["new_workflow_id"]
        test_app.dependency_overrides.clear()

    def test_post_rerun_unknown_workflow_returns_404(self):
        admin = _make_admin_user()
        svc = _make_audit_service_mock()
        svc.rerun_workflow = AsyncMock(side_effect=NotFoundError("not found"))

        test_app.dependency_overrides[get_current_admin_user] = lambda: admin
        test_app.dependency_overrides[_get_audit_service] = lambda: svc

        client = TestClient(test_app, raise_server_exceptions=False)
        response = client.post(f"/api/v1/admin/audit/workflows/{uuid.uuid4()}/rerun")
        assert response.status_code == 404
        test_app.dependency_overrides.clear()
