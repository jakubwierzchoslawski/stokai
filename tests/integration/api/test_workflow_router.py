"""
Integration tests for workflow router endpoints.

Tests:
  POST /api/v1/companies/{company_id}/analysis
  GET  /api/v1/workflow-runs/{run_id}

TDD: written before implementation.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI

from src.ai.workflows.state import WorkflowStatus, WorkflowType


def _make_mock_run(
    workflow_id: uuid.UUID | None = None,
    status: str = "RUNNING",
    tenant_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    company_id: uuid.UUID | None = None,
    final_state: dict | None = None,
) -> MagicMock:
    run = MagicMock()
    run.workflow_id = workflow_id or uuid.uuid4()
    run.status = status
    run.tenant_id = tenant_id or uuid.uuid4()
    run.user_id = user_id or uuid.uuid4()
    run.company_id = company_id or uuid.uuid4()
    run.workflow_type = "on_demand"
    run.started_at = datetime.now(tz=timezone.utc)
    run.completed_at = None
    run.cost_usd = 0.0
    run.final_state = final_state
    run.langfuse_trace_id = None
    return run


def _make_current_user(
    user_id: uuid.UUID | None = None,
    tenant_id: uuid.UUID | None = None,
) -> MagicMock:
    user = MagicMock()
    user.user_id = user_id or uuid.uuid4()
    user.tenant_id = tenant_id or uuid.uuid4()
    user.role = "analyst"
    return user


class TestPostAnalysisEndpoint:
    def test_post_analysis_returns_202_with_run_id(self):
        """POST /api/v1/companies/{id}/analysis returns 202 with run_id."""
        from src.api.routers.workflow_router import workflow_router
        from src.api.auth.dependencies import get_current_user

        app = FastAPI()
        app.include_router(workflow_router)

        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        company_id = uuid.uuid4()
        mock_run = _make_mock_run(
            tenant_id=tenant_id, user_id=user_id, company_id=company_id
        )
        mock_user = _make_current_user(user_id=user_id, tenant_id=tenant_id)

        mock_repo = AsyncMock()
        mock_repo.get_active_for_company_user = AsyncMock(return_value=None)
        mock_repo.create = AsyncMock(return_value=mock_run)

        app.dependency_overrides[get_current_user] = lambda: mock_user

        with patch(
            "src.api.routers.workflow_router.WorkflowRunRepository",
            return_value=mock_repo,
        ), patch(
            "src.api.routers.workflow_router.get_db_session",
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=AsyncMock()),
                __aexit__=AsyncMock(return_value=False),
            ),
        ), patch(
            "src.api.routers.workflow_router.on_demand_analysis_task.delay"
        ):
            client = TestClient(app, raise_server_exceptions=False)
            response = client.post(
                f"/api/v1/companies/{company_id}/analysis"
            )

        assert response.status_code == 202
        body = response.json()
        assert "data" in body
        assert "run_id" in body["data"]

    def test_post_analysis_returns_409_when_run_already_active(self):
        """Returns 409 if user already has RUNNING analysis for this company."""
        from src.api.routers.workflow_router import workflow_router
        from src.api.auth.dependencies import get_current_user

        app = FastAPI()
        app.include_router(workflow_router)

        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        company_id = uuid.uuid4()
        mock_user = _make_current_user(user_id=user_id, tenant_id=tenant_id)
        mock_active_run = _make_mock_run(status="RUNNING")

        mock_repo = AsyncMock()
        mock_repo.get_active_for_company_user = AsyncMock(return_value=mock_active_run)

        app.dependency_overrides[get_current_user] = lambda: mock_user

        with patch(
            "src.api.routers.workflow_router.WorkflowRunRepository",
            return_value=mock_repo,
        ), patch(
            "src.api.routers.workflow_router.get_db_session",
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=AsyncMock()),
                __aexit__=AsyncMock(return_value=False),
            ),
        ):
            client = TestClient(app, raise_server_exceptions=False)
            response = client.post(
                f"/api/v1/companies/{company_id}/analysis"
            )

        assert response.status_code == 409

    def test_post_analysis_requires_authentication(self):
        """Unauthenticated request → 401 or 403."""
        from src.api.routers.workflow_router import workflow_router

        app = FastAPI()
        app.include_router(workflow_router)

        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(f"/api/v1/companies/{uuid.uuid4()}/analysis")

        assert response.status_code in (401, 403, 422)

    def test_post_analysis_enqueues_celery_task(self):
        """Task is enqueued with correct company_id and tenant_id."""
        from src.api.routers.workflow_router import workflow_router
        from src.api.auth.dependencies import get_current_user

        app = FastAPI()
        app.include_router(workflow_router)

        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        company_id = uuid.uuid4()
        workflow_id = uuid.uuid4()
        mock_user = _make_current_user(user_id=user_id, tenant_id=tenant_id)
        mock_run = _make_mock_run(
            workflow_id=workflow_id,
            tenant_id=tenant_id,
            user_id=user_id,
            company_id=company_id,
        )

        mock_repo = AsyncMock()
        mock_repo.get_active_for_company_user = AsyncMock(return_value=None)
        mock_repo.create = AsyncMock(return_value=mock_run)

        app.dependency_overrides[get_current_user] = lambda: mock_user

        with patch(
            "src.api.routers.workflow_router.WorkflowRunRepository",
            return_value=mock_repo,
        ), patch(
            "src.api.routers.workflow_router.get_db_session",
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=AsyncMock()),
                __aexit__=AsyncMock(return_value=False),
            ),
        ), patch(
            "src.api.routers.workflow_router.on_demand_analysis_task.delay"
        ) as mock_delay:
            client = TestClient(app, raise_server_exceptions=False)
            client.post(f"/api/v1/companies/{company_id}/analysis")

        mock_delay.assert_called_once()
        call_kwargs = mock_delay.call_args
        assert str(company_id) in str(call_kwargs)


class TestGetWorkflowRunEndpoint:
    def test_get_run_returns_status_for_running_workflow(self):
        """GET /api/v1/workflow-runs/{run_id} returns status."""
        from src.api.routers.workflow_router import workflow_router
        from src.api.auth.dependencies import get_current_user

        app = FastAPI()
        app.include_router(workflow_router)

        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        workflow_id = uuid.uuid4()

        mock_user = _make_current_user(user_id=user_id, tenant_id=tenant_id)
        mock_run = _make_mock_run(
            workflow_id=workflow_id,
            status="RUNNING",
            tenant_id=tenant_id,
            user_id=user_id,
        )

        mock_repo = AsyncMock()
        mock_repo.get = AsyncMock(return_value=mock_run)

        app.dependency_overrides[get_current_user] = lambda: mock_user

        with patch(
            "src.api.routers.workflow_router.WorkflowRunRepository",
            return_value=mock_repo,
        ), patch(
            "src.api.routers.workflow_router.get_db_session",
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=AsyncMock()),
                __aexit__=AsyncMock(return_value=False),
            ),
        ):
            client = TestClient(app, raise_server_exceptions=False)
            response = client.get(f"/api/v1/workflow-runs/{workflow_id}")

        assert response.status_code == 200
        body = response.json()
        assert body["data"]["status"] == "RUNNING"

    def test_get_run_returns_report_when_completed(self):
        """GET run returns report field when status=COMPLETED."""
        from src.api.routers.workflow_router import workflow_router
        from src.api.auth.dependencies import get_current_user

        app = FastAPI()
        app.include_router(workflow_router)

        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        workflow_id = uuid.uuid4()
        report_data = {"sections": ["overview", "risk"]}

        mock_user = _make_current_user(user_id=user_id, tenant_id=tenant_id)
        mock_run = _make_mock_run(
            workflow_id=workflow_id,
            status="COMPLETED",
            tenant_id=tenant_id,
            user_id=user_id,
            final_state={"report": report_data, "status": "COMPLETED"},
        )

        mock_repo = AsyncMock()
        mock_repo.get = AsyncMock(return_value=mock_run)

        app.dependency_overrides[get_current_user] = lambda: mock_user

        with patch(
            "src.api.routers.workflow_router.WorkflowRunRepository",
            return_value=mock_repo,
        ), patch(
            "src.api.routers.workflow_router.get_db_session",
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=AsyncMock()),
                __aexit__=AsyncMock(return_value=False),
            ),
        ):
            client = TestClient(app, raise_server_exceptions=False)
            response = client.get(f"/api/v1/workflow-runs/{workflow_id}")

        assert response.status_code == 200
        body = response.json()
        assert body["data"]["report"] == report_data

    def test_get_run_returns_404_when_not_found(self):
        """GET /api/v1/workflow-runs/{run_id} → 404 when run not found."""
        from src.api.routers.workflow_router import workflow_router
        from src.api.auth.dependencies import get_current_user

        app = FastAPI()
        app.include_router(workflow_router)

        mock_user = _make_current_user()
        mock_repo = AsyncMock()
        mock_repo.get = AsyncMock(return_value=None)

        app.dependency_overrides[get_current_user] = lambda: mock_user

        with patch(
            "src.api.routers.workflow_router.WorkflowRunRepository",
            return_value=mock_repo,
        ), patch(
            "src.api.routers.workflow_router.get_db_session",
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=AsyncMock()),
                __aexit__=AsyncMock(return_value=False),
            ),
        ):
            client = TestClient(app, raise_server_exceptions=False)
            response = client.get(f"/api/v1/workflow-runs/{uuid.uuid4()}")

        assert response.status_code == 404

    def test_get_run_idor_protection_wrong_tenant_returns_404(self):
        """run belonging to different tenant → 404 (IDOR prevention)."""
        from src.api.routers.workflow_router import workflow_router
        from src.api.auth.dependencies import get_current_user

        app = FastAPI()
        app.include_router(workflow_router)

        my_tenant = uuid.uuid4()
        other_tenant = uuid.uuid4()
        workflow_id = uuid.uuid4()

        mock_user = _make_current_user(tenant_id=my_tenant)
        mock_repo = AsyncMock()
        # Repository returns None when tenant_id doesn't match (enforced at repo layer)
        mock_repo.get = AsyncMock(return_value=None)

        app.dependency_overrides[get_current_user] = lambda: mock_user

        with patch(
            "src.api.routers.workflow_router.WorkflowRunRepository",
            return_value=mock_repo,
        ), patch(
            "src.api.routers.workflow_router.get_db_session",
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=AsyncMock()),
                __aexit__=AsyncMock(return_value=False),
            ),
        ):
            client = TestClient(app, raise_server_exceptions=False)
            response = client.get(f"/api/v1/workflow-runs/{workflow_id}")

        assert response.status_code == 404
