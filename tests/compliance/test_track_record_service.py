"""
Unit tests for ComplianceCheckService.get_company_track_record — TDD for TASK-003.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

from src.compliance.compliance_check_service import (
    ComplianceCheckService,
    IComplianceRepository,
    IRecommendationRepository,
    RecommendationWithOutcome,
    WorkflowRunSummary,
)
from src.compliance.compliance_schemas import TrackRecordResponse


# ── Stub helpers ──────────────────────────────────────────────────────────────


class StubComplianceRepo(IComplianceRepository):
    async def list_completed_runs_in_window(self, lookback_days: int) -> list[WorkflowRunSummary]:
        return []

    async def count_invocations_for_run(self, workflow_id: UUID) -> int:
        return 0


class StubRecommendationRepo(IRecommendationRepository):
    def __init__(
        self,
        rows: list[RecommendationWithOutcome],
        ticker: str = "AAPL",
    ) -> None:
        self._rows = rows
        self._ticker = ticker

    async def list_by_company(
        self, company_id: UUID, limit: int
    ) -> list[RecommendationWithOutcome]:
        return self._rows[:limit]

    async def get_company_ticker(self, company_id: UUID) -> str | None:
        return self._ticker


def _rec(
    action_signal: str = "BUY_OPP",
    confidence: float = 0.8,
    sample_size: int = 10,
    actual_t1d: float | None = None,
    actual_t1w: float | None = None,
) -> RecommendationWithOutcome:
    return RecommendationWithOutcome(
        rec_id=uuid4(),
        company_ticker="AAPL",
        action_signal=action_signal,
        confidence=confidence,
        sample_size=sample_size,
        generated_at=datetime.now(tz=timezone.utc),
        actual_t1d=actual_t1d,
        actual_t1w=actual_t1w,
        accuracy=None,
    )


def _service(rows: list[RecommendationWithOutcome]) -> ComplianceCheckService:
    return ComplianceCheckService(
        compliance_repo=StubComplianceRepo(),
        recommendation_repo=StubRecommendationRepo(rows),
        disclaimer_threshold=5,
    )


COMPANY_ID = uuid4()


# ── direction_correct_t1d_pct tests ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_track_record_all_correct_t1d() -> None:
    """3 recommendations, all with actual_t1d filled and directionally correct."""
    rows = [
        _rec(action_signal="BUY_OPP", actual_t1d=1.5),   # direction +1, actual +1.5 → correct
        _rec(action_signal="BUY_OPP", actual_t1d=0.5),   # direction +1, actual +0.5 → correct
        _rec(action_signal="REDUCE_RISK", actual_t1d=-0.3),  # direction -1, actual -0.3 → correct
    ]
    service = _service(rows)
    result = await service.get_company_track_record(COMPANY_ID)
    assert result.direction_correct_t1d_pct == pytest.approx(100.0)


@pytest.mark.asyncio
async def test_track_record_no_actuals_returns_none() -> None:
    """2 recommendations, none with actual_t1d → direction_correct_t1d_pct is None."""
    rows = [_rec(action_signal="BUY_OPP"), _rec(action_signal="BUY_OPP")]
    service = _service(rows)
    result = await service.get_company_track_record(COMPANY_ID)
    assert result.direction_correct_t1d_pct is None


@pytest.mark.asyncio
async def test_track_record_mixed_actuals() -> None:
    """1 correct, 1 incorrect, 1 no actual → direction_correct = 50.0."""
    rows = [
        _rec(action_signal="BUY_OPP", actual_t1d=1.0),    # correct
        _rec(action_signal="BUY_OPP", actual_t1d=-0.5),   # incorrect
        _rec(action_signal="BUY_OPP", actual_t1d=None),   # no actual — excluded
    ]
    service = _service(rows)
    result = await service.get_company_track_record(COMPANY_ID)
    assert result.direction_correct_t1d_pct == pytest.approx(50.0)


@pytest.mark.asyncio
async def test_track_record_disclaimer_required_when_small_sample() -> None:
    """sample_size=3 → disclaimer_required=True."""
    rows = [_rec(sample_size=3)]
    service = _service(rows)
    result = await service.get_company_track_record(COMPANY_ID)
    assert result.entries[0].disclaimer_required is True


@pytest.mark.asyncio
async def test_track_record_disclaimer_not_required_for_large_sample() -> None:
    """sample_size=7 → disclaimer_required=False."""
    rows = [_rec(sample_size=7)]
    service = _service(rows)
    result = await service.get_company_track_record(COMPANY_ID)
    assert result.entries[0].disclaimer_required is False


@pytest.mark.asyncio
async def test_track_record_empty_company() -> None:
    """No recommendations → entries=[], total=0, accuracy fields None."""
    service = _service([])
    result = await service.get_company_track_record(COMPANY_ID)
    assert result.entries == []
    assert result.total == 0
    assert result.direction_correct_t1d_pct is None
    assert result.direction_correct_t1w_pct is None


@pytest.mark.asyncio
async def test_track_record_limit_applied() -> None:
    """limit=2 returns at most 2 entries."""
    rows = [_rec() for _ in range(10)]
    service = _service(rows)
    result = await service.get_company_track_record(COMPANY_ID, limit=2)
    assert len(result.entries) <= 2


@pytest.mark.asyncio
async def test_track_record_hold_watch_excluded_from_direction_pct() -> None:
    """HOLD and WATCH (direction=0) are excluded from direction-correct pct."""
    rows = [
        _rec(action_signal="HOLD", actual_t1d=1.0),    # excluded
        _rec(action_signal="WATCH", actual_t1d=-1.0),  # excluded
        _rec(action_signal="BUY_OPP", actual_t1d=1.0), # correct
    ]
    service = _service(rows)
    result = await service.get_company_track_record(COMPANY_ID)
    # Only the BUY_OPP entry is counted — 1/1 = 100%
    assert result.direction_correct_t1d_pct == pytest.approx(100.0)


# ── API endpoint tests ────────────────────────────────────────────────────────


def test_compliance_router_imported() -> None:
    """Smoke test: the router can be imported and has the expected route."""
    from src.compliance.compliance_router import compliance_router
    routes = [r.path for r in compliance_router.routes]  # type: ignore[union-attr]
    assert any("track-record" in r for r in routes)
