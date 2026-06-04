"""
Integration tests for Q&A API router (PLAN-F-027 TASK-005).

Tests:
  - create_session returns session_id
  - create requires auth (401 without token)
  - submit to another user's session → 403
  - streams 'done' event with QAAnswer
  - streams 'cost_limited' event when cost_limited=True

Uses httpx.AsyncClient with FastAPI TestClient-compatible approach.
Mock dependencies injected via app.dependency_overrides.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.api.auth_deps import CurrentUser, get_current_user
from src.ai.qa.response_builder import QAAnswer, QASource
from src.storage.repositories.qa_repository import QASession, QAMessage


# ── Test helpers ───────────────────────────────────────────────────────────────


def make_current_user(user_id=None, tenant_id=None) -> CurrentUser:
    return CurrentUser(
        user_id=user_id or uuid.uuid4(),
        tenant_id=tenant_id or uuid.uuid4(),
        role="end_user",
        email="test@example.com",
    )


def make_mock_qa_repo(session=None, session_id=None, tenant_id=None, user_id=None):
    """Build a mock QARepository."""
    repo = AsyncMock()
    sid = session_id or uuid.uuid4()
    tid = tenant_id or uuid.uuid4()
    uid = user_id or uuid.uuid4()

    mock_session = session or QASession(
        session_id=sid,
        user_id=uid,
        tenant_id=tid,
        created_at=datetime.now(tz=timezone.utc),
        updated_at=datetime.now(tz=timezone.utc),
    )
    repo.create_session = AsyncMock(return_value=mock_session)
    repo.get_session = AsyncMock(return_value=mock_session)
    repo.get_messages = AsyncMock(return_value=[])

    mock_msg = MagicMock()
    mock_msg.message_id = uuid.uuid4()
    repo.append_message = AsyncMock(return_value=mock_msg)

    return repo, mock_session


# ── Tests ──────────────────────────────────────────────────────────────────────


class TestCreateQASession:
    """POST /api/v1/qa/sessions — create a new Q&A session."""

    def test_create_session_returns_session_id(self):
        """create_session returns 201 with session_id."""
        from src.api.routers.qa_router import qa_router, get_qa_repository

        user_id = uuid.uuid4()
        tenant_id = uuid.uuid4()
        session_id = uuid.uuid4()
        current_user = make_current_user(user_id=user_id, tenant_id=tenant_id)
        mock_repo, mock_session = make_mock_qa_repo(
            session_id=session_id, tenant_id=tenant_id, user_id=user_id
        )

        app.dependency_overrides[get_current_user] = lambda: current_user
        app.dependency_overrides[get_qa_repository] = lambda: mock_repo

        try:
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.post("/api/v1/qa/sessions")
            assert resp.status_code == 201
            data = resp.json()
            assert "session_id" in data
        finally:
            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_qa_repository, None)

    def test_create_session_requires_auth(self):
        """POST /api/v1/qa/sessions without token → 403 or 401."""
        # Remove auth override — use real auth which will reject missing token
        app.dependency_overrides.pop(get_current_user, None)

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/api/v1/qa/sessions")
        assert resp.status_code in (401, 403)


class TestSubmitQAMessage:
    """POST /api/v1/qa/sessions/{session_id}/messages — SSE streaming."""

    def test_submit_to_another_users_session_returns_403(self):
        """Submitting to another user's session → 403 (IDOR prevention)."""
        from src.api.routers.qa_router import qa_router, get_qa_repository

        user_id = uuid.uuid4()
        tenant_id = uuid.uuid4()
        session_id = uuid.uuid4()
        current_user = make_current_user(user_id=user_id, tenant_id=tenant_id)

        # get_session returns None → session not owned by this user
        mock_repo = AsyncMock()
        mock_repo.get_session = AsyncMock(return_value=None)
        mock_repo.get_messages = AsyncMock(return_value=[])

        app.dependency_overrides[get_current_user] = lambda: current_user
        app.dependency_overrides[get_qa_repository] = lambda: mock_repo

        try:
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.post(
                f"/api/v1/qa/sessions/{session_id}/messages",
                json={"question": "What is AAPL exposure?"},
            )
            assert resp.status_code == 403
        finally:
            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_qa_repository, None)

    def test_streams_done_event_with_qa_answer(self):
        """Successful Q&A → stream ends with 'done' event containing QAAnswer."""
        from src.api.routers.qa_router import get_qa_repository, get_qa_workflow

        user_id = uuid.uuid4()
        tenant_id = uuid.uuid4()
        session_id = uuid.uuid4()
        current_user = make_current_user(user_id=user_id, tenant_id=tenant_id)

        mock_repo, mock_session = make_mock_qa_repo(
            session_id=session_id, tenant_id=tenant_id, user_id=user_id
        )

        # Build a real QAAnswer for the mock workflow
        expected_answer = QAAnswer(
            answer_text="Your AAPL exposure is 15%.",
            sources=[
                QASource(type="event", id="evt-1", description="AAPL Q1 2026")
            ],
            confidence=0.87,
            cost_usd=0.12,
            cost_limited=False,
        )

        async def mock_workflow_run(state):
            from src.ai.workflows.qa_state import QAWorkflowState
            return state.model_copy(update={"answer": expected_answer})

        mock_workflow = AsyncMock()
        mock_workflow.run = mock_workflow_run

        app.dependency_overrides[get_current_user] = lambda: current_user
        app.dependency_overrides[get_qa_repository] = lambda: mock_repo
        app.dependency_overrides[get_qa_workflow] = lambda: mock_workflow

        try:
            client = TestClient(app, raise_server_exceptions=True)
            with client.stream(
                "POST",
                f"/api/v1/qa/sessions/{session_id}/messages",
                json={"question": "What is AAPL exposure?"},
            ) as resp:
                assert resp.status_code == 200
                content = resp.read().decode()

            # The stream must contain a 'done' event
            assert '"type": "done"' in content or '"type":"done"' in content
        finally:
            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_qa_repository, None)
            app.dependency_overrides.pop(get_qa_workflow, None)

    def test_streams_cost_limited_event_when_cost_limited(self):
        """cost_limited=True answer → stream contains 'cost_limited' event."""
        from src.api.routers.qa_router import get_qa_repository, get_qa_workflow

        user_id = uuid.uuid4()
        tenant_id = uuid.uuid4()
        session_id = uuid.uuid4()
        current_user = make_current_user(user_id=user_id, tenant_id=tenant_id)

        mock_repo, mock_session = make_mock_qa_repo(
            session_id=session_id, tenant_id=tenant_id, user_id=user_id
        )

        cost_limited_answer = QAAnswer(
            answer_text="Partial answer before cost ceiling.",
            sources=[],
            confidence=0.60,
            cost_usd=0.41,
            cost_limited=True,
        )

        async def mock_workflow_run(state):
            return state.model_copy(update={"answer": cost_limited_answer})

        mock_workflow = AsyncMock()
        mock_workflow.run = mock_workflow_run

        app.dependency_overrides[get_current_user] = lambda: current_user
        app.dependency_overrides[get_qa_repository] = lambda: mock_repo
        app.dependency_overrides[get_qa_workflow] = lambda: mock_workflow

        try:
            client = TestClient(app, raise_server_exceptions=True)
            with client.stream(
                "POST",
                f"/api/v1/qa/sessions/{session_id}/messages",
                json={"question": "Tell me about AAPL."},
            ) as resp:
                assert resp.status_code == 200
                content = resp.read().decode()

            assert "cost_limited" in content
        finally:
            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_qa_repository, None)
            app.dependency_overrides.pop(get_qa_workflow, None)
