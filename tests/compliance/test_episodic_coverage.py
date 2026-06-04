"""
Integration tests for episodic completeness check — TASK-006.

Uses in-memory stub repositories; no live PostgreSQL required.
Seeds workflow runs and invocation counts, then calls ComplianceCheckService
and asserts on CoverageReport results.

PLAN-N-012 AC-001
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest

from src.compliance.compliance_check_service import (
    ComplianceCheckService,
    IComplianceRepository,
    IRecommendationRepository,
    RecommendationWithOutcome,
    WorkflowRunSummary,
)


# ── Stubs ─────────────────────────────────────────────────────────────────────


class MutableComplianceRepo(IComplianceRepository):
    """Mutable stub that simulates adding/removing workflow runs and invocations."""

    def __init__(self) -> None:
        self._runs: list[WorkflowRunSummary] = []
        self._invocation_counts: dict[UUID, int] = {}

    def add_run(self, wid: UUID | None = None, workflow_type: str = "on_demand") -> UUID:
        wid = wid or uuid4()
        now = datetime.now(tz=timezone.utc)
        self._runs.append(
            WorkflowRunSummary(
                workflow_id=wid,
                workflow_type=workflow_type,
                started_at=now - timedelta(minutes=5),
                completed_at=now - timedelta(minutes=1),
            )
        )
        return wid

    def set_invocations(self, wid: UUID, count: int) -> None:
        self._invocation_counts[wid] = count

    async def list_completed_runs_in_window(
        self, lookback_days: int
    ) -> list[WorkflowRunSummary]:
        return list(self._runs)

    async def count_invocations_for_run(self, workflow_id: UUID) -> int:
        return self._invocation_counts.get(workflow_id, 0)


class StubRecommendationRepo(IRecommendationRepository):
    async def list_by_company(
        self, company_id: UUID, limit: int
    ) -> list[RecommendationWithOutcome]:
        return []

    async def get_company_ticker(self, company_id: UUID) -> str | None:
        return None


def _service(repo: MutableComplianceRepo) -> ComplianceCheckService:
    return ComplianceCheckService(
        compliance_repo=repo,
        recommendation_repo=StubRecommendationRepo(),
        disclaimer_threshold=5,
    )


# ── Integration test: seed 10, cover 8, then fill the 2 gaps ─────────────────


@pytest.mark.asyncio
async def test_coverage_check_initial_80_pct_then_100_pct() -> None:
    """
    Seed 10 workflow_run rows with status='done'.
    Seed agent_invocation rows for 8 of them.
    Assert coverage_pct=80.0 and 2 gap run IDs.
    Then seed invocations for the 2 gap runs and assert coverage_pct=100.0.
    """
    repo = MutableComplianceRepo()

    # Seed 10 runs; record IDs
    all_wids = [repo.add_run() for _ in range(10)]

    # Seed invocations for 8 of them (indices 0–7); leave indices 8 and 9 as gaps
    gap_wids = {all_wids[8], all_wids[9]}
    for wid in all_wids[:8]:
        repo.set_invocations(wid, 2)

    service = _service(repo)
    report = await service.run_coverage_check(lookback_days=90)

    assert report.coverage_pct == pytest.approx(80.0)
    assert report.runs_with_zero_invocations == 2
    assert len(report.gaps) == 2
    reported_gap_ids = {g.workflow_run_id for g in report.gaps}
    assert reported_gap_ids == gap_wids

    # Fill the 2 gap runs with invocations
    for wid in gap_wids:
        repo.set_invocations(wid, 1)

    report2 = await service.run_coverage_check(lookback_days=90)

    assert report2.coverage_pct == pytest.approx(100.0)
    assert report2.gaps == []
    assert report2.runs_with_zero_invocations == 0
    assert report2.total_completed_runs == 10


@pytest.mark.asyncio
async def test_coverage_check_all_have_invocations() -> None:
    """All 5 runs have invocations → coverage_pct=100.0."""
    repo = MutableComplianceRepo()
    wids = [repo.add_run() for _ in range(5)]
    for wid in wids:
        repo.set_invocations(wid, 1)

    report = await _service(repo).run_coverage_check(lookback_days=90)
    assert report.coverage_pct == pytest.approx(100.0)
    assert report.gaps == []


@pytest.mark.asyncio
async def test_coverage_check_zero_runs_is_vacuously_compliant() -> None:
    """Zero completed runs in window → coverage_pct=100.0 (vacuously compliant)."""
    repo = MutableComplianceRepo()
    report = await _service(repo).run_coverage_check(lookback_days=90)
    assert report.coverage_pct == pytest.approx(100.0)
    assert report.total_completed_runs == 0
    assert report.gaps == []


@pytest.mark.asyncio
async def test_coverage_gap_contains_correct_workflow_metadata() -> None:
    """Gap record contains correct workflow_type and timestamps from the run."""
    repo = MutableComplianceRepo()
    wid = repo.add_run(workflow_type="earnings_brief")
    # No invocations → gap

    report = await _service(repo).run_coverage_check(lookback_days=90)
    assert len(report.gaps) == 1
    gap = report.gaps[0]
    assert gap.workflow_run_id == wid
    assert gap.workflow_type == "earnings_brief"
    assert gap.agent_invocation_count == 0
