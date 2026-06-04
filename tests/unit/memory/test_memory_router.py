"""
Unit tests for the memory FastAPI router (TASK-016).

Uses FastAPI TestClient with dependency overrides to avoid DB access.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.auth_deps import CurrentUser, get_current_user, require_admin
from src.api.memory.memory_router import (
    router,
    _get_memory_service,
    _get_improvement_repo,
    _get_procedural_repo,
)
from src.ai.memory.schemas.feedback_schemas import (
    FeedbackSource,
    FeedbackType,
    ImprovementProposal,
    ProposalStatus,
    UserFeedback,
)
from src.ai.memory.schemas.procedural_schemas import ProceduralPattern


# ── Test app setup ────────────────────────────────────────────────────────────


def _build_app(
    role: str = "end_user",
    memory_service=None,
    improvement_repo=None,
    procedural_repo=None,
) -> FastAPI:
    """Build a test FastAPI app with dependency overrides."""
    app = FastAPI()
    app.include_router(router)

    user_id = uuid.uuid4()
    tenant_id = uuid.uuid4()

    current_user = CurrentUser(
        user_id=user_id,
        tenant_id=tenant_id,
        role=role,
        email=f"{role}@example.com",
    )

    app.dependency_overrides[get_current_user] = lambda: current_user
    if role == "admin":
        app.dependency_overrides[require_admin] = lambda: current_user

    if memory_service is not None:
        app.dependency_overrides[_get_memory_service] = lambda: memory_service
    if improvement_repo is not None:
        app.dependency_overrides[_get_improvement_repo] = lambda: improvement_repo
    if procedural_repo is not None:
        app.dependency_overrides[_get_procedural_repo] = lambda: procedural_repo

    return app


def _make_feedback_response(tenant_id: uuid.UUID | None = None) -> UserFeedback:
    return UserFeedback(
        feedback_id=uuid.uuid4(),
        tenant_id=tenant_id or uuid.uuid4(),
        report_id=uuid.uuid4(),
        feedback_type=FeedbackType.THUMBS_DOWN,
        source=FeedbackSource.IN_APP,
        submitted_at=datetime.now(tz=timezone.utc),
    )


def _make_proposal() -> ImprovementProposal:
    return ImprovementProposal(
        proposal_id=uuid.uuid4(),
        proposal_type="threshold_adjustment",
        description="Test",
        status=ProposalStatus.PENDING,
        created_at=datetime.now(tz=timezone.utc),
        source_feedback_ids=[],
    )


def _make_pattern() -> ProceduralPattern:
    return ProceduralPattern(
        pattern_id=uuid.uuid4(),
        pattern_type="reasoning",
        context_tags=["relevance"],
        pattern_text="Step 1: identify region.",
        authored_by="mined",
        approved_at=None,
        version=1,
        recommended_for_agents=["relevance-analyst"],
        created_at=datetime.now(tz=timezone.utc),
    )


# ── POST /api/v1/memory/feedback ──────────────────────────────────────────────


def test_submit_feedback_thumbs_down_by_end_user_returns_201():
    feedback_row = _make_feedback_response()
    memory_service = AsyncMock()
    memory_service.record_user_feedback = AsyncMock(return_value=feedback_row)

    app = _build_app(role="end_user", memory_service=memory_service)
    client = TestClient(app, raise_server_exceptions=True)

    payload = {
        "report_id": str(uuid.uuid4()),
        "feedback_type": "thumbs_down",
        "source": "in_app",
    }
    response = client.post("/api/v1/memory/feedback", json=payload)

    assert response.status_code == 201
    assert response.json()["data"]["feedback_type"] == "thumbs_down"


def test_submit_feedback_without_authentication_returns_401():
    """Without a Bearer token, the endpoint must return 401."""
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app, raise_server_exceptions=False)

    payload = {"feedback_type": "thumbs_down", "source": "in_app"}
    response = client.post("/api/v1/memory/feedback", json=payload)

    assert response.status_code == 401


# ── GET /api/v1/memory/proposals ──────────────────────────────────────────────


def test_list_proposals_by_non_admin_returns_403():
    """end_user role must not access proposals list."""
    app = FastAPI()
    app.include_router(router)

    # Non-admin user override for get_current_user but NOT require_admin
    current_user = CurrentUser(
        user_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        role="end_user",
        email="user@example.com",
    )
    app.dependency_overrides[get_current_user] = lambda: current_user
    # require_admin is NOT overridden — uses real implementation which checks role

    client = TestClient(app, raise_server_exceptions=False)
    # We need to provide a token (Bearer) but require_admin will reject end_user
    # Since we're overriding get_current_user, it returns end_user → require_admin raises 403
    response = client.get("/api/v1/memory/proposals", headers={"Authorization": "Bearer fake"})

    assert response.status_code == 403


def test_list_proposals_by_admin_returns_list():
    """Admin can access proposals list."""
    proposals = [_make_proposal()]
    improvement_repo = AsyncMock()
    improvement_repo.list_pending = AsyncMock(return_value=proposals)

    app = _build_app(role="admin", improvement_repo=improvement_repo)
    client = TestClient(app, raise_server_exceptions=True)

    response = client.get(
        "/api/v1/memory/proposals",
        headers={"Authorization": "Bearer admin-token"},
    )
    assert response.status_code == 200
    assert isinstance(response.json()["data"], list)


# ── POST /api/v1/memory/proposals/{id}/approve ───────────────────────────────


def test_approve_proposal_by_admin_sets_status_to_approved():
    proposal_id = uuid.uuid4()
    approved_proposal = _make_proposal()
    approved_proposal.status = ProposalStatus.APPROVED

    improvement_repo = AsyncMock()
    improvement_repo.update_status = AsyncMock(return_value=approved_proposal)

    app = _build_app(role="admin", improvement_repo=improvement_repo)
    client = TestClient(app, raise_server_exceptions=True)

    response = client.post(
        f"/api/v1/memory/proposals/{proposal_id}/approve",
        headers={"Authorization": "Bearer admin-token"},
    )
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "approved"


# ── POST /api/v1/memory/patterns/{id}/approve ────────────────────────────────


def test_approve_pattern_by_admin_sets_approved_at():
    pattern_id = uuid.uuid4()
    approved_pattern = _make_pattern()
    approved_pattern.approved_at = datetime.now(tz=timezone.utc)

    procedural_repo = AsyncMock()
    procedural_repo.approve_pattern = AsyncMock(return_value=approved_pattern)

    app = _build_app(role="admin", procedural_repo=procedural_repo)
    client = TestClient(app, raise_server_exceptions=True)

    response = client.post(
        f"/api/v1/memory/patterns/{pattern_id}/approve",
        headers={"Authorization": "Bearer admin-token"},
    )
    assert response.status_code == 200
    assert response.json()["data"]["approved_at"] is not None
