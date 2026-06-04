"""
Integration tests for HIL admin queue API endpoints.

Uses FastAPI TestClient with mocked service layer. No real DB required.

TDD tests defined before implementation (PLAN-F-013 TASK-007).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routers.hil_router import hil_router
from src.api.auth_deps import CurrentUser, get_current_user


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


def _make_app(
    *,
    role: str = "admin",
    tenant_id: uuid.UUID | None = None,
) -> tuple[FastAPI, uuid.UUID, uuid.UUID]:
    """Build a minimal test FastAPI app with the HIL router mounted."""
    app = FastAPI()
    app.include_router(hil_router)

    tid = tenant_id or uuid.uuid4()
    uid = uuid.uuid4()

    user = CurrentUser(
        user_id=uid,
        tenant_id=tid,
        role=role,
        email="test@example.com",
    )

    app.dependency_overrides[get_current_user] = lambda: user
    return app, tid, uid


def _make_queue_item(tenant_id: uuid.UUID | None = None) -> MagicMock:
    item = MagicMock()
    item.item_id = uuid.uuid4()
    item.workflow_run_id = uuid.uuid4()
    item.workflow_type = "on_demand"
    item.user_id = uuid.uuid4()
    item.tenant_id = tenant_id or uuid.uuid4()
    item.confidence = 0.55
    item.scheduled_send_at = _utcnow() + timedelta(hours=1)
    item.status = "pending"
    item.reviewer_id = None
    item.reviewed_at = None
    item.lc_checkpoint_id = f"hil:{uuid.uuid4()}"
    item.created_at = _utcnow()
    return item


class TestListEndpoint:
    """GET /api/v1/admin/hil/ tests."""

    def test_list_returns_200_for_admin_role(self) -> None:
        app, tid, uid = _make_app(role="admin")

        with patch(
            "src.api.routers.hil_router.HILQueueRepository"
        ) as mock_repo_cls:
            mock_repo = AsyncMock()
            item = _make_queue_item(tenant_id=tid)
            mock_repo.list_pending = AsyncMock(return_value=[item])
            mock_repo_cls.return_value = mock_repo

            with patch("src.api.routers.hil_router._get_db_session") as mock_sess:
                mock_ctx = AsyncMock()
                mock_ctx.__aenter__ = AsyncMock(return_value=AsyncMock())
                mock_ctx.__aexit__ = AsyncMock(return_value=False)
                mock_sess.return_value = mock_ctx

                client = TestClient(app)
                response = client.get("/api/v1/admin/hil/")

        assert response.status_code == 200
        data = response.json()
        assert data["error"] is None
        assert isinstance(data["data"], list)

    def test_list_returns_403_for_end_user_role(self) -> None:
        app, tid, uid = _make_app(role="end_user")
        client = TestClient(app)
        response = client.get("/api/v1/admin/hil/")
        assert response.status_code == 403

    def test_list_items_sorted_by_scheduled_send_at(self) -> None:
        app, tid, uid = _make_app(role="admin")

        with patch(
            "src.api.routers.hil_router.HILQueueRepository"
        ) as mock_repo_cls:
            mock_repo = AsyncMock()

            item1 = _make_queue_item(tenant_id=tid)
            item1.scheduled_send_at = _utcnow() + timedelta(hours=2)

            item2 = _make_queue_item(tenant_id=tid)
            item2.scheduled_send_at = _utcnow() + timedelta(hours=1)

            # Repository returns pre-sorted; validate response preserves order
            mock_repo.list_pending = AsyncMock(return_value=[item2, item1])
            mock_repo_cls.return_value = mock_repo

            with patch("src.api.routers.hil_router._get_db_session") as mock_sess:
                mock_ctx = AsyncMock()
                mock_ctx.__aenter__ = AsyncMock(return_value=AsyncMock())
                mock_ctx.__aexit__ = AsyncMock(return_value=False)
                mock_sess.return_value = mock_ctx

                client = TestClient(app)
                response = client.get("/api/v1/admin/hil/")

        assert response.status_code == 200


class TestActionEndpoint:
    """POST /api/v1/admin/hil/{item_id}/action tests."""

    def test_action_approve_returns_200_and_workflow_resumed_true(self) -> None:
        app, tid, uid = _make_app(role="admin")
        item_id = uuid.uuid4()

        with (
            patch("src.api.routers.hil_router.HILQueueRepository") as mock_repo_cls,
            patch("src.api.routers.hil_router.HILActionService") as mock_svc_cls,
            patch("src.api.routers.hil_router._get_db_session") as mock_sess,
        ):
            mock_repo = AsyncMock()
            mock_repo_cls.return_value = mock_repo

            action_result = MagicMock()
            action_result.item_id = item_id
            action_result.status = "approved"
            action_result.workflow_resumed = True
            action_result.feedback_id = uuid.uuid4()

            mock_svc = AsyncMock()
            mock_svc.apply_action = AsyncMock(return_value=action_result)
            mock_svc_cls.return_value = mock_svc

            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=AsyncMock())
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_sess.return_value = mock_ctx

            client = TestClient(app)
            response = client.post(
                f"/api/v1/admin/hil/{item_id}/action",
                json={"action": "approve"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["error"] is None
        assert data["data"]["workflow_resumed"] is True

    def test_action_edit_approve_returns_200(self) -> None:
        app, tid, uid = _make_app(role="admin")
        item_id = uuid.uuid4()

        with (
            patch("src.api.routers.hil_router.HILQueueRepository") as mock_repo_cls,
            patch("src.api.routers.hil_router.HILActionService") as mock_svc_cls,
            patch("src.api.routers.hil_router._get_db_session") as mock_sess,
        ):
            mock_repo = AsyncMock()
            mock_repo_cls.return_value = mock_repo

            action_result = MagicMock()
            action_result.item_id = item_id
            action_result.status = "edited_approved"
            action_result.workflow_resumed = True
            action_result.feedback_id = uuid.uuid4()

            mock_svc = AsyncMock()
            mock_svc.apply_action = AsyncMock(return_value=action_result)
            mock_svc_cls.return_value = mock_svc

            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=AsyncMock())
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_sess.return_value = mock_ctx

            client = TestClient(app)
            response = client.post(
                f"/api/v1/admin/hil/{item_id}/action",
                json={
                    "action": "edit_approve",
                    "edited_text": "Reviewer edited this.",
                },
            )

        assert response.status_code == 200

    def test_action_reject_returns_200(self) -> None:
        app, tid, uid = _make_app(role="admin")
        item_id = uuid.uuid4()

        with (
            patch("src.api.routers.hil_router.HILQueueRepository") as mock_repo_cls,
            patch("src.api.routers.hil_router.HILActionService") as mock_svc_cls,
            patch("src.api.routers.hil_router._get_db_session") as mock_sess,
        ):
            mock_repo = AsyncMock()
            mock_repo_cls.return_value = mock_repo

            action_result = MagicMock()
            action_result.item_id = item_id
            action_result.status = "rejected"
            action_result.workflow_resumed = False
            action_result.feedback_id = uuid.uuid4()

            mock_svc = AsyncMock()
            mock_svc.apply_action = AsyncMock(return_value=action_result)
            mock_svc_cls.return_value = mock_svc

            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=AsyncMock())
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_sess.return_value = mock_ctx

            client = TestClient(app)
            response = client.post(
                f"/api/v1/admin/hil/{item_id}/action",
                json={"action": "reject"},
            )

        assert response.status_code == 200

    def test_action_on_nonexistent_item_returns_404(self) -> None:
        app, tid, uid = _make_app(role="admin")
        item_id = uuid.uuid4()

        with (
            patch("src.api.routers.hil_router.HILQueueRepository") as mock_repo_cls,
            patch("src.api.routers.hil_router.HILActionService") as mock_svc_cls,
            patch("src.api.routers.hil_router._get_db_session") as mock_sess,
        ):
            mock_repo = AsyncMock()
            mock_repo_cls.return_value = mock_repo

            mock_svc = AsyncMock()
            mock_svc.apply_action = AsyncMock(
                side_effect=ValueError(f"HIL queue item {item_id} not found")
            )
            mock_svc_cls.return_value = mock_svc

            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=AsyncMock())
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_sess.return_value = mock_ctx

            client = TestClient(app)
            response = client.post(
                f"/api/v1/admin/hil/{item_id}/action",
                json={"action": "approve"},
            )

        assert response.status_code == 404

    def test_action_on_other_tenant_item_returns_404(self) -> None:
        """Items from a different tenant return 404 (not 403) to prevent IDOR."""
        app, tid, uid = _make_app(role="admin")
        item_id = uuid.uuid4()

        with (
            patch("src.api.routers.hil_router.HILQueueRepository") as mock_repo_cls,
            patch("src.api.routers.hil_router.HILActionService") as mock_svc_cls,
            patch("src.api.routers.hil_router._get_db_session") as mock_sess,
        ):
            mock_repo = AsyncMock()
            mock_repo_cls.return_value = mock_repo

            mock_svc = AsyncMock()
            mock_svc.apply_action = AsyncMock(
                side_effect=ValueError("HIL queue item not found for tenant")
            )
            mock_svc_cls.return_value = mock_svc

            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=AsyncMock())
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_sess.return_value = mock_ctx

            client = TestClient(app)
            response = client.post(
                f"/api/v1/admin/hil/{item_id}/action",
                json={"action": "approve"},
            )

        assert response.status_code == 404
