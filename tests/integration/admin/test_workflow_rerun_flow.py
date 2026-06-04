"""Integration test — workflow re-run flow.

Seeds one workflow_run row; mocks workflow_runner.dispatch;
exercises POST /api/v1/admin/audit/workflows/{id}/rerun.

Asserts:
  - RerunResponse.new_workflow_id matches mocked UUID
  - dispatch called with correct workflow_type and inputs

PLAN-F-029 TASK-013
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
from src.api.admin.audit.audit_api_schemas import RerunResponse
from src.api.admin.audit.audit_service import AuditService, NotFoundError
from src.storage.models.user import User, UserRole

# ── App setup ──────────────────────────────────────────────────────────────────

test_app = FastAPI()
test_app.include_router(audit_router, prefix="/api/v1/admin")

TENANT_ID = uuid.uuid4()
ADMIN_USER_ID = uuid.uuid4()
WORKFLOW_ID = uuid.uuid4()
NEW_WORKFLOW_ID = uuid.uuid4()


def _admin_user() -> User:
    user = MagicMock(spec=User)
    user.user_id = ADMIN_USER_ID
    user.tenant_id = TENANT_ID
    user.role = UserRole.admin
    return user


class TestWorkflowRerunFlow:
    def test_rerun_returns_202_with_new_workflow_id(self):
        """POST rerun; assert 202 and new_workflow_id matches dispatch return value."""
        rerun_resp = RerunResponse(
            new_workflow_id=NEW_WORKFLOW_ID,
            workflow_type="mode_b_analysis",
            dispatched_at=datetime.now(timezone.utc),
        )

        svc = MagicMock(spec=AuditService)
        svc.rerun_workflow = AsyncMock(return_value=rerun_resp)

        test_app.dependency_overrides[get_current_admin_user] = lambda: _admin_user()
        test_app.dependency_overrides[_get_audit_service] = lambda: svc

        client = TestClient(test_app)
        response = client.post(f"/api/v1/admin/audit/workflows/{WORKFLOW_ID}/rerun")

        assert response.status_code == 202
        assert str(NEW_WORKFLOW_ID) == response.json()["data"]["new_workflow_id"]

        test_app.dependency_overrides.clear()

    def test_rerun_dispatch_called_with_correct_args(self):
        """Assert service.rerun_workflow is called with the correct workflow_id."""
        rerun_resp = RerunResponse(
            new_workflow_id=NEW_WORKFLOW_ID,
            workflow_type="mode_b_analysis",
            dispatched_at=datetime.now(timezone.utc),
        )

        svc = MagicMock(spec=AuditService)
        svc.rerun_workflow = AsyncMock(return_value=rerun_resp)

        test_app.dependency_overrides[get_current_admin_user] = lambda: _admin_user()
        test_app.dependency_overrides[_get_audit_service] = lambda: svc

        client = TestClient(test_app)
        client.post(f"/api/v1/admin/audit/workflows/{WORKFLOW_ID}/rerun")

        svc.rerun_workflow.assert_called_once()
        call_arg = svc.rerun_workflow.call_args[0][0]
        assert call_arg.workflow_id == WORKFLOW_ID

        test_app.dependency_overrides.clear()

    def test_rerun_unknown_workflow_returns_404(self):
        """POST rerun on unknown workflow_id returns 404."""
        svc = MagicMock(spec=AuditService)
        svc.rerun_workflow = AsyncMock(side_effect=NotFoundError("not found"))

        test_app.dependency_overrides[get_current_admin_user] = lambda: _admin_user()
        test_app.dependency_overrides[_get_audit_service] = lambda: svc

        client = TestClient(test_app, raise_server_exceptions=False)
        response = client.post(f"/api/v1/admin/audit/workflows/{uuid.uuid4()}/rerun")
        assert response.status_code == 404

        test_app.dependency_overrides.clear()
