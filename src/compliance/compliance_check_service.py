"""
compliance.compliance_check_service — ComplianceCheckService implementation.

REQ-N-012: Episodic completeness enforcement and ex-post accuracy visibility.

Depends on IComplianceRepository (defined here) which is a narrow read-only
interface that queries workflow_run, agent_invocation, and recommendation
tables. This avoids coupling the compliance module to the full
IEpisodicRepository contract.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from uuid import UUID

from src.compliance.compliance_schemas import (
    SIGNAL_DIRECTION_MAP,
    CoverageGap,
    CoverageReport,
    TrackRecordEntry,
    TrackRecordResponse,
)


# ── Data transfer objects used by the repository contract ────────────────────


class WorkflowRunSummary:
    """Minimal data the service needs from a workflow_run row."""

    __slots__ = ("workflow_id", "workflow_type", "started_at", "completed_at")

    def __init__(
        self,
        workflow_id: UUID,
        workflow_type: str,
        started_at: datetime,
        completed_at: datetime | None,
    ) -> None:
        self.workflow_id = workflow_id
        self.workflow_type = workflow_type
        self.started_at = started_at
        self.completed_at = completed_at


class RecommendationWithOutcome:
    """Joined recommendation + optional outcome row."""

    __slots__ = (
        "rec_id",
        "company_ticker",
        "action_signal",
        "confidence",
        "sample_size",
        "generated_at",
        "actual_t1d",
        "actual_t1w",
        "accuracy",
    )

    def __init__(
        self,
        rec_id: UUID,
        company_ticker: str,
        action_signal: str,
        confidence: float,
        sample_size: int,
        generated_at: datetime,
        actual_t1d: float | None,
        actual_t1w: float | None,
        accuracy: float | None,
    ) -> None:
        self.rec_id = rec_id
        self.company_ticker = company_ticker
        self.action_signal = action_signal
        self.confidence = confidence
        self.sample_size = sample_size
        self.generated_at = generated_at
        self.actual_t1d = actual_t1d
        self.actual_t1w = actual_t1w
        self.accuracy = accuracy


# ── Repository interfaces ─────────────────────────────────────────────────────


class IComplianceRepository(ABC):
    """
    Narrow read-only repository interface for compliance checks.

    Implementations query the episodic and recommendation tables directly
    via SQLAlchemy; the compliance module does not depend on the full
    IEpisodicRepository contract.
    """

    @abstractmethod
    async def list_completed_runs_in_window(
        self,
        lookback_days: int,
    ) -> list[WorkflowRunSummary]:
        """
        Return all workflow_run rows with status IN ('done', 'failed', 'completed')
        and completed_at >= NOW() - INTERVAL ':days days'.
        """
        ...

    @abstractmethod
    async def count_invocations_for_run(self, workflow_id: UUID) -> int:
        """Return the number of agent_invocation rows for a given workflow_id."""
        ...


class IRecommendationRepository(ABC):
    """
    Narrow read-only repository interface for track record queries.

    Implementations join ai_recommendation with recommendation_outcome.
    """

    @abstractmethod
    async def list_by_company(
        self,
        company_id: UUID,
        limit: int,
    ) -> list[RecommendationWithOutcome]:
        """
        Return up to `limit` recommendations for a company ordered by
        generated_at DESC, joined with recommendation_outcome where available.
        """
        ...

    @abstractmethod
    async def get_company_ticker(self, company_id: UUID) -> str | None:
        """Return the ticker symbol for a company, or None if not found."""
        ...


# ── Service interface ─────────────────────────────────────────────────────────


class IComplianceCheckService(ABC):
    """Abstract compliance check service."""

    @abstractmethod
    async def run_coverage_check(self, lookback_days: int) -> CoverageReport:
        """
        Check episodic completeness for all completed workflow runs in the
        lookback window. Returns a CoverageReport with gap details.
        """
        ...

    @abstractmethod
    async def get_company_track_record(
        self,
        company_id: UUID,
        limit: int = 50,
    ) -> TrackRecordResponse:
        """
        Return ex-post accuracy track record for a company.
        """
        ...


# ── Concrete service ──────────────────────────────────────────────────────────


class ComplianceCheckService(IComplianceCheckService):
    """
    Concrete implementation of IComplianceCheckService.

    Constructor-injected dependencies:
      - compliance_repo: IComplianceRepository
      - recommendation_repo: IRecommendationRepository
      - disclaimer_threshold: int  (from settings.DISCLAIMER_SAMPLE_SIZE_THRESHOLD)
    """

    def __init__(
        self,
        compliance_repo: IComplianceRepository,
        recommendation_repo: IRecommendationRepository,
        disclaimer_threshold: int = 5,
    ) -> None:
        self._compliance_repo = compliance_repo
        self._recommendation_repo = recommendation_repo
        self._disclaimer_threshold = disclaimer_threshold

    async def run_coverage_check(self, lookback_days: int) -> CoverageReport:
        """
        Episodic completeness check.

        1. Fetch all completed workflow runs in the lookback window.
        2. For each run, count agent_invocation rows.
        3. Collect runs with zero invocations as CoverageGap records.
        4. Compute coverage_pct (100.0 when no completed runs — vacuously compliant).
        """
        runs = await self._compliance_repo.list_completed_runs_in_window(lookback_days)
        total = len(runs)
        gaps: list[CoverageGap] = []

        for run in runs:
            count = await self._compliance_repo.count_invocations_for_run(run.workflow_id)
            if count == 0:
                gaps.append(
                    CoverageGap(
                        workflow_run_id=run.workflow_id,
                        workflow_type=run.workflow_type,
                        started_at=run.started_at,
                        completed_at=run.completed_at,
                        agent_invocation_count=0,
                    )
                )

        gap_count = len(gaps)
        coverage_pct = 100.0 if total == 0 else (total - gap_count) / total * 100.0

        return CoverageReport(
            checked_at=datetime.now(tz=timezone.utc),
            lookback_days=lookback_days,
            total_completed_runs=total,
            runs_with_zero_invocations=gap_count,
            coverage_pct=coverage_pct,
            gaps=gaps,
        )

    async def get_company_track_record(
        self,
        company_id: UUID,
        limit: int = 50,
    ) -> TrackRecordResponse:
        """
        Ex-post accuracy track record for a company.

        1. Query recommendations with outcomes via IRecommendationRepository.
        2. Map to TrackRecordEntry, setting disclaimer_required.
        3. Compute direction_correct_t1d_pct / _t1w_pct over entries with actuals;
           None if no actuals. HOLD and WATCH (direction 0) are excluded from the pct.
        """
        ticker = await self._recommendation_repo.get_company_ticker(company_id) or ""
        rows = await self._recommendation_repo.list_by_company(company_id, limit)

        entries: list[TrackRecordEntry] = []
        for row in rows:
            entries.append(
                TrackRecordEntry(
                    rec_id=row.rec_id,
                    company_ticker=row.company_ticker or ticker,
                    action_signal=row.action_signal,
                    confidence=row.confidence,
                    sample_size=row.sample_size,
                    generated_at=row.generated_at,
                    actual_t1d=row.actual_t1d,
                    actual_t1w=row.actual_t1w,
                    accuracy=row.accuracy,
                    disclaimer_required=row.sample_size < self._disclaimer_threshold,
                )
            )

        direction_correct_t1d_pct = _compute_direction_pct(entries, "t1d")
        direction_correct_t1w_pct = _compute_direction_pct(entries, "t1w")

        return TrackRecordResponse(
            company_id=company_id,
            company_ticker=ticker,
            entries=entries,
            total=len(entries),
            direction_correct_t1d_pct=direction_correct_t1d_pct,
            direction_correct_t1w_pct=direction_correct_t1w_pct,
        )


# ── Direction-correct helpers ─────────────────────────────────────────────────


def _compute_direction_pct(
    entries: list[TrackRecordEntry],
    horizon: str,  # "t1d" or "t1w"
) -> float | None:
    """
    Compute the percentage of directional predictions that were correct.

    Only entries where:
      - actual_{horizon} is not None
      - SIGNAL_DIRECTION_MAP[action_signal] != 0  (HOLD/WATCH excluded)

    are included.  Returns None when no qualifying entries exist.
    """
    total_directional = 0
    correct = 0

    for entry in entries:
        direction = SIGNAL_DIRECTION_MAP.get(entry.action_signal, 0)
        if direction == 0:
            continue

        actual = entry.actual_t1d if horizon == "t1d" else entry.actual_t1w
        if actual is None:
            continue

        total_directional += 1
        if direction * actual > 0:
            correct += 1

    if total_directional == 0:
        return None

    return correct / total_directional * 100.0
