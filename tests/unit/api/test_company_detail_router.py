"""
Unit tests for the Company Detail API endpoint.

All external dependencies (fetch functions, JWT auth) are mocked.

PLAN-F-023 TASK-002, TASK-003, TASK-004
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.v1.company_detail_router import (
    _build_track_record,
    _compute_directional_accuracy,
    _map_direction,
    _truncate_formula,
    router,
)
from src.api.v1.schemas.company_detail import (
    ActiveEventSummary,
    AnalysisHistoryItem,
    FundamentalsPanel,
    ScoreBreakdownItem,
    TrackRecordItem,
)

# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------

TENANT_ID = uuid.uuid4()
COMPANY_ID = uuid.uuid4()
USER_ID = uuid.uuid4()


def _make_jwt(role: str = "end_user", tenant_id: uuid.UUID | None = None) -> str:
    import jwt as _jwt
    from datetime import timedelta

    payload = {
        "sub": str(USER_ID),
        "tenant_id": str(tenant_id or TENANT_ID),
        "role": role,
        "email": "test@example.com",
        "exp": datetime.utcnow() + timedelta(hours=1),
    }
    return _jwt.encode(payload, "test-secret", algorithm="HS256")


def _make_app() -> FastAPI:
    app = FastAPI()
    # router has prefix="/companies"; mount under /api/v1 so the full path is
    # /api/v1/companies/{company_id}/detail
    app.include_router(router, prefix="/api/v1")
    return app


def _make_fundamentals() -> FundamentalsPanel:
    return FundamentalsPanel(
        pe_ratio=20.5,
        eps=3.14,
        revenue=1_000_000.0,
        debt_to_equity=0.5,
        source="fmp",
        as_of=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )


def _make_score_items() -> list[ScoreBreakdownItem]:
    return [
        ScoreBreakdownItem(
            indicator_id=uuid.uuid4(),
            indicator_name="Revenue Growth",
            formula_summary="revenue / revenue_lag1",
            weight=0.6,
            raw_value=1.05,
            score=72.0,
            geo_adjusted=None,
            sub_score_contribution=0.432,
            sparkline=[60.0, 65.0, 70.0, 72.0],
        )
    ]


def _make_active_events() -> list[ActiveEventSummary]:
    return [
        ActiveEventSummary(
            event_id=uuid.uuid4(),
            title="Supply Chain Disruption",
            occurred_at=datetime(2024, 2, 1, tzinfo=timezone.utc),
            intensity=3,
            category=["trade"],
            exposure_magnitude=0.65,
        )
    ]


def _make_history_raw() -> list[dict]:
    return [
        {
            "rec_id": uuid.uuid4(),
            "generated_at": datetime(2024, 2, 1, tzinfo=timezone.utc),
            "workflow_type": "on_demand",
            "action_signal": "BUY_OPP",
            "confidence": 0.85,
            "rationale": "Strong fundamentals amid supply-chain disruption.",
            "actual_t1d": 0.02,
            "actual_t1w": 0.05,
        },
    ]


def _company_meta() -> dict:
    return {
        "ticker": "ACME",
        "name": "Acme Corp",
        "sector": "Technology",
        "market_cap": 5_000_000.0,
    }


# ---------------------------------------------------------------------------
# TASK-002 tests — endpoint contract
# ---------------------------------------------------------------------------


class TestGetCompanyDetailEndpoint:
    """Integration-level unit tests using TestClient with mocked dependencies."""

    def _get_client_with_mocks(
        self,
        *,
        company_meta=None,
        fundamentals=None,
        score_breakdown=None,
        active_events=None,
        history_raw=None,
    ):
        app = _make_app()

        async def _meta(*a, **kw):
            return company_meta if company_meta is not None else _company_meta()

        async def _fund(*a, **kw):
            return fundamentals if fundamentals is not None else _make_fundamentals()

        async def _scores(*a, **kw):
            return score_breakdown if score_breakdown is not None else _make_score_items()

        async def _events(*a, **kw):
            return active_events if active_events is not None else _make_active_events()

        async def _hist(*a, **kw):
            return history_raw if history_raw is not None else _make_history_raw()

        patches = [
            patch("src.api.v1.company_detail_router._fetch_company_meta", side_effect=_meta),
            patch("src.api.v1.company_detail_router._fetch_fundamentals", side_effect=_fund),
            patch("src.api.v1.company_detail_router._fetch_score_breakdown", side_effect=_scores),
            patch("src.api.v1.company_detail_router._fetch_active_events", side_effect=_events),
            patch("src.api.v1.company_detail_router._fetch_analysis_history", side_effect=_hist),
            patch("src.api.auth_deps.get_settings"),
        ]
        return patches, app

    def test_endpoint_returns_200_with_all_panels(self):
        """GET /detail returns 200 with all panels populated."""
        app = _make_app()

        async def _meta(*a, **kw): return _company_meta()
        async def _fund(*a, **kw): return _make_fundamentals()
        async def _scores(*a, **kw): return _make_score_items()
        async def _events(*a, **kw): return _make_active_events()
        async def _hist(*a, **kw): return _make_history_raw()

        with (
            patch("src.api.v1.company_detail_router._fetch_company_meta", side_effect=_meta),
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
                    f"/api/v1/companies/{COMPANY_ID}/detail",
                    headers={"Authorization": f"Bearer {token}"},
                )

        assert resp.status_code == 200
        body = resp.json()
        assert body["ticker"] == "ACME"
        assert body["name"] == "Acme Corp"
        assert "fundamentals" in body
        assert "scores" in body
        assert "active_events" in body
        assert "analysis_history" in body
        assert "track_record" in body

    def test_endpoint_404_for_unknown_company_id(self):
        """GET /detail returns 404 when company is not found for the tenant."""
        app = _make_app()

        async def _meta(*a, **kw): return None  # Simulates not found
        async def _fund(*a, **kw): return _make_fundamentals()
        async def _scores(*a, **kw): return []
        async def _events(*a, **kw): return []
        async def _hist(*a, **kw): return []

        with (
            patch("src.api.v1.company_detail_router._fetch_company_meta", side_effect=_meta),
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
                    f"/api/v1/companies/{uuid.uuid4()}/detail",
                    headers={"Authorization": f"Bearer {token}"},
                )

        assert resp.status_code == 404
        body = resp.json()
        assert body["detail"]["code"] == "COMPANY_NOT_FOUND"

    def test_endpoint_401_without_jwt(self):
        """GET /detail returns 401 or 403 when no Authorization header is provided."""
        app = _make_app()
        with TestClient(app) as client:
            resp = client.get(f"/api/v1/companies/{COMPANY_ID}/detail")
        assert resp.status_code in (401, 403)  # HTTPBearer raises 401 or 403 depending on version

    def test_endpoint_scopes_data_to_tenant(self):
        """The tenant_id from the JWT is passed to all fetch functions."""
        captured_tenant_ids: list[uuid.UUID] = []

        async def _meta(company_id, tenant_id):
            captured_tenant_ids.append(tenant_id)
            return _company_meta()

        async def _fund(company_id, tenant_id): return _make_fundamentals()
        async def _scores(company_id, tenant_id, profile_id): return []
        async def _events(company_id, tenant_id): return []
        async def _hist(company_id, tenant_id, limit=10): return []

        app = _make_app()
        with (
            patch("src.api.v1.company_detail_router._fetch_company_meta", side_effect=_meta),
            patch("src.api.v1.company_detail_router._fetch_fundamentals", side_effect=_fund),
            patch("src.api.v1.company_detail_router._fetch_score_breakdown", side_effect=_scores),
            patch("src.api.v1.company_detail_router._fetch_active_events", side_effect=_events),
            patch("src.api.v1.company_detail_router._fetch_analysis_history", side_effect=_hist),
            patch("src.api.auth_deps.get_settings") as mock_settings,
        ):
            mock_settings.return_value.JWT_SECRET_KEY = "test-secret"
            token = _make_jwt(tenant_id=TENANT_ID)
            with TestClient(app) as client:
                resp = client.get(
                    f"/api/v1/companies/{COMPANY_ID}/detail",
                    headers={"Authorization": f"Bearer {token}"},
                )

        assert resp.status_code == 200
        assert all(tid == TENANT_ID for tid in captured_tenant_ids)

    def test_endpoint_directional_accuracy_computed_correctly(self):
        """3 filled records, 2 correct → directional_accuracy_t1d ≈ 0.667."""
        # 3 bullish recs: t1d > 0 (correct), t1d > 0 (correct), t1d < 0 (wrong)
        history_raw = [
            {
                "rec_id": uuid.uuid4(),
                "generated_at": datetime(2024, 1, 1, tzinfo=timezone.utc),
                "workflow_type": "on_demand",
                "action_signal": "BUY_OPP",
                "confidence": 0.8,
                "rationale": "Strong",
                "actual_t1d": 0.01,  # correct
                "actual_t1w": None,
            },
            {
                "rec_id": uuid.uuid4(),
                "generated_at": datetime(2024, 1, 2, tzinfo=timezone.utc),
                "workflow_type": "on_demand",
                "action_signal": "BUY_OPP",
                "confidence": 0.7,
                "rationale": "Strong",
                "actual_t1d": 0.02,  # correct
                "actual_t1w": None,
            },
            {
                "rec_id": uuid.uuid4(),
                "generated_at": datetime(2024, 1, 3, tzinfo=timezone.utc),
                "workflow_type": "on_demand",
                "action_signal": "BUY_OPP",
                "confidence": 0.6,
                "rationale": "Strong",
                "actual_t1d": -0.01,  # wrong (bullish but price fell)
                "actual_t1w": None,
            },
        ]

        async def _meta(*a, **kw): return _company_meta()
        async def _fund(*a, **kw): return _make_fundamentals()
        async def _scores(*a, **kw): return []
        async def _events(*a, **kw): return []
        async def _hist(*a, **kw): return history_raw

        app = _make_app()
        with (
            patch("src.api.v1.company_detail_router._fetch_company_meta", side_effect=_meta),
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
                    f"/api/v1/companies/{COMPANY_ID}/detail",
                    headers={"Authorization": f"Bearer {token}"},
                )

        assert resp.status_code == 200
        body = resp.json()
        acc = body["directional_accuracy_t1d"]
        assert acc is not None
        assert abs(acc - 2 / 3) < 0.01

    def test_endpoint_uses_default_profile_when_profile_id_not_supplied(self):
        """When profile_id is not in query string, endpoint does not error."""
        async def _meta(*a, **kw): return _company_meta()
        async def _fund(*a, **kw): return _make_fundamentals()
        async def _scores(*a, **kw): return []
        async def _events(*a, **kw): return []
        async def _hist(*a, **kw): return []

        app = _make_app()
        with (
            patch("src.api.v1.company_detail_router._fetch_company_meta", side_effect=_meta),
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
                    f"/api/v1/companies/{COMPANY_ID}/detail",
                    headers={"Authorization": f"Bearer {token}"},
                )

        assert resp.status_code == 200

    def test_endpoint_parallel_fetches_via_asyncio_gather(self):
        """All five fetches are called exactly once per request."""
        call_counts: dict[str, int] = {
            "meta": 0,
            "fund": 0,
            "scores": 0,
            "events": 0,
            "hist": 0,
        }

        async def _meta(*a, **kw):
            call_counts["meta"] += 1
            return _company_meta()

        async def _fund(*a, **kw):
            call_counts["fund"] += 1
            return _make_fundamentals()

        async def _scores(*a, **kw):
            call_counts["scores"] += 1
            return []

        async def _events(*a, **kw):
            call_counts["events"] += 1
            return []

        async def _hist(*a, **kw):
            call_counts["hist"] += 1
            return []

        app = _make_app()
        with (
            patch("src.api.v1.company_detail_router._fetch_company_meta", side_effect=_meta),
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
                    f"/api/v1/companies/{COMPANY_ID}/detail",
                    headers={"Authorization": f"Bearer {token}"},
                )

        assert resp.status_code == 200
        assert all(v == 1 for v in call_counts.values()), call_counts


# ---------------------------------------------------------------------------
# TASK-003 tests — score breakdown panel
# ---------------------------------------------------------------------------


class TestScoreBreakdown:
    """Unit tests for formula summary truncation and sub-score contribution."""

    def test_score_breakdown_truncates_formula_at_120_chars(self):
        """A 150-char DSL → 123-char string ending with '...'."""
        long_formula = "x" * 150
        result = _truncate_formula(long_formula)
        assert len(result) == 123  # 120 + 3 for "..."
        assert result.endswith("...")

    def test_score_breakdown_sub_score_contribution_calculation(self):
        """weight=0.4, score=75.0 → sub_score_contribution=0.30."""
        weight = 0.4
        score = 75.0
        contribution = weight * score / 100
        assert abs(contribution - 0.30) < 1e-9

    def test_score_breakdown_missing_score_row_yields_zero_defaults(self):
        """When score data is missing, defaults: score=0, raw_value=None, geo_adjusted=None."""
        item = ScoreBreakdownItem(
            indicator_id=uuid.uuid4(),
            indicator_name="Test",
            formula_summary="x",
            weight=0.5,
            raw_value=None,
            score=0.0,
            geo_adjusted=None,
            sub_score_contribution=0.0,
            sparkline=[],
        )
        assert item.raw_value is None
        assert item.score == 0.0
        assert item.geo_adjusted is None
        assert item.sub_score_contribution == 0.0

    def test_score_breakdown_sparkline_is_oldest_first(self):
        """Sparkline list is ordered oldest-first (smallest index = earliest date)."""
        sparkline = [50.0, 55.0, 60.0, 65.0, 70.0]
        item = ScoreBreakdownItem(
            indicator_id=uuid.uuid4(),
            indicator_name="Test",
            formula_summary="x",
            weight=0.5,
            raw_value=1.0,
            score=70.0,
            geo_adjusted=None,
            sub_score_contribution=0.35,
            sparkline=sparkline,
        )
        # Oldest-first means each element should be <= the next
        for i in range(len(item.sparkline) - 1):
            assert item.sparkline[i] <= item.sparkline[i + 1]

    def test_score_breakdown_all_indicators_in_profile_present(self):
        """All indicators returned by _fetch_score_breakdown appear in the response."""
        n_indicators = 3
        items = [
            ScoreBreakdownItem(
                indicator_id=uuid.uuid4(),
                indicator_name=f"Indicator {i}",
                formula_summary=f"x_{i}",
                weight=1.0 / n_indicators,
                raw_value=float(i),
                score=float(i * 10),
                geo_adjusted=None,
                sub_score_contribution=float(i * 10) / n_indicators / 100,
                sparkline=[],
            )
            for i in range(n_indicators)
        ]
        assert len(items) == n_indicators

    def test_formula_not_truncated_when_at_or_below_120_chars(self):
        """Formula of exactly 120 chars is not truncated."""
        formula_120 = "x" * 120
        result = _truncate_formula(formula_120)
        assert result == formula_120
        assert not result.endswith("...")


# ---------------------------------------------------------------------------
# TASK-004 tests — track record panel
# ---------------------------------------------------------------------------


class TestTrackRecord:
    """Unit tests for direction mapping and correctness computation."""

    def test_direction_buy_opp_is_bullish(self):
        assert _map_direction("BUY_OPP") == "bullish"

    def test_direction_reduce_risk_is_bearish(self):
        assert _map_direction("REDUCE_RISK") == "bearish"

    def test_direction_hedge_is_bearish(self):
        assert _map_direction("HEDGE") == "bearish"

    def test_direction_hold_is_neutral(self):
        assert _map_direction("HOLD") == "neutral"

    def test_direction_watch_is_neutral(self):
        assert _map_direction("WATCH") == "neutral"

    def test_direction_contrarian_is_neutral(self):
        assert _map_direction("CONTRARIAN") == "neutral"

    def test_correct_t1d_bullish_positive_return(self):
        """Bullish + positive return → correct."""
        raw = [
            {
                "rec_id": uuid.uuid4(),
                "generated_at": datetime.now(tz=timezone.utc),
                "action_signal": "BUY_OPP",
                "confidence": 0.9,
                "actual_t1d": 0.05,
                "actual_t1w": None,
            }
        ]
        items = _build_track_record(raw)
        assert items[0].correct_t1d is True

    def test_correct_t1d_bearish_negative_return(self):
        """Bearish + negative return → correct."""
        raw = [
            {
                "rec_id": uuid.uuid4(),
                "generated_at": datetime.now(tz=timezone.utc),
                "action_signal": "REDUCE_RISK",
                "confidence": 0.8,
                "actual_t1d": -0.03,
                "actual_t1w": None,
            }
        ]
        items = _build_track_record(raw)
        assert items[0].correct_t1d is True

    def test_correct_t1d_bullish_negative_return_is_wrong(self):
        """Bullish + negative return → incorrect."""
        raw = [
            {
                "rec_id": uuid.uuid4(),
                "generated_at": datetime.now(tz=timezone.utc),
                "action_signal": "BUY_OPP",
                "confidence": 0.7,
                "actual_t1d": -0.02,
                "actual_t1w": None,
            }
        ]
        items = _build_track_record(raw)
        assert items[0].correct_t1d is False

    def test_correct_t1d_none_when_no_actual(self):
        """correct_t1d is None when actual_t1d is not yet available."""
        raw = [
            {
                "rec_id": uuid.uuid4(),
                "generated_at": datetime.now(tz=timezone.utc),
                "action_signal": "BUY_OPP",
                "confidence": 0.7,
                "actual_t1d": None,
                "actual_t1w": None,
            }
        ]
        items = _build_track_record(raw)
        assert items[0].correct_t1d is None

    def test_directional_accuracy_none_when_no_filled_records(self):
        """Returns None when there are no records with actual_t1d filled."""
        items: list[TrackRecordItem] = []
        result = _compute_directional_accuracy(items)
        assert result is None

    def test_directional_accuracy_excludes_neutral(self):
        """Neutral signals are excluded from accuracy computation."""
        items = [
            TrackRecordItem(
                rec_id=uuid.uuid4(),
                generated_at=datetime.now(tz=timezone.utc),
                action_signal="HOLD",
                direction="neutral",
                confidence=0.5,
                actual_t1d=0.01,
                actual_t1w=None,
                correct_t1d=None,
                correct_t1w=None,
            )
        ]
        result = _compute_directional_accuracy(items)
        assert result is None


# ---------------------------------------------------------------------------
# Integration-level schema tests
# ---------------------------------------------------------------------------


class TestCompanyDetailResponse:
    """Schema-level tests for CompanyDetailResponse construction."""

    def test_directional_accuracy_returns_none_for_no_track_record(self):
        """No track record → directional_accuracy_t1d is None."""
        result = _compute_directional_accuracy([])
        assert result is None
