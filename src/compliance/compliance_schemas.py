"""
compliance.compliance_schemas — Pydantic DTOs for compliance and auditability.

REQ-N-012: Defines data shapes for:
  - CoverageGap / CoverageReport — episodic completeness check
  - TrackRecordEntry / TrackRecordResponse — ex-post accuracy visibility
  - DisclaimerAuditResult — internal audit (non-user-facing)

SIGNAL_DIRECTION_MAP maps action_signal values to directional intent
for direction_correct percentage computation:
  +1 (long)  — BUY_OPP, CONTRARIAN
   0 (neutral) — HOLD, WATCH  (excluded from direction-correct pct)
  -1 (short) — REDUCE_RISK, HEDGE
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

# Direction map used by ComplianceCheckService.get_company_track_record.
# HOLD and WATCH have direction 0 and are excluded from the pct calculation.
SIGNAL_DIRECTION_MAP: dict[str, int] = {
    "BUY_OPP": 1,
    "CONTRARIAN": 1,
    "HOLD": 0,
    "WATCH": 0,
    "REDUCE_RISK": -1,
    "HEDGE": -1,
}


# ── Episodic coverage ─────────────────────────────────────────────────────────


class CoverageGap(BaseModel):
    """A workflow run with zero agent_invocation rows — a completeness gap."""

    workflow_run_id: UUID
    workflow_type: str
    started_at: datetime
    completed_at: datetime | None
    agent_invocation_count: int  # always 0 in a gap row


class CoverageReport(BaseModel):
    """Aggregated result of one episodic completeness check run."""

    checked_at: datetime
    lookback_days: int
    total_completed_runs: int
    runs_with_zero_invocations: int
    coverage_pct: float  # (total - gaps) / total * 100; 100.0 when total is 0
    gaps: list[CoverageGap]  # empty when coverage_pct == 100.0


# ── Track record (ex-post accuracy) ──────────────────────────────────────────


class TrackRecordEntry(BaseModel):
    """One historical recommendation with ex-post outcome data."""

    rec_id: UUID
    company_ticker: str
    action_signal: str  # HOLD | WATCH | BUY_OPP | REDUCE_RISK | HEDGE | CONTRARIAN
    confidence: float
    sample_size: int
    generated_at: datetime
    actual_t1d: float | None
    actual_t1w: float | None
    accuracy: float | None
    disclaimer_required: bool  # True when sample_size < DISCLAIMER_SAMPLE_SIZE_THRESHOLD


class TrackRecordResponse(BaseModel):
    """Company-level track record with aggregate accuracy percentages."""

    company_id: UUID
    company_ticker: str
    entries: list[TrackRecordEntry]
    total: int
    direction_correct_t1d_pct: float | None  # None when no actuals yet
    direction_correct_t1w_pct: float | None


# ── Disclaimer audit (internal) ───────────────────────────────────────────────


class DisclaimerAuditResult(BaseModel):
    """Returned by internal audit endpoint; not user-facing."""

    audited_at: datetime
    sample_checked: int
    disclaimer_present_count: int
    disclaimer_missing_count: int
    missing_rec_ids: list[UUID]
