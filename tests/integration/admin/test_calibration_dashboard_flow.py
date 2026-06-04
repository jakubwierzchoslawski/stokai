"""Integration test — calibration dashboard flow.

Seeds 10 calibration_result rows; exercises:
  - GET /api/v1/admin/audit/calibration?days=30
  - GET /api/v1/admin/audit/calibration/summary

Asserts:
  - 10 rows returned in time-series
  - below_threshold field present in summary
  - per_signal_accuracy contains at least one entry

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
from src.api.admin.audit.audit_api_schemas import CalibrationResult, CalibrationSummary, PerSignalAccuracy
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


def _make_calibration_result(i: int) -> CalibrationResult:
    return CalibrationResult(
        result_id=uuid.uuid4(),
        action_signal="HOLD",
        window_days=30,
        corr_confidence_actual=0.4 + i * 0.01,
        direction_correct_pct=0.65,
        mean_confidence=0.72,
        total_recommendations=100,
        computed_at=datetime(2026, 5, i + 1, tzinfo=timezone.utc),
        below_threshold=False,
    )


class TestCalibrationDashboardFlow:
    def test_get_calibration_returns_10_rows(self):
        """Seed 10 calibration rows; assert all 10 returned."""
        rows = [_make_calibration_result(i) for i in range(10)]

        svc = MagicMock(spec=AuditService)
        svc.get_calibration_time_series = AsyncMock(return_value=rows)

        test_app.dependency_overrides[get_current_admin_user] = lambda: _admin_user()
        test_app.dependency_overrides[_get_audit_service] = lambda: svc

        client = TestClient(test_app)
        response = client.get("/api/v1/admin/audit/calibration?days=30")
        assert response.status_code == 200
        assert len(response.json()["data"]) == 10

        svc.get_calibration_time_series.assert_called_once_with(days=30, action_signal=None)
        test_app.dependency_overrides.clear()

    def test_get_calibration_summary_has_below_threshold_field(self):
        """GET calibration/summary returns below_threshold bool."""
        summary = CalibrationSummary(
            window_days=30,
            below_threshold=False,
            threshold=0.3,
            per_signal_accuracy=[
                PerSignalAccuracy(
                    action_signal="HOLD",
                    direction_correct_pct=0.72,
                    mean_confidence=0.75,
                    total_recommendations=100,
                )
            ],
            computed_at=datetime.now(timezone.utc),
        )

        svc = MagicMock(spec=AuditService)
        svc.get_calibration_summary = AsyncMock(return_value=summary)

        test_app.dependency_overrides[get_current_admin_user] = lambda: _admin_user()
        test_app.dependency_overrides[_get_audit_service] = lambda: svc

        client = TestClient(test_app)
        response = client.get("/api/v1/admin/audit/calibration/summary?days=30")
        assert response.status_code == 200
        data = response.json()["data"]
        assert "below_threshold" in data
        assert isinstance(data["below_threshold"], bool)
        test_app.dependency_overrides.clear()

    def test_get_calibration_summary_has_per_signal_accuracy(self):
        """per_signal_accuracy must contain at least one entry."""
        summary = CalibrationSummary(
            window_days=30,
            below_threshold=True,
            threshold=0.3,
            per_signal_accuracy=[
                PerSignalAccuracy(
                    action_signal="HOLD",
                    direction_correct_pct=0.55,
                    mean_confidence=0.65,
                    total_recommendations=50,
                ),
                PerSignalAccuracy(
                    action_signal="BUY_OPP",
                    direction_correct_pct=0.48,
                    mean_confidence=0.60,
                    total_recommendations=30,
                ),
            ],
            computed_at=datetime.now(timezone.utc),
        )

        svc = MagicMock(spec=AuditService)
        svc.get_calibration_summary = AsyncMock(return_value=summary)

        test_app.dependency_overrides[get_current_admin_user] = lambda: _admin_user()
        test_app.dependency_overrides[_get_audit_service] = lambda: svc

        client = TestClient(test_app)
        response = client.get("/api/v1/admin/audit/calibration/summary?days=30")
        assert response.status_code == 200
        per_signal = response.json()["data"]["per_signal_accuracy"]
        assert len(per_signal) >= 1
        test_app.dependency_overrides.clear()
