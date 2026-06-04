"""
Integration tests for the Company Detail aggregated endpoint.

Uses FastAPI TestClient with all 5 fetch functions mocked.

PLAN-F-023 TASK-002
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.v1.company_detail_router import router
from src.api.v1.schemas.company_detail import (
    ActiveEventSummary,
    FundamentalsPanel,
    ScoreBreakdownItem,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

TENANT_ID = uuid.uuid4()
COMPANY_ID = uuid.uuid4()
USER_ID = uuid.uuid4()


def _make_jwt(tenant_id: uuid.UUID | None = None) -> str:
    import jwt as _jwt
    from datetime import timedelta

    payload = {
        "sub": str(USER_ID),
        "tenant_id": str(tenant_id or TENANT_ID),
        "role": "end_user",
        "email": "integration@test.com",
        "exp": datetime.utcnow() + timedelta(hours=1),
    }
    return _jwt.encode(payload, "test-secret", algorithm="HS256")


def _make_app() -> FastAPI:
    app = FastAPI()
    # router has prefix="/companies"; mount under /api/v1
    app.include_router(router, prefix="/api/v1")
    return app


def _company_meta() -> dict:
    return {
        "ticker": "INTG",
        "name": "Integration Corp",
        "sector": "Finance",
        "market_cap": 10_000_000.0,
    }


def _fundamentals() -> FundamentalsPanel:
    return FundamentalsPanel(
        pe_ratio=15.0,
        eps=2.50,
        revenue=5_000_000.0,
        debt_to_equity=1.2,
        source="edgar",
        as_of=datetime(2024, 3, 1, tzinfo=timezone.utc),
    )


def _score_items() -> list[ScoreBreakdownItem]:
    return [
        ScoreBreakdownItem(
            indicator_id=uuid.uuid4(),
            indicator_name="ROE",
            formula_summary="net_income / equity",
            weight=0.5,
            raw_value=0.18,
            score=65.0,
            geo_adjusted=None,
            sub_score_contribution=0.325,
            sparkline=[50.0, 55.0, 60.0, 65.0],
        )
    ]


def _active_events() -> list[ActiveEventSummary]:
    return [
        ActiveEventSummary(
            event_id=uuid.uuid4(),
            title="Regulatory Change",
            occurred_at=datetime(2024, 3, 15, tzinfo=timezone.utc),
            intensity=4,
            category=["regulatory"],
            exposure_magnitude=0.45,
        )
    ]


def _history_raw() -> list[dict]:
    return [
        {
            "rec_id": uuid.uuid4(),
            "generated_at": datetime(2024, 3, 1, tzinfo=timezone.utc),
            "workflow_type": "scheduled",
            "action_signal": "HOLD",
            "confidence": 0.55,
            "rationale": "Mixed signals from macro environment.",
            "actual_t1d": None,
            "actual_t1w": None,
        }
    ]


# ---------------------------------------------------------------------------
# Helper context manager
# ---------------------------------------------------------------------------

def _patched_app(
    meta=None,
    fundamentals=None,
    score_breakdown=None,
    active_events=None,
    history_raw=None,
):
    async def _meta(*a, **kw): return meta if meta is not None else _company_meta()
    async def _fund(*a, **kw): return fundamentals if fundamentals is not None else _fundamentals()
    async def _scores(*a, **kw): return score_breakdown if score_breakdown is not None else _score_items()
    async def _events(*a, **kw): return active_events if active_events is not None else _active_events()
    async def _hist(*a, **kw): return history_raw if history_raw is not None else _history_raw()

    return (
        patch("src.api.v1.company_detail_router._fetch_company_meta", side_effect=_meta),
        patch("src.api.v1.company_detail_router._fetch_fundamentals", side_effect=_fund),
        patch("src.api.v1.company_detail_router._fetch_score_breakdown", side_effect=_scores),
        patch("src.api.v1.company_detail_router._fetch_active_events", side_effect=_events),
        patch("src.api.v1.company_detail_router._fetch_analysis_history", side_effect=_hist),
        patch("src.api.auth_deps.get_settings"),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestCompanyDetailEndpointIntegration:
    """Integration tests for GET /api/v1/companies/{company_id}/detail."""

    def test_returns_200_with_all_panels_populated(self):
        """Full happy path: all panels present and non-empty."""
        app = _make_app()
        patches = _patched_app()

        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5] as mock_settings:
            mock_settings.return_value.JWT_SECRET_KEY = "test-secret"
            token = _make_jwt()
            with TestClient(app) as client:
                resp = client.get(
                    f"/api/v1/companies/{COMPANY_ID}/detail",
                    headers={"Authorization": f"Bearer {token}"},
                )

        assert resp.status_code == 200
        body = resp.json()
        assert body["ticker"] == "INTG"
        assert body["name"] == "Integration Corp"
        assert len(body["scores"]) == 1
        assert len(body["active_events"]) == 1
        assert "fundamentals" in body

    def test_returns_404_for_unknown_company(self):
        """Returns 404 with COMPANY_NOT_FOUND error code."""
        app = _make_app()
        unknown_id = uuid.uuid4()

        async def _no_meta(*a, **kw): return None
        async def _fund(*a, **kw): return _fundamentals()
        async def _scores(*a, **kw): return []
        async def _events(*a, **kw): return []
        async def _hist(*a, **kw): return []

        with (
            patch("src.api.v1.company_detail_router._fetch_company_meta", side_effect=_no_meta),
            patch("src.api.v1.company_detail_router._fetch_fundamentals", side_effect=_fund),
            patch("src.api.v1.company_detail_router._fetch_score_breakdown", side_effect=_scores),
            patch("src.api.v1.company_detail_router._fetch_active_events", side_effect=_events),
            patch("src.api.v1.company_detail_router._fetch_analysis_history", side_effect=_hist),
            patch("src.api.auth_deps.get_settings") as mock_settings,
        ):
            mock_settings.return_value.JWT_SECRET_KEY = "test-secret"
            token = _make_jwt()
            with TestClient(app) as client:
                resp = client.get(
                    f"/api/v1/companies/{unknown_id}/detail",
                    headers={"Authorization": f"Bearer {token}"},
                )

        assert resp.status_code == 404
        assert resp.json()["detail"]["code"] == "COMPANY_NOT_FOUND"

    def test_returns_403_without_jwt(self):
        """Returns 403 when no Authorization header is provided."""
        app = _make_app()
        with TestClient(app) as client:
            resp = client.get(f"/api/v1/companies/{COMPANY_ID}/detail")
        assert resp.status_code == 403

    def test_analysis_trigger_returns_202_with_run_id(self):
        """POST /analysis returns 202 with run_id."""
        app = _make_app()

        with patch("src.api.auth_deps.get_settings") as mock_settings:
            mock_settings.return_value.JWT_SECRET_KEY = "test-secret"
            token = _make_jwt()
            with TestClient(app) as client:
                resp = client.post(
                    f"/api/v1/companies/{COMPANY_ID}/analysis",
                    headers={"Authorization": f"Bearer {token}"},
                )

        assert resp.status_code == 202
        body = resp.json()
        assert "run_id" in body["data"]
        assert body["data"]["status"] == "queued"

    def test_scores_present_in_response(self):
        """Score breakdown items are returned in the response."""
        app = _make_app()
        patches = _patched_app()

        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5] as mock_settings:
            mock_settings.return_value.JWT_SECRET_KEY = "test-secret"
            token = _make_jwt()
            with TestClient(app) as client:
                resp = client.get(
                    f"/api/v1/companies/{COMPANY_ID}/detail",
                    headers={"Authorization": f"Bearer {token}"},
                )

        body = resp.json()
        assert len(body["scores"]) == 1
        score = body["scores"][0]
        assert score["indicator_name"] == "ROE"
        assert score["score"] == 65.0
        assert score["sub_score_contribution"] == pytest.approx(0.325)
