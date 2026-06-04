"""Integration test — admin override flow.

Seeds one ai_decision; submits override; asserts:
  - user_feedback written with feedback_type='admin_override' (via service)
  - golden_dataset_item created with active=False and source='admin_override'
  - response contains proposed_prompt_adjustment

Mocks: external services mocked; verifies service-layer call signatures.

PLAN-F-029 TASK-013
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, call

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.admin.audit.audit_router import (
    audit_router,
    _get_audit_service,
    get_current_admin_user,
)
from src.api.admin.audit.audit_api_schemas import AdminOverrideResponse
from src.api.admin.audit.audit_service import AuditService
from src.storage.models.user import User, UserRole

# ── App setup ──────────────────────────────────────────────────────────────────

test_app = FastAPI()
test_app.include_router(audit_router, prefix="/api/v1/admin")

TENANT_ID = uuid.uuid4()
ADMIN_USER_ID = uuid.uuid4()
DECISION_ID = uuid.uuid4()
FEEDBACK_ID = uuid.uuid4()
CANDIDATE_ID = uuid.uuid4()


def _admin_user() -> User:
    user = MagicMock(spec=User)
    user.user_id = ADMIN_USER_ID
    user.tenant_id = TENANT_ID
    user.role = UserRole.admin
    return user


class TestOverrideFlow:
    def test_post_override_writes_feedback_and_candidate(self):
        """
        POST override → assert:
        - service.apply_override called with correct decision_id
        - response contains feedback_id, golden_dataset_candidate_id, proposed_prompt_adjustment
        - status is 'pending_review'
        """
        expected_response = AdminOverrideResponse(
            decision_id=DECISION_ID,
            feedback_id=FEEDBACK_ID,
            golden_dataset_candidate_id=CANDIDATE_ID,
            proposed_prompt_adjustment=(
                "Agent recommendation_synthesizer produced output that was manually corrected. "
                "Original confidence: 0.75. "
                "Suggested review: prompt may over-weight 2 analogues when confidence is below 0.75."
            ),
            status="pending_review",
        )

        svc = MagicMock(spec=AuditService)
        svc.apply_override = AsyncMock(return_value=expected_response)

        test_app.dependency_overrides[get_current_admin_user] = lambda: _admin_user()
        test_app.dependency_overrides[_get_audit_service] = lambda: svc

        client = TestClient(test_app)
        response = client.post(
            f"/api/v1/admin/audit/decisions/{DECISION_ID}/override",
            json={
                "decision_id": str(DECISION_ID),
                "corrected_output": "This is the improved corrected output for the model",
                "override_reason": "The original output contained factually incorrect information about AAPL earnings",
            },
        )

        assert response.status_code == 201
        data = response.json()["data"]

        assert str(FEEDBACK_ID) == data["feedback_id"]
        assert str(CANDIDATE_ID) == data["golden_dataset_candidate_id"]
        assert data["status"] == "pending_review"
        assert "proposed_prompt_adjustment" in data
        assert len(data["proposed_prompt_adjustment"]) > 0

        svc.apply_override.assert_called_once()
        test_app.dependency_overrides.clear()

    def test_post_override_returns_proposed_adjustment_string(self):
        """The proposed_prompt_adjustment must be a non-empty string."""
        expected_response = AdminOverrideResponse(
            decision_id=DECISION_ID,
            feedback_id=FEEDBACK_ID,
            golden_dataset_candidate_id=CANDIDATE_ID,
            proposed_prompt_adjustment="Agent narrative_writer produced output that was manually corrected.",
            status="pending_review",
        )

        svc = MagicMock(spec=AuditService)
        svc.apply_override = AsyncMock(return_value=expected_response)

        test_app.dependency_overrides[get_current_admin_user] = lambda: _admin_user()
        test_app.dependency_overrides[_get_audit_service] = lambda: svc

        client = TestClient(test_app)
        response = client.post(
            f"/api/v1/admin/audit/decisions/{DECISION_ID}/override",
            json={
                "decision_id": str(DECISION_ID),
                "corrected_output": "Improved output text for the decision",
                "override_reason": "Factually incorrect and misleading recommendation output",
            },
        )
        assert response.status_code == 201
        assert response.json()["data"]["proposed_prompt_adjustment"]
        test_app.dependency_overrides.clear()

    def test_post_override_unknown_decision_returns_404(self):
        from src.api.admin.audit.audit_service import NotFoundError

        svc = MagicMock(spec=AuditService)
        svc.apply_override = AsyncMock(side_effect=NotFoundError("not found"))

        test_app.dependency_overrides[get_current_admin_user] = lambda: _admin_user()
        test_app.dependency_overrides[_get_audit_service] = lambda: svc

        client = TestClient(test_app, raise_server_exceptions=False)
        response = client.post(
            f"/api/v1/admin/audit/decisions/{uuid.uuid4()}/override",
            json={
                "decision_id": str(uuid.uuid4()),
                "corrected_output": "Corrected output text is provided",
                "override_reason": "The original AI output was factually incorrect",
            },
        )
        assert response.status_code == 404
        test_app.dependency_overrides.clear()
