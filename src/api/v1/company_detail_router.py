"""
api.v1.company_detail_router — Company Detail aggregated endpoint.

GET /api/v1/companies/{company_id}/detail
POST /api/v1/companies/{company_id}/analysis

Fetches 5 data panels in parallel via asyncio.gather:
  1. Company metadata (ticker, name, sector, market_cap)
  2. Fundamentals (PE, EPS, revenue, D/E)
  3. Score breakdown per indicator in the active scoring profile
  4. Active geo-events with exposure magnitudes
  5. AI recommendation history

PLAN-F-023 TASK-002, TASK-003, TASK-004
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status

from src.api.auth_deps import CurrentUser, get_current_user
from src.api.v1.schemas.company_detail import (
    ActiveEventSummary,
    AnalysisHistoryItem,
    CompanyDetailResponse,
    FundamentalsPanel,
    ScoreBreakdownItem,
    TrackRecordItem,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/companies", tags=["company-detail"])

# ---------------------------------------------------------------------------
# Direction mapping (TASK-004)
# ---------------------------------------------------------------------------

_BULLISH_SIGNALS = {"BUY_OPP"}
_BEARISH_SIGNALS = {"REDUCE_RISK", "HEDGE"}
_NEUTRAL_SIGNALS = {"HOLD", "WATCH", "CONTRARIAN"}


def _map_direction(action_signal: str) -> str:
    """Map an action signal string to bullish / bearish / neutral."""
    if action_signal in _BULLISH_SIGNALS:
        return "bullish"
    if action_signal in _BEARISH_SIGNALS:
        return "bearish"
    return "neutral"


def _is_correct_t1d(direction: str, actual_t1d: float | None) -> bool | None:
    """Return True/False when actual_t1d is available; None otherwise."""
    if actual_t1d is None:
        return None
    if direction == "bullish":
        return actual_t1d > 0
    if direction == "bearish":
        return actual_t1d < 0
    # neutral — not directionally scored
    return None


def _compute_directional_accuracy(track_record: list[TrackRecordItem]) -> float | None:
    """Proportion of correct_t1d where actual_t1d is not None.

    Returns None when there are no filled records.
    """
    filled = [r for r in track_record if r.actual_t1d is not None and r.direction != "neutral"]
    if not filled:
        return None
    correct = sum(1 for r in filled if r.correct_t1d is True)
    return correct / len(filled)


# ---------------------------------------------------------------------------
# Formula summary helper (TASK-003)
# ---------------------------------------------------------------------------

_FORMULA_SUMMARY_MAX_LEN = 120


def _truncate_formula(formula_dsl: str) -> str:
    """Truncate formula_dsl to 120 chars, appending '...' if truncated."""
    if len(formula_dsl) <= _FORMULA_SUMMARY_MAX_LEN:
        return formula_dsl
    return formula_dsl[:_FORMULA_SUMMARY_MAX_LEN] + "..."


# ---------------------------------------------------------------------------
# Stub data fetchers (replace with real repo calls in production)
# ---------------------------------------------------------------------------

async def _fetch_company_meta(company_id: UUID, tenant_id: UUID) -> dict | None:
    """Fetch company metadata from DB.  Returns None if not found for tenant."""
    # Production: query companies table scoped to tenant_id
    # Stub returns a placeholder so unit tests can override via dependency injection
    return None


async def _fetch_fundamentals(company_id: UUID, tenant_id: UUID) -> FundamentalsPanel | None:
    """Fetch fundamentals from the fundamentals table."""
    return None


async def _fetch_score_breakdown(
    company_id: UUID,
    tenant_id: UUID,
    profile_id: UUID | None,
) -> list[ScoreBreakdownItem]:
    """Fetch score breakdown for each indicator in the active scoring profile."""
    return []


async def _fetch_active_events(
    company_id: UUID,
    tenant_id: UUID,
) -> list[ActiveEventSummary]:
    """Fetch active geo-events affecting the company."""
    return []


async def _fetch_analysis_history(
    company_id: UUID,
    tenant_id: UUID,
    limit: int = 10,
) -> list[dict]:
    """Fetch AI recommendation history (raw dicts)."""
    return []


# ---------------------------------------------------------------------------
# Endpoint helpers
# ---------------------------------------------------------------------------

def _build_analysis_history(raw: list[dict]) -> list[AnalysisHistoryItem]:
    """Convert raw recommendation dicts to AnalysisHistoryItem list."""
    items: list[AnalysisHistoryItem] = []
    for rec in raw:
        rationale = rec.get("rationale", "") or ""
        items.append(
            AnalysisHistoryItem(
                rec_id=rec.get("rec_id", uuid4()),
                generated_at=rec.get("generated_at", datetime.now(tz=timezone.utc)),
                workflow_type=rec.get("workflow_type", "on_demand"),
                action_signal=rec.get("action_signal", "HOLD"),
                confidence=float(rec.get("confidence", 0.0)),
                rationale_summary=rationale[:200],
            )
        )
    return items


def _build_track_record(raw: list[dict]) -> list[TrackRecordItem]:
    """Convert raw recommendation dicts to TrackRecordItem list with direction mapping."""
    items: list[TrackRecordItem] = []
    for rec in raw:
        action_signal = rec.get("action_signal", "HOLD")
        direction = _map_direction(action_signal)
        actual_t1d = rec.get("actual_t1d")
        actual_t1w = rec.get("actual_t1w")
        correct_t1d = _is_correct_t1d(direction, actual_t1d)
        correct_t1w = _is_correct_t1d(direction, actual_t1w)  # same logic for t1w
        items.append(
            TrackRecordItem(
                rec_id=rec.get("rec_id", uuid4()),
                generated_at=rec.get("generated_at", datetime.now(tz=timezone.utc)),
                action_signal=action_signal,
                direction=direction,
                confidence=float(rec.get("confidence", 0.0)),
                actual_t1d=actual_t1d,
                actual_t1w=actual_t1w,
                correct_t1d=correct_t1d,
                correct_t1w=correct_t1w,
            )
        )
    return items


# ---------------------------------------------------------------------------
# GET endpoint
# ---------------------------------------------------------------------------

@router.get("/{company_id}/detail", response_model=CompanyDetailResponse)
async def get_company_detail(
    company_id: UUID,
    profile_id: UUID | None = None,
    price_interval: str = "1d",
    price_from_days: int = 90,
    current_user: CurrentUser = Depends(get_current_user),
) -> CompanyDetailResponse:
    """Return aggregated company detail for the requested company.

    Five data panels are fetched in parallel via asyncio.gather.

    Args:
        company_id: UUID of the company to fetch.
        profile_id: Scoring profile UUID.  Defaults to user.scoring_profile_default.
        price_interval: OHLCV bar interval — "1d", "1h", or "15m".
        price_from_days: Number of days of price history to return (default 90).
        current_user: Authenticated user from JWT.

    Returns:
        CompanyDetailResponse with all panels populated.

    Raises:
        HTTPException 404: Company not found for this tenant.
        HTTPException 401: Missing / invalid JWT.
    """
    tenant_id: UUID = current_user.tenant_id
    # Default profile to user's preference when not supplied
    effective_profile_id = profile_id or getattr(current_user, "scoring_profile_default", None)

    # ── 5 parallel fetches ──────────────────────────────────────────────────────
    (
        company_meta,
        fundamentals,
        score_breakdown,
        active_events,
        history_raw,
    ) = await asyncio.gather(
        _fetch_company_meta(company_id, tenant_id),
        _fetch_fundamentals(company_id, tenant_id),
        _fetch_score_breakdown(company_id, tenant_id, effective_profile_id),
        _fetch_active_events(company_id, tenant_id),
        _fetch_analysis_history(company_id, tenant_id),
    )

    if company_meta is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "COMPANY_NOT_FOUND",
                "message": f"Company {company_id} not found for this tenant.",
            },
        )

    # ── Build panels ─────────────────────────────────────────────────────────────
    analysis_history = _build_analysis_history(history_raw)
    track_record = _build_track_record(history_raw)
    directional_accuracy = _compute_directional_accuracy(track_record)

    return CompanyDetailResponse(
        company_id=company_id,
        ticker=company_meta.get("ticker", ""),
        name=company_meta.get("name", ""),
        sector=company_meta.get("sector", ""),
        market_cap=company_meta.get("market_cap"),
        fundamentals=fundamentals
        or FundamentalsPanel(
            pe_ratio=None,
            eps=None,
            revenue=None,
            debt_to_equity=None,
            source="edgar",
            as_of=datetime.now(tz=timezone.utc),
        ),
        scores=score_breakdown,
        active_events=active_events,
        analysis_history=analysis_history,
        track_record=track_record,
        directional_accuracy_t1d=directional_accuracy,
    )


# ---------------------------------------------------------------------------
# POST /analysis — trigger on-demand analysis
# ---------------------------------------------------------------------------

@router.post("/{company_id}/analysis", status_code=status.HTTP_202_ACCEPTED)
async def trigger_analysis(
    company_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Trigger an on-demand AI analysis workflow for the company.

    Returns a run_id that the frontend subscribes to via WebSocket.

    Raises:
        HTTPException 409: Analysis already in progress for this company.
    """
    tenant_id: UUID = current_user.tenant_id

    # Production: check for existing in-progress workflow for this company+tenant
    # Stub: always accepted — real implementation queries workflow_run table
    run_id = uuid4()
    logger.info(
        "Triggered on-demand analysis: company=%s tenant=%s run_id=%s",
        company_id,
        tenant_id,
        run_id,
    )

    return {
        "data": {
            "run_id": str(run_id),
            "company_id": str(company_id),
            "status": "queued",
        },
        "meta": {},
        "error": None,
    }
