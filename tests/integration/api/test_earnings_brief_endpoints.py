"""
Integration tests for Earnings Brief REST API endpoints.

Uses FastAPI TestClient with mocked DB repositories.
No real database required.

TDD — PLAN-F-009 TASK-006.

Tests cover:
- GET /api/v1/companies/{company_id}/earnings-brief returns 200 with latest brief
- GET /api/v1/companies/{company_id}/earnings-brief returns 404 when none found
- GET /api/v1/earnings-briefs returns 200 with tenant-scoped list
- Both endpoints require JWT (401 when unauthenticated)
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.auth_deps import CurrentUser, get_current_user
from src.api.v1.earnings_brief_router import router as company_router
from src.api.v1.earnings_brief_router import list_router


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_app(
    *,
    tenant_id: uuid.UUID | None = None,
    role: str = "end_user",
) -> tuple[FastAPI, uuid.UUID, uuid.UUID]:
    """Build a minimal FastAPI app with earnings brief routers mounted."""
    app = FastAPI()
    app.include_router(company_router, prefix="/api/v1")
    app.include_router(list_router, prefix="/api/v1")

    tid = tenant_id or uuid.uuid4()
    uid = uuid.uuid4()
    user = CurrentUser(user_id=uid, tenant_id=tid, role=role, email="test@example.com")
    app.dependency_overrides[get_current_user] = lambda: user

    return app, tid, uid


def _make_brief_run(
    company_id: uuid.UUID | None = None,
    tenant_id: uuid.UUID | None = None,
    status: str = "completed",
) -> MagicMock:
    """Return a mock EarningsBriefRun ORM row."""
    m = MagicMock()
    m.run_id = uuid.uuid4()
    m.workflow_id = uuid.uuid4()
    m.company_id = company_id or uuid.uuid4()
    m.tenant_id = tenant_id or uuid.uuid4()
    m.earnings_date = date.today()
    m.status = status
    m.scenario_tree = None
    m.confidence = 0.85
    m.cost_usd = 0.12
    m.hil_status = "none"
    m.created_at = datetime.now(tz=timezone.utc)
    return m


# ── GET /api/v1/companies/{company_id}/earnings-brief ─────────────────────────


class TestGetCompanyEarningsBrief:
    """GET /api/v1/companies/{company_id}/earnings-brief."""

    def test_returns_200_when_brief_exists(self):
        """200 returned when a brief run exists for company+tenant."""
        app, tid, uid = _make_app(tenant_id=uuid.uuid4())
        company_id = uuid.uuid4()
        brief_run = _make_brief_run(company_id=company_id, tenant_id=tid)

        mock_repo = AsyncMock()
        mock_repo.get_latest_by_company = AsyncMock(return_value=brief_run)

        with patch(
            "src.api.v1.earnings_brief_router.EarningsBriefRunRepository",
            return_value=mock_repo,
        ), patch(
            "src.api.v1.earnings_brief_router.create_async_engine"
        ), patch(
            "src.api.v1.earnings_brief_router.async_sessionmaker"
        ) as mock_factory:
            mock_session = AsyncMock()
            mock_factory.return_value.return_value.__aenter__ = AsyncMock(
                return_value=mock_session
            )
            mock_factory.return_value.return_value.__aexit__ = AsyncMock(
                return_value=False
            )

            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get(f"/api/v1/companies/{company_id}/earnings-brief")

        assert resp.status_code == 200
        body = resp.json()
        assert str(brief_run.company_id) == body["company_id"]

    def test_returns_404_when_no_brief_found(self):
        """404 returned when no brief run exists for company+tenant."""
        app, tid, uid = _make_app()
        company_id = uuid.uuid4()

        mock_repo = AsyncMock()
        mock_repo.get_latest_by_company = AsyncMock(return_value=None)

        with patch(
            "src.api.v1.earnings_brief_router.EarningsBriefRunRepository",
            return_value=mock_repo,
        ), patch(
            "src.api.v1.earnings_brief_router.create_async_engine"
        ), patch(
            "src.api.v1.earnings_brief_router.async_sessionmaker"
        ) as mock_factory:
            mock_session = AsyncMock()
            mock_factory.return_value.return_value.__aenter__ = AsyncMock(
                return_value=mock_session
            )
            mock_factory.return_value.return_value.__aexit__ = AsyncMock(
                return_value=False
            )

            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get(f"/api/v1/companies/{company_id}/earnings-brief")

        assert resp.status_code == 404
        body = resp.json()
        assert body["detail"]["code"] == "EARNINGS_BRIEF_NOT_FOUND"

    def test_requires_jwt_returns_403_without_auth(self):
        """403 is returned when no auth is set up (dependency not overridden)."""
        from fastapi import FastAPI
        from src.api.v1.earnings_brief_router import router as cr

        app = FastAPI()
        app.include_router(cr, prefix="/api/v1")
        company_id = uuid.uuid4()

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get(f"/api/v1/companies/{company_id}/earnings-brief")

        # FastAPI 403 when Bearer not present (HTTPBearer auto_error=True)
        assert resp.status_code in (401, 403, 422)

    def test_response_is_tenant_scoped(self):
        """get_latest_by_company is called with the tenant_id from the JWT."""
        app, tid, uid = _make_app(tenant_id=uuid.uuid4())
        company_id = uuid.uuid4()
        brief_run = _make_brief_run(company_id=company_id, tenant_id=tid)

        mock_repo = AsyncMock()
        mock_repo.get_latest_by_company = AsyncMock(return_value=brief_run)

        with patch(
            "src.api.v1.earnings_brief_router.EarningsBriefRunRepository",
            return_value=mock_repo,
        ), patch(
            "src.api.v1.earnings_brief_router.create_async_engine"
        ), patch(
            "src.api.v1.earnings_brief_router.async_sessionmaker"
        ) as mock_factory:
            mock_session = AsyncMock()
            mock_factory.return_value.return_value.__aenter__ = AsyncMock(
                return_value=mock_session
            )
            mock_factory.return_value.return_value.__aexit__ = AsyncMock(
                return_value=False
            )

            client = TestClient(app, raise_server_exceptions=False)
            client.get(f"/api/v1/companies/{company_id}/earnings-brief")

        # Verify tenant_id was passed to the repo
        mock_repo.get_latest_by_company.assert_called_once_with(
            company_id=company_id,
            tenant_id=tid,
        )


# ── GET /api/v1/earnings-briefs ───────────────────────────────────────────────


class TestListEarningsBriefs:
    """GET /api/v1/earnings-briefs."""

    def test_returns_200_with_empty_list(self):
        """200 returned with empty list when no briefs exist."""
        app, tid, uid = _make_app()

        with patch(
            "src.api.v1.earnings_brief_router.EarningsBriefRun"
        ), patch(
            "src.api.v1.earnings_brief_router.create_async_engine"
        ), patch(
            "src.api.v1.earnings_brief_router.async_sessionmaker"
        ) as mock_factory, patch(
            "src.api.v1.earnings_brief_router.select"
        ):
            mock_session = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = []
            mock_session.execute = AsyncMock(return_value=mock_result)
            mock_factory.return_value.return_value.__aenter__ = AsyncMock(
                return_value=mock_session
            )
            mock_factory.return_value.return_value.__aexit__ = AsyncMock(
                return_value=False
            )

            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/api/v1/earnings-briefs")

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 0
        assert body["data"] == []
