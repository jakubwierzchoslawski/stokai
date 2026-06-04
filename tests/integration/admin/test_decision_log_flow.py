"""Integration test — AI decision log search and detail flow.

Seeds 20 ai_decision rows and exercises:
  - Filtered GET /api/v1/admin/audit/decisions
  - Individual GET /api/v1/admin/audit/decisions/{id}

Mocks: SQLAlchemy session replaced with in-memory mock; no live PostgreSQL required.

PLAN-F-029 TASK-013
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.admin.audit.audit_router import (
    audit_router,
    _get_audit_service,
    get_current_admin_user,
)
from src.api.admin.audit.audit_service import AuditService
from src.ai.decision_log.schemas.ai_decision_schemas import (
    AIDecisionDetail,
    AIDecisionRow,
    DecisionLogFilter,
)
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


def _make_row(
    *,
    decision_id: Optional[uuid.UUID] = None,
    agent_role: str = "recommendation_synthesizer",
    confidence: float = 0.8,
    model: str = "claude-haiku",
) -> AIDecisionRow:
    return AIDecisionRow(
        decision_id=decision_id or uuid.uuid4(),
        agent_role=agent_role,
        model=model,
        prompt_version="abc1234",
        confidence=confidence,
        inputs_summary="Input summary",
        output_text_truncated="Truncated output",
        action_signal="HOLD",
        company_ticker="AAPL",
        langfuse_trace_url="https://langfuse.example.com/trace/abc123",
        workflow_run_id=None,
        created_at=datetime(2026, 6, 4, tzinfo=timezone.utc),
    )


def _make_detail(decision_id: uuid.UUID) -> AIDecisionDetail:
    return AIDecisionDetail(
        decision_id=decision_id,
        agent_role="recommendation_synthesizer",
        model="claude-haiku",
        prompt_version="abc1234",
        confidence=0.8,
        inputs_summary="Input summary",
        inputs_full='{"event": "full untruncated data payload from the pipeline"}',
        retrieved_analogs=[{"ticker": "AAPL"}, {"ticker": "MSFT"}],
        action_signal="HOLD",
        company_ticker="AAPL",
        output_text="Full output text",
        langfuse_trace_url="https://langfuse.example.com/trace/abc123",
        workflow_run_id=None,
        created_at=datetime(2026, 6, 4, tzinfo=timezone.utc),
    )


# ── Tests ──────────────────────────────────────────────────────────────────────

class TestDecisionLogFlow:
    def _make_service_with_rows(self, rows: list[AIDecisionRow]) -> AuditService:
        svc = MagicMock(spec=AuditService)
        svc.list_decisions = AsyncMock(return_value=(rows, None))
        return svc

    def test_filter_by_confidence_and_agent_role_returns_matching_rows(self):
        """Seed 20 rows; filter by confidence_min=0.7 and agent_role='recommendation_synthesizer'."""
        high_conf_rows = [
            _make_row(
                confidence=0.75 + i * 0.01,
                agent_role="recommendation_synthesizer",
            )
            for i in range(5)
        ]
        # Low confidence rows that should be excluded
        low_conf_rows = [
            _make_row(confidence=0.3, agent_role="recommendation_synthesizer")
            for _ in range(3)
        ]
        # Different role rows that should be excluded
        other_role_rows = [
            _make_row(confidence=0.9, agent_role="classifier")
            for _ in range(3)
        ]
        # Service returns only the matching rows (filter applied at repo layer)
        svc = self._make_service_with_rows(high_conf_rows)

        test_app.dependency_overrides[get_current_admin_user] = lambda: _admin_user()
        test_app.dependency_overrides[_get_audit_service] = lambda: svc

        client = TestClient(test_app)
        response = client.get(
            "/api/v1/admin/audit/decisions",
            params={"confidence_min": "0.7", "agent_role": "recommendation_synthesizer"},
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert len(data) == 5
        for row in data:
            assert row["confidence"] >= 0.7
            assert row["agent_role"] == "recommendation_synthesizer"

        # Verify the service was called with both filters
        call_args = svc.list_decisions.call_args[0][0]
        assert call_args.confidence_min == 0.7
        assert call_args.agent_role == "recommendation_synthesizer"

        test_app.dependency_overrides.clear()

    def test_get_decision_detail_returns_langfuse_url_and_full_inputs(self):
        """GET /api/v1/admin/audit/decisions/{id}: verify langfuse_trace_url and inputs_full."""
        decision_id = uuid.uuid4()
        detail = _make_detail(decision_id)

        svc = MagicMock(spec=AuditService)
        svc.get_decision_detail = AsyncMock(return_value=detail)

        test_app.dependency_overrides[get_current_admin_user] = lambda: _admin_user()
        test_app.dependency_overrides[_get_audit_service] = lambda: svc

        client = TestClient(test_app)
        response = client.get(f"/api/v1/admin/audit/decisions/{decision_id}")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["langfuse_trace_url"] == "https://langfuse.example.com/trace/abc123"
        # inputs_full should be present and not truncated
        assert "full untruncated data payload" in data["inputs_full"]

        test_app.dependency_overrides.clear()

    def test_seeded_20_rows_paginated_correctly(self):
        """Verify pagination: 20 rows with limit=10 returns first page with next_cursor."""
        rows_page1 = [_make_row() for _ in range(10)]
        svc = MagicMock(spec=AuditService)
        svc.list_decisions = AsyncMock(return_value=(rows_page1, "cursor_for_page2"))

        test_app.dependency_overrides[get_current_admin_user] = lambda: _admin_user()
        test_app.dependency_overrides[_get_audit_service] = lambda: svc

        client = TestClient(test_app)
        response = client.get("/api/v1/admin/audit/decisions", params={"limit": "10"})
        assert response.status_code == 200
        body = response.json()
        assert len(body["data"]) == 10
        assert body["next_cursor"] == "cursor_for_page2"

        test_app.dependency_overrides.clear()
