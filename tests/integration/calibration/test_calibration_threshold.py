"""
Integration tests for TASK-005: NFR threshold enforcement.

5 test cases verifying AC-001 and AC-002:
  1. Threshold met: 30 rows corr=0.45 → below_threshold=False, assessment="Healthy"
  2. Threshold breached: 30 rows corr=0.15 → below_threshold=True, "Warning" in assessment
  3. Insufficient sample: 10 recommendations → assessment="Insufficient data"
  4. Configurable threshold: override CALIBRATION_CORR_THRESHOLD=0.5, corr=0.35 → below_threshold=True
  5. Dashboard: GET /api/v1/evaluation/calibration/summary when below_threshold=True
     → JSON has "below_threshold": true

Uses mocked repositories — no real DB required.
pytest.mark.integration so they can be skipped without infrastructure.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.ai.evaluation.schemas.calibration_schemas import (
    CalibrationPassResult,
    CalibrationResult,
    CalibrationSummary,
)
from src.ai.evaluation.schemas.calibration_review_schemas import CalibrationReview
from src.api.evaluation.evaluation_router import (
    evaluation_router,
    get_calibration_repo,
    get_calibration_review_repo,
)

pytestmark = pytest.mark.integration


# ── Helpers ───────────────────────────────────────────────────────────────────

JWT_SECRET = "test-secret-key-minimum-32-characters-long!"
ADMIN_USER_ID = uuid.uuid4()


def _make_jwt(role: str = "admin") -> str:
    from datetime import timedelta

    from jose import jwt

    payload = {
        "sub": str(ADMIN_USER_ID),
        "tenant_id": str(uuid.uuid4()),
        "role": role,
        "email": f"{role}@example.com",
        "exp": datetime.now(tz=timezone.utc) + timedelta(hours=1),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def _make_cal_result(
    action_signal: str = "BUY",
    total_recommendations: int = 10,
    direction_correct_pct: float = 0.7,
    corr_confidence_actual: float | None = 0.45,
) -> CalibrationResult:
    return CalibrationResult(
        result_id=uuid.uuid4(),
        date=date(2026, 6, 1),
        action_signal=action_signal,
        total_recommendations=total_recommendations,
        direction_correct_pct=direction_correct_pct,
        corr_confidence_actual=corr_confidence_actual,
        mean_confidence=0.75,
        computed_at=datetime.now(tz=timezone.utc),
    )


def _build_app(mock_cal_repo: AsyncMock) -> FastAPI:
    """Build minimal FastAPI app for calibration summary tests."""
    import os

    os.environ.setdefault("JWT_SECRET_KEY", JWT_SECRET)

    app = FastAPI()
    app.include_router(evaluation_router, prefix="/api/v1/evaluation")
    app.dependency_overrides[get_calibration_repo] = lambda: mock_cal_repo
    # review repo not needed for summary tests, but stub it
    mock_review_repo = AsyncMock()
    app.dependency_overrides[get_calibration_review_repo] = lambda: mock_review_repo
    return app


# ── Test 1: Threshold met ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_threshold_met_healthy():
    """
    30 recommendations with corr=0.45 → below_threshold=False, assessment='Healthy'.
    """
    from src.ai.evaluation.services.tier3_calibration_service import (
        Tier3CalibrationService,
    )

    mock_cal_repo = AsyncMock()
    # 3 results × 10 recs = 30 total; corr above threshold 0.3
    results = [_make_cal_result(total_recommendations=10, corr_confidence_actual=0.45) for _ in range(3)]
    mock_cal_repo.list_last_n_days = AsyncMock(return_value=results)
    mock_cal_repo.get_rolling_corr = AsyncMock(return_value=0.45)

    mock_episodic_repo = AsyncMock()
    service = Tier3CalibrationService(
        calibration_repo=mock_cal_repo,
        episodic_repo=mock_episodic_repo,
    )

    summary = await service.get_calibration_summary(days=30)

    assert summary.below_threshold is False
    assert summary.assessment == "Healthy"
    assert summary.total_recommendations == 30


# ── Test 2: Threshold breached ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_threshold_breached_warning():
    """
    30 recommendations with corr=0.15 → below_threshold=True, 'Warning' in assessment.
    """
    from src.ai.evaluation.services.tier3_calibration_service import (
        Tier3CalibrationService,
    )

    mock_cal_repo = AsyncMock()
    results = [_make_cal_result(total_recommendations=10, corr_confidence_actual=0.15) for _ in range(3)]
    mock_cal_repo.list_last_n_days = AsyncMock(return_value=results)
    mock_cal_repo.get_rolling_corr = AsyncMock(return_value=0.15)

    mock_episodic_repo = AsyncMock()
    service = Tier3CalibrationService(
        calibration_repo=mock_cal_repo,
        episodic_repo=mock_episodic_repo,
    )

    summary = await service.get_calibration_summary(days=30)

    assert summary.below_threshold is True
    assert "Warning" in summary.assessment
    assert "CORR below threshold" in summary.assessment


# ── Test 3: Insufficient sample ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_insufficient_sample_assessment():
    """
    10 recommendations (< 30) → assessment='Insufficient data', below_threshold=False.
    """
    from src.ai.evaluation.services.tier3_calibration_service import (
        Tier3CalibrationService,
    )

    mock_cal_repo = AsyncMock()
    # Only 10 recommendations total (< 30 minimum)
    results = [_make_cal_result(total_recommendations=10, corr_confidence_actual=0.1)]
    mock_cal_repo.list_last_n_days = AsyncMock(return_value=results)
    mock_cal_repo.get_rolling_corr = AsyncMock(return_value=0.1)

    mock_episodic_repo = AsyncMock()
    service = Tier3CalibrationService(
        calibration_repo=mock_cal_repo,
        episodic_repo=mock_episodic_repo,
    )

    summary = await service.get_calibration_summary(days=30)

    assert summary.assessment == "Insufficient data"
    assert summary.below_threshold is False
    assert summary.total_recommendations == 10


# ── Test 4: Configurable threshold ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_configurable_threshold_override():
    """
    With CALIBRATION_CORR_THRESHOLD=0.5, corr=0.35 → below_threshold=True.
    """
    from src.ai.evaluation.services.tier3_calibration_service import (
        Tier3CalibrationService,
    )
    from src.config.settings import Settings, get_settings

    mock_cal_repo = AsyncMock()
    results = [_make_cal_result(total_recommendations=10, corr_confidence_actual=0.35) for _ in range(3)]
    mock_cal_repo.list_last_n_days = AsyncMock(return_value=results)
    mock_cal_repo.get_rolling_corr = AsyncMock(return_value=0.35)

    mock_episodic_repo = AsyncMock()
    service = Tier3CalibrationService(
        calibration_repo=mock_cal_repo,
        episodic_repo=mock_episodic_repo,
    )

    # Override the settings via patching get_settings
    mock_settings = AsyncMock(spec=Settings)
    mock_settings.CALIBRATION_CORR_THRESHOLD = 0.5  # Higher threshold
    mock_settings.CALIBRATION_MIN_SAMPLE = 30

    with patch(
        "src.ai.evaluation.services.tier3_calibration_service.get_settings",
        return_value=mock_settings,
    ):
        summary = await service.get_calibration_summary(days=30)

    # corr=0.35 is below new threshold=0.5
    assert summary.below_threshold is True
    assert "Warning" in summary.assessment


# ── Test 5: Dashboard summary endpoint ───────────────────────────────────────


def test_dashboard_summary_below_threshold_true_in_json():
    """
    GET /api/v1/evaluation/calibration/summary when below_threshold=True
    → JSON response has "below_threshold": true.
    """
    import os

    os.environ.setdefault("JWT_SECRET_KEY", JWT_SECRET)

    mock_cal_repo = AsyncMock()
    # 30 recs, low corr
    results = [_make_cal_result(total_recommendations=10, corr_confidence_actual=0.1) for _ in range(3)]
    mock_cal_repo.list_last_n_days = AsyncMock(return_value=results)
    mock_cal_repo.get_rolling_corr = AsyncMock(return_value=0.1)

    app = _build_app(mock_cal_repo)
    token = _make_jwt(role="admin")

    with TestClient(app, raise_server_exceptions=True) as client:
        response = client.get(
            "/api/v1/evaluation/calibration/summary",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["below_threshold"] is True
    assert "Warning" in data["assessment"]
