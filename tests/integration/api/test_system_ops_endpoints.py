"""
Integration tests for system ops endpoints.

Uses FastAPI TestClient with mocked services via dependency_overrides.
All endpoints require admin role; non-admin gets 403.

PLAN-F-030 TASK-008
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.admin.dependencies import require_admin
from src.admin.system.router import system_ops_router, _get_service
from src.admin.system.service import SystemOpsService
from src.ingestion.job_registry import JobNotFoundError, TriggerResponse
from src.storage.models.ingestion_job import IngestionJob, IngestionJobStatus
from src.storage.models.user import User, UserRole


# ── Test app setup ─────────────────────────────────────────────────────────────

test_app = FastAPI()
test_app.include_router(system_ops_router, prefix="/api/v1/admin")


TENANT_ID = uuid.uuid4()
ADMIN_USER_ID = uuid.uuid4()
END_USER_ID = uuid.uuid4()
JOB_ID = uuid.uuid4()
COMPANY_ID = uuid.uuid4()


def _make_admin() -> User:
    user = MagicMock(spec=User)
    user.user_id = ADMIN_USER_ID
    user.tenant_id = TENANT_ID
    user.role = UserRole.admin
    return user


def _make_end_user() -> User:
    user = MagicMock(spec=User)
    user.user_id = END_USER_ID
    user.tenant_id = TENANT_ID
    user.role = UserRole.end_user
    return user


def _make_job(
    status: str = "idle",
    error_count: int = 0,
) -> MagicMock:
    job = MagicMock(spec=IngestionJob)
    job.job_id = JOB_ID
    job.tenant_id = TENANT_ID
    job.name = "edgar_ingest"
    job.schedule = "0 * * * *"
    job.last_run = None
    job.next_run = None
    job.status = status
    job.error_count = error_count
    job.last_error_trace = None
    job.updated_at = datetime.now(timezone.utc)
    return job


def _make_service() -> AsyncMock:
    svc = AsyncMock(spec=SystemOpsService)

    # Jobs
    svc.list_jobs = AsyncMock(return_value=[_make_job()])
    svc.trigger_job = AsyncMock(
        return_value=TriggerResponse(
            job_id=str(JOB_ID), task_id="celery-abc-123", status="running"
        )
    )

    # Cost
    svc.get_cost_data = AsyncMock(
        return_value={
            "spend_usd": 42.5,
            "threshold_usd": 100.0,
            "pct_used": 42.5,
            "warning_active": False,
            "hard_stop_active": False,
            "by_source": [{"source": "openai", "total_cost_usd": 42.5}],
            "by_model": [],
            "by_workflow": [],
            "daily_totals": [],
        }
    )
    svc.update_threshold = AsyncMock(return_value={"threshold_usd": 150.0})

    # Companies
    svc.list_companies = AsyncMock(
        return_value={
            "items": [
                {
                    "company_id": str(COMPANY_ID),
                    "ticker": "AAPL",
                    "name": "Apple Inc",
                    "is_tracked": True,
                }
            ],
            "total": 1,
            "page": 1,
            "page_size": 50,
        }
    )
    svc.set_tracked = AsyncMock(
        return_value={
            "company_id": str(COMPANY_ID),
            "is_tracked": True,
            "ticker": "AAPL",
            "name": "Apple Inc",
        }
    )
    svc.search_companies = AsyncMock(
        return_value=[
            {"company_id": str(COMPANY_ID), "ticker": "AAPL", "name": "Apple Inc"}
        ]
    )

    # Cache
    svc.get_cache_stats = AsyncMock(
        return_value={
            "price_bars_count": 10,
            "embeddings_count": 5,
            "event_data_count": 3,
            "total_redis_memory_bytes": 2048,
        }
    )
    svc.force_refresh_cache = AsyncMock(
        return_value={"data_type": "price_bars", "keys_deleted": 10}
    )

    # Flags
    svc.list_flags = AsyncMock(
        return_value=[
            {
                "flag_id": "morning_brief",
                "environment": "production",
                "enabled": True,
                "updated_at": None,
                "updated_by": None,
            },
            {
                "flag_id": "social_twitter",
                "environment": "production",
                "enabled": False,
                "updated_at": None,
                "updated_by": None,
            },
        ]
    )
    svc.set_flag = AsyncMock(
        return_value={
            "flag_id": "morning_brief",
            "environment": "production",
            "enabled": False,
            "updated_at": None,
            "updated_by": None,
        }
    )
    return svc


def _admin_client() -> TestClient:
    """Build a TestClient with admin user override."""
    svc = _make_service()
    test_app.dependency_overrides[require_admin] = lambda: _make_admin()
    test_app.dependency_overrides[_get_service] = lambda: svc
    client = TestClient(test_app, raise_server_exceptions=False)
    return client, svc


def _end_user_client() -> TestClient:
    """Build a TestClient that raises 403 for non-admin calls."""
    from fastapi import HTTPException, status

    def _forbidden():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "Admin role required"},
        )

    test_app.dependency_overrides[require_admin] = _forbidden
    test_app.dependency_overrides[_get_service] = lambda: _make_service()
    return TestClient(test_app, raise_server_exceptions=False)


# ── Authorization tests ────────────────────────────────────────────────────────


class TestAuthorization:
    def test_trigger_job_with_end_user_returns_403(self) -> None:
        client = _end_user_client()
        resp = client.post(f"/api/v1/admin/system/jobs/{JOB_ID}/trigger")
        assert resp.status_code == 403

    def test_get_cost_with_end_user_returns_403(self) -> None:
        client = _end_user_client()
        resp = client.get("/api/v1/admin/system/cost")
        assert resp.status_code == 403

    def test_get_flags_with_end_user_returns_403(self) -> None:
        client = _end_user_client()
        resp = client.get("/api/v1/admin/system/flags")
        assert resp.status_code == 403


# ── Ingestion Jobs ─────────────────────────────────────────────────────────────


class TestIngestionJobsEndpoints:
    def test_list_jobs_returns_200(self) -> None:
        client, svc = _admin_client()
        resp = client.get("/api/v1/admin/system/jobs")
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        assert body["error"] is None

    def test_trigger_job_with_admin_returns_200_with_task_id(self) -> None:
        client, svc = _admin_client()
        resp = client.post(f"/api/v1/admin/system/jobs/{JOB_ID}/trigger")
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["task_id"] == "celery-abc-123"

    def test_trigger_known_job_dispatches_send_task(self) -> None:
        client, svc = _admin_client()
        client.post(f"/api/v1/admin/system/jobs/{JOB_ID}/trigger")
        svc.trigger_job.assert_called_once()

    def test_trigger_unknown_job_returns_404(self) -> None:
        svc = _make_service()
        svc.trigger_job = AsyncMock(
            side_effect=JobNotFoundError("not registered")
        )
        test_app.dependency_overrides[require_admin] = lambda: _make_admin()
        test_app.dependency_overrides[_get_service] = lambda: svc
        client = TestClient(test_app, raise_server_exceptions=False)

        unknown_job_id = uuid.uuid4()
        resp = client.post(f"/api/v1/admin/system/jobs/{unknown_job_id}/trigger")
        assert resp.status_code == 404


# ── Cost Monitor ───────────────────────────────────────────────────────────────


class TestCostMonitorEndpoints:
    def test_get_cost_returns_aggregate_fields(self) -> None:
        client, _ = _admin_client()
        resp = client.get("/api/v1/admin/system/cost")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "spend_usd" in data
        assert "threshold_usd" in data
        assert "pct_used" in data
        assert "warning_active" in data
        assert "hard_stop_active" in data

    def test_patch_threshold_persists(self) -> None:
        client, svc = _admin_client()
        resp = client.patch(
            "/api/v1/admin/system/cost/threshold",
            json={"threshold_usd": 150.0},
        )
        assert resp.status_code == 200
        svc.update_threshold.assert_called_once_with(150.0)


# ── Company Universe ───────────────────────────────────────────────────────────


class TestCompanyEndpoints:
    def test_post_track_returns_200_with_is_tracked_true(self) -> None:
        client, svc = _admin_client()
        resp = client.post(f"/api/v1/admin/system/companies/{COMPANY_ID}/track")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["is_tracked"] is True

    def test_delete_track_returns_200_with_is_tracked_false(self) -> None:
        svc = _make_service()
        svc.set_tracked = AsyncMock(
            return_value={
                "company_id": str(COMPANY_ID),
                "is_tracked": False,
                "ticker": "AAPL",
                "name": "Apple Inc",
            }
        )
        test_app.dependency_overrides[require_admin] = lambda: _make_admin()
        test_app.dependency_overrides[_get_service] = lambda: svc
        client = TestClient(test_app, raise_server_exceptions=False)

        resp = client.delete(f"/api/v1/admin/system/companies/{COMPANY_ID}/track")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["is_tracked"] is False


# ── Cache Inspection ───────────────────────────────────────────────────────────


class TestCacheEndpoints:
    def test_post_cache_refresh_price_bars_calls_force_refresh(self) -> None:
        client, svc = _admin_client()
        resp = client.post(
            "/api/v1/admin/system/cache/refresh",
            json={"data_type": "price_bars"},
        )
        assert resp.status_code == 200
        svc.force_refresh_cache.assert_called_once_with("price_bars", None)

    def test_post_cache_refresh_invalid_data_type_returns_422(self) -> None:
        from src.admin.system.cache_service import InvalidDataTypeError

        svc = _make_service()
        svc.force_refresh_cache = AsyncMock(
            side_effect=InvalidDataTypeError("unknown_type")
        )
        test_app.dependency_overrides[require_admin] = lambda: _make_admin()
        test_app.dependency_overrides[_get_service] = lambda: svc
        client = TestClient(test_app, raise_server_exceptions=False)

        resp = client.post(
            "/api/v1/admin/system/cache/refresh",
            json={"data_type": "invalid_type"},
        )
        assert resp.status_code == 422


# ── Feature Flags ──────────────────────────────────────────────────────────────


class TestFeatureFlagEndpoints:
    def test_patch_flag_returns_200_with_enabled_false(self) -> None:
        client, svc = _admin_client()
        resp = client.patch(
            "/api/v1/admin/system/flags/morning_brief",
            json={"enabled": False},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["enabled"] is False

    def test_get_flags_returns_only_active_environment_flags(self) -> None:
        client, svc = _admin_client()
        resp = client.get("/api/v1/admin/system/flags")
        assert resp.status_code == 200
        flags = resp.json()["data"]
        # All returned flags should have the same environment
        envs = {f["environment"] for f in flags}
        assert len(envs) == 1

    def test_get_flags_returns_morning_brief_and_social_twitter(self) -> None:
        client, _ = _admin_client()
        resp = client.get("/api/v1/admin/system/flags")
        data = resp.json()["data"]
        flag_ids = {f["flag_id"] for f in data}
        assert "morning_brief" in flag_ids
        assert "social_twitter" in flag_ids
