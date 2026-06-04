"""
Integration tests for the track record API endpoint — TASK-006.

Uses a minimal FastAPI test application with the compliance_router wired in.
Dependency injection overrides replace the real SQL repositories with stubs.

PLAN-N-012 AC-001, AC-003
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import AsyncGenerator
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.api.auth_deps import CurrentUser, get_current_user
from src.compliance.compliance_check_service import (
    ComplianceCheckService,
    IComplianceRepository,
    IRecommendationRepository,
    RecommendationWithOutcome,
    WorkflowRunSummary,
)
from src.compliance.compliance_router import compliance_router, _get_compliance_service


# ── Stubs ─────────────────────────────────────────────────────────────────────


class StubComplianceRepo(IComplianceRepository):
    async def list_completed_runs_in_window(
        self, lookback_days: int
    ) -> list[WorkflowRunSummary]:
        return []

    async def count_invocations_for_run(self, workflow_id: UUID) -> int:
        return 0


class ConfigurableRecommendationRepo(IRecommendationRepository):
    def __init__(
        self,
        rows: list[RecommendationWithOutcome] | None = None,
        ticker: str = "TEST",
    ) -> None:
        self._rows = rows or []
        self._ticker = ticker

    async def list_by_company(
        self, company_id: UUID, limit: int
    ) -> list[RecommendationWithOutcome]:
        return self._rows[:limit]

    async def get_company_ticker(self, company_id: UUID) -> str | None:
        return self._ticker


def _make_rec(
    action_signal: str = "BUY_OPP",
    sample_size: int = 10,
    confidence: float = 0.7,
    actual_t1d: float | None = None,
    actual_t1w: float | None = None,
) -> RecommendationWithOutcome:
    return RecommendationWithOutcome(
        rec_id=uuid4(),
        company_ticker="TEST",
        action_signal=action_signal,
        confidence=confidence,
        sample_size=sample_size,
        generated_at=datetime.now(tz=timezone.utc),
        actual_t1d=actual_t1d,
        actual_t1w=actual_t1w,
        accuracy=None,
    )


# ── App factory ───────────────────────────────────────────────────────────────


def _make_app(
    rows: list[RecommendationWithOutcome] | None = None,
    authenticated: bool = True,
) -> FastAPI:
    """Build a minimal test app with the compliance_router and stubbed deps."""
    app = FastAPI()
    app.include_router(compliance_router, prefix="/api/v1")

    rec_repo = ConfigurableRecommendationRepo(rows or [])
    service = ComplianceCheckService(
        compliance_repo=StubComplianceRepo(),
        recommendation_repo=rec_repo,
        disclaimer_threshold=5,
    )

    app.dependency_overrides[_get_compliance_service] = lambda: service

    if authenticated:
        dummy_user = CurrentUser(
            user_id=uuid4(),
            tenant_id=uuid4(),
            role="end_user",
            email="test@example.com",
        )
        app.dependency_overrides[get_current_user] = lambda: dummy_user

    return app


COMPANY_ID = uuid4()
BASE_URL = "http://test"


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_track_record_returns_5_entries_total() -> None:
    """5 seeded recommendations → 5 entries, total=5."""
    rows = [_make_rec() for _ in range(5)]
    app = _make_app(rows)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url=BASE_URL
    ) as client:
        resp = await client.get(f"/api/v1/compliance/track-record/{COMPANY_ID}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 5
    assert len(body["entries"]) == 5


@pytest.mark.asyncio
async def test_track_record_direction_correct_computed() -> None:
    """3 entries with actual_t1d; direction_correct_t1d_pct computed correctly."""
    rows = [
        _make_rec(action_signal="BUY_OPP", actual_t1d=1.0),    # correct
        _make_rec(action_signal="BUY_OPP", actual_t1d=-0.5),   # wrong
        _make_rec(action_signal="BUY_OPP", actual_t1d=0.3),    # correct
    ]
    app = _make_app(rows)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url=BASE_URL
    ) as client:
        resp = await client.get(f"/api/v1/compliance/track-record/{COMPANY_ID}")

    body = resp.json()
    assert body["direction_correct_t1d_pct"] == pytest.approx(200 / 3)


@pytest.mark.asyncio
async def test_track_record_disclaimer_required_for_small_sample() -> None:
    """Entries with sample_size < 5 have disclaimer_required=True."""
    rows = [
        _make_rec(sample_size=2),   # disclaimer required
        _make_rec(sample_size=10),  # not required
    ]
    app = _make_app(rows)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url=BASE_URL
    ) as client:
        resp = await client.get(f"/api/v1/compliance/track-record/{COMPANY_ID}")

    entries = resp.json()["entries"]
    # Find by sample_size (order may vary)
    small = next(e for e in entries if e["sample_size"] == 2)
    large = next(e for e in entries if e["sample_size"] == 10)
    assert small["disclaimer_required"] is True
    assert large["disclaimer_required"] is False


@pytest.mark.asyncio
async def test_track_record_unauthenticated_returns_401() -> None:
    """Unauthenticated request returns 401."""
    app = _make_app(authenticated=False)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url=BASE_URL
    ) as client:
        resp = await client.get(f"/api/v1/compliance/track-record/{COMPANY_ID}")

    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_track_record_empty_company() -> None:
    """Company with no recommendations returns entries=[], total=0."""
    app = _make_app([])

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url=BASE_URL
    ) as client:
        resp = await client.get(f"/api/v1/compliance/track-record/{COMPANY_ID}")

    body = resp.json()
    assert body["entries"] == []
    assert body["total"] == 0
    assert body["direction_correct_t1d_pct"] is None
    assert body["direction_correct_t1w_pct"] is None


@pytest.mark.asyncio
async def test_track_record_limit_param_restricts_entries() -> None:
    """limit=3 returns at most 3 entries from a 10-entry dataset."""
    rows = [_make_rec() for _ in range(10)]
    app = _make_app(rows)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url=BASE_URL
    ) as client:
        resp = await client.get(
            f"/api/v1/compliance/track-record/{COMPANY_ID}?limit=3"
        )

    body = resp.json()
    assert len(body["entries"]) <= 3
