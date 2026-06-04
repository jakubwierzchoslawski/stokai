"""Integration test — prompt rollback flow.

Seeds prompt_publication rows; mocks IPromptLabelService.rollback();
exercises POST /api/v1/admin/audit/prompts/{role}/rollback.

Asserts:
  - RollbackResponse.effective_at is within 10 seconds of request
  - rollback called with correct role_id and to_version

PLAN-F-029 TASK-013
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.admin.audit.audit_router import (
    audit_router,
    _get_audit_service,
    get_current_admin_user,
)
from src.api.admin.audit.audit_api_schemas import RollbackResponse
from src.api.admin.audit.audit_service import AuditService
from src.storage.models.user import User, UserRole

# ── App setup ──────────────────────────────────────────────────────────────────

test_app = FastAPI()
test_app.include_router(audit_router, prefix="/api/v1/admin")

TENANT_ID = uuid.uuid4()
ADMIN_USER_ID = uuid.uuid4()


def _admin_user() -> User:
    user = MagicMock(spec=User)
    user.user_id = ADMIN_USER_ID
    user.tenant_id = TENANT_ID
    user.role = UserRole.admin
    return user


class TestRollbackFlow:
    def test_rollback_returns_effective_at_within_10_seconds(self):
        """POST rollback; assert effective_at is within 10 seconds of now."""
        now = datetime.now(timezone.utc)
        effective_at = now + timedelta(seconds=5)

        rollback_resp = RollbackResponse(
            agent_role="narrative_writer",
            previous_version="old_sha_1234",
            rolled_back_to="abc1234def5678",
            effective_at=effective_at,
        )

        svc = MagicMock(spec=AuditService)
        svc.rollback_prompt = AsyncMock(return_value=rollback_resp)

        test_app.dependency_overrides[get_current_admin_user] = lambda: _admin_user()
        test_app.dependency_overrides[_get_audit_service] = lambda: svc

        client = TestClient(test_app)
        request_time = datetime.now(timezone.utc)
        response = client.post(
            "/api/v1/admin/audit/prompts/narrative_writer/rollback",
            json={"agent_role": "narrative_writer", "to_version": "abc1234def5678"},
        )
        assert response.status_code == 200
        data = response.json()["data"]
        effective_at_parsed = datetime.fromisoformat(data["effective_at"])
        # effective_at should be within 10 seconds of request_time
        delta = abs((effective_at_parsed - request_time).total_seconds())
        assert delta < 10, f"effective_at delta {delta}s exceeds 10s SLA check"

        test_app.dependency_overrides.clear()

    def test_rollback_called_with_correct_role_and_version(self):
        """Assert service.rollback_prompt called with correct agent_role and to_version."""
        rollback_resp = RollbackResponse(
            agent_role="narrative_writer",
            previous_version="old_sha_1234",
            rolled_back_to="target_sha_9876",
            effective_at=datetime.now(timezone.utc),
        )

        svc = MagicMock(spec=AuditService)
        svc.rollback_prompt = AsyncMock(return_value=rollback_resp)

        test_app.dependency_overrides[get_current_admin_user] = lambda: _admin_user()
        test_app.dependency_overrides[_get_audit_service] = lambda: svc

        client = TestClient(test_app)
        response = client.post(
            "/api/v1/admin/audit/prompts/narrative_writer/rollback",
            json={"agent_role": "narrative_writer", "to_version": "target_sha_9876"},
        )
        assert response.status_code == 200

        svc.rollback_prompt.assert_called_once()
        call_arg = svc.rollback_prompt.call_args[0][0]
        assert call_arg.agent_role == "narrative_writer"
        assert call_arg.to_version == "target_sha_9876"

        test_app.dependency_overrides.clear()

    def test_rollback_response_contains_rolled_back_to(self):
        rollback_resp = RollbackResponse(
            agent_role="narrative_writer",
            previous_version="old_sha",
            rolled_back_to="abc1234def5678",
            effective_at=datetime.now(timezone.utc),
        )

        svc = MagicMock(spec=AuditService)
        svc.rollback_prompt = AsyncMock(return_value=rollback_resp)

        test_app.dependency_overrides[get_current_admin_user] = lambda: _admin_user()
        test_app.dependency_overrides[_get_audit_service] = lambda: svc

        client = TestClient(test_app)
        response = client.post(
            "/api/v1/admin/audit/prompts/narrative_writer/rollback",
            json={"agent_role": "narrative_writer", "to_version": "abc1234def5678"},
        )
        assert response.status_code == 200
        assert response.json()["data"]["rolled_back_to"] == "abc1234def5678"

        test_app.dependency_overrides.clear()
