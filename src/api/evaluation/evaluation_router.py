"""
FastAPI router for the evaluation framework.

All endpoints require admin role (403 for non-admin, 401 for unauthenticated).

Endpoints:
  GET  /evaluation/results                           — list recent evaluation results
  GET  /evaluation/results/{run_id}                  — results for a specific run
  GET  /evaluation/golden-dataset                    — list active golden dataset items
  GET  /evaluation/golden-dataset/candidates         — list candidate items
  POST /evaluation/golden-dataset                    → 201
  POST /evaluation/golden-dataset/{item_id}/approve  → 200
  DELETE /evaluation/golden-dataset/{item_id}        → 204
  GET  /evaluation/calibration                       — list recent calibration rows
  GET  /evaluation/calibration/summary               — 30-day summary
  POST /evaluation/calibration/reviews               → 201 (admin only)
  GET  /evaluation/calibration/reviews               — list recent reviews (admin only)
"""
from __future__ import annotations

import logging
from typing import Annotated, Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.ai.evaluation.interfaces.i_calibration_repository import (
    ICalibrationRepository,
)
from src.ai.evaluation.interfaces.i_calibration_review_repository import (
    ICalibrationReviewRepository,
)
from src.ai.evaluation.interfaces.i_evaluation_repository import (
    IEvaluationRepository,
)
from src.ai.evaluation.interfaces.i_golden_dataset_repository import (
    IGoldenDatasetRepository,
)
from src.ai.evaluation.repositories.calibration_repository import (
    CalibrationRepository,
)
from src.ai.evaluation.repositories.evaluation_repository import (
    EvaluationRepository,
)
from src.ai.evaluation.repositories.golden_dataset_repository import (
    GoldenDatasetRepository,
)
from src.ai.evaluation.schemas.calibration_schemas import (
    CalibrationResult,
    CalibrationSummary,
)
from src.ai.evaluation.schemas.calibration_review_schemas import (
    CalibrationReview,
)
from src.ai.evaluation.schemas.evaluation_schemas import (
    EvaluationResult,
    EvaluationResultCreate,
)
from src.ai.evaluation.schemas.golden_dataset_schemas import (
    GoldenDatasetItem,
    GoldenDatasetItemCreate,
)
from src.ai.evaluation.services.calibration_review_service import (
    CalibrationReviewService,
)
from src.api.auth_deps import CurrentUser, require_admin
from src.api.evaluation.evaluation_api_schemas import (
    CalibrationReviewRequest,
    CalibrationReviewResponse,
)
from src.config.settings import get_settings

logger = logging.getLogger(__name__)

evaluation_router = APIRouter(
    prefix="/evaluation",
    tags=["evaluation"],
)

# ── Dependency providers ───────────────────────────────────────────────────────

# These are module-level callable dependencies. Tests can override them via
# app.dependency_overrides[get_evaluation_repo] = lambda: mock_repo.


def get_evaluation_repo() -> IEvaluationRepository:
    """Stub — override in tests or wire with a real DB session via Depends."""
    raise NotImplementedError(
        "get_evaluation_repo must be overridden with a real session-backed repo."
    )


def get_golden_dataset_repo() -> IGoldenDatasetRepository:
    """Stub — override in tests or wire with a real DB session via Depends."""
    raise NotImplementedError(
        "get_golden_dataset_repo must be overridden with a real session-backed repo."
    )


def get_calibration_repo() -> ICalibrationRepository:
    """Stub — override in tests or wire with a real DB session via Depends."""
    raise NotImplementedError(
        "get_calibration_repo must be overridden with a real session-backed repo."
    )


def get_calibration_review_repo() -> ICalibrationReviewRepository:
    """Stub — override in tests or wire with a real DB session via Depends."""
    raise NotImplementedError(
        "get_calibration_review_repo must be overridden with a real session-backed repo."
    )


# ── /evaluation/results ────────────────────────────────────────────────────────


@evaluation_router.get(
    "/results",
    response_model=list[EvaluationResult],
    summary="List recent evaluation results (admin only)",
)
async def list_evaluation_results(
    limit: int = Query(default=100, ge=1, le=1000),
    _admin: CurrentUser = Depends(require_admin),
    repo: IEvaluationRepository = Depends(get_evaluation_repo),
) -> list[EvaluationResult]:
    """Return the most recent evaluation results."""
    return await repo.list_recent(limit=limit)


@evaluation_router.post(
    "/results",
    response_model=EvaluationResult,
    status_code=status.HTTP_201_CREATED,
    summary="Insert an evaluation result (admin only)",
)
async def create_evaluation_result(
    body: EvaluationResultCreate,
    _admin: CurrentUser = Depends(require_admin),
    repo: IEvaluationRepository = Depends(get_evaluation_repo),
) -> EvaluationResult:
    """Insert a new evaluation result row."""
    return await repo.insert_result(body)


@evaluation_router.get(
    "/results/{run_id}",
    response_model=list[EvaluationResult],
    summary="Get evaluation results for a run (admin only)",
)
async def get_evaluation_results_for_run(
    run_id: UUID,
    _admin: CurrentUser = Depends(require_admin),
    repo: IEvaluationRepository = Depends(get_evaluation_repo),
) -> list[EvaluationResult]:
    """Return all evaluation results for a specific workflow run."""
    return await repo.get_results_for_run(run_id)


# ── /evaluation/golden-dataset ────────────────────────────────────────────────


@evaluation_router.get(
    "/golden-dataset",
    response_model=list[GoldenDatasetItem],
    summary="List active golden dataset items (admin only)",
)
async def list_golden_dataset_active(
    _admin: CurrentUser = Depends(require_admin),
    repo: IGoldenDatasetRepository = Depends(get_golden_dataset_repo),
) -> list[GoldenDatasetItem]:
    """Return all active golden dataset items."""
    return await repo.list_active()


@evaluation_router.get(
    "/golden-dataset/candidates",
    response_model=list[GoldenDatasetItem],
    summary="List golden dataset candidates (admin only)",
)
async def list_golden_dataset_candidates(
    _admin: CurrentUser = Depends(require_admin),
    repo: IGoldenDatasetRepository = Depends(get_golden_dataset_repo),
) -> list[GoldenDatasetItem]:
    """Return all golden dataset items awaiting approval."""
    return await repo.list_candidates()


@evaluation_router.post(
    "/golden-dataset",
    response_model=GoldenDatasetItem,
    status_code=status.HTTP_201_CREATED,
    summary="Create a golden dataset candidate (admin only)",
)
async def create_golden_dataset_item(
    body: GoldenDatasetItemCreate,
    _admin: CurrentUser = Depends(require_admin),
    repo: IGoldenDatasetRepository = Depends(get_golden_dataset_repo),
) -> GoldenDatasetItem:
    """Insert a new golden dataset item as an inactive candidate."""
    return await repo.create_item(body)


@evaluation_router.post(
    "/golden-dataset/{item_id}/approve",
    response_model=GoldenDatasetItem,
    summary="Approve a golden dataset candidate (admin only)",
)
async def approve_golden_dataset_item(
    item_id: UUID,
    admin: CurrentUser = Depends(require_admin),
    repo: IGoldenDatasetRepository = Depends(get_golden_dataset_repo),
) -> GoldenDatasetItem:
    """Activate a golden dataset candidate, recording the approver."""
    return await repo.activate_item(item_id, admin.user_id)


@evaluation_router.delete(
    "/golden-dataset/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Deactivate a golden dataset item (admin only)",
)
async def delete_golden_dataset_item(
    item_id: UUID,
    _admin: CurrentUser = Depends(require_admin),
    repo: IGoldenDatasetRepository = Depends(get_golden_dataset_repo),
) -> None:
    """Set active=False on a golden dataset item."""
    await repo.deactivate_item(item_id)


# ── /evaluation/calibration ───────────────────────────────────────────────────


@evaluation_router.get(
    "/calibration",
    response_model=list[CalibrationResult],
    summary="List recent calibration results (admin only)",
)
async def list_calibration_results(
    days: int = Query(default=30, ge=1, le=365),
    action_signal: Optional[str] = Query(default=None),
    _admin: CurrentUser = Depends(require_admin),
    repo: ICalibrationRepository = Depends(get_calibration_repo),
) -> list[CalibrationResult]:
    """Return calibration results for the last N days."""
    return await repo.list_last_n_days(days=days, action_signal=action_signal)


@evaluation_router.get(
    "/calibration/summary",
    response_model=CalibrationSummary,
    summary="Get 30-day calibration summary (admin only)",
)
async def get_calibration_summary(
    days: int = Query(default=30, ge=1, le=365),
    _admin: CurrentUser = Depends(require_admin),
    repo: ICalibrationRepository = Depends(get_calibration_repo),
) -> CalibrationSummary:
    """
    Return aggregated calibration summary.

    assessment:
      - 'Healthy' when rolling_corr >= 0.3 and total_recommendations >= 30
      - 'Warning: CORR below threshold — improvement loop recommended' when < 0.3
        and total_recommendations >= 30
      - 'Insufficient data' when total_recommendations < 30
    """
    settings = get_settings()
    _threshold = settings.CALIBRATION_CORR_THRESHOLD
    _min_sample = settings.CALIBRATION_MIN_SAMPLE

    results = await repo.list_last_n_days(days=days)
    rolling_corr = await repo.get_rolling_corr(days=days)

    total = sum(r.total_recommendations for r in results)

    per_signal: dict[str, float] = {}
    for r in results:
        signal = r.action_signal
        if signal not in per_signal:
            per_signal[signal] = r.direction_correct_pct
        else:
            # Simple average across days for the same signal
            per_signal[signal] = (per_signal[signal] + r.direction_correct_pct) / 2.0

    below_threshold = False
    if total >= _min_sample and rolling_corr is not None:
        below_threshold = rolling_corr < _threshold

    if total < _min_sample:
        assessment = "Insufficient data"
    elif below_threshold:
        assessment = "Warning: CORR below threshold — improvement loop recommended"
    else:
        assessment = "Healthy"

    return CalibrationSummary(
        days=days,
        total_recommendations=total,
        per_signal_accuracy=per_signal,
        rolling_corr=rolling_corr,
        below_threshold=below_threshold,
        assessment=assessment,
    )


# ── /evaluation/calibration/reviews ──────────────────────────────────────────


@evaluation_router.post(
    "/calibration/reviews",
    response_model=CalibrationReviewResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record a weekly calibration review (admin only)",
)
async def create_calibration_review(
    body: CalibrationReviewRequest,
    admin: CurrentUser = Depends(require_admin),
    cal_repo: ICalibrationRepository = Depends(get_calibration_repo),
    review_repo: ICalibrationReviewRepository = Depends(get_calibration_review_repo),
) -> CalibrationReviewResponse:
    """
    Record an admin calibration review decision.

    Reads the current rolling CORR from the calibration repository, derives
    below_threshold, persists the review, and returns it with a 201 status.
    """
    service = CalibrationReviewService(
        review_repo=review_repo,
        calibration_repo=cal_repo,
    )
    review = await service.record_review(
        reviewed_by=admin.user_id,
        action_taken=body.action_taken,
        notes=body.notes,
    )
    return CalibrationReviewResponse(
        review_id=review.review_id,
        reviewed_by=review.reviewed_by,
        reviewed_at=review.reviewed_at,
        corr_at_review=review.corr_at_review,
        below_threshold=review.below_threshold,
        action_taken=review.action_taken,
        notes=review.notes,
    )


@evaluation_router.get(
    "/calibration/reviews",
    response_model=list[CalibrationReviewResponse],
    summary="List recent calibration reviews (admin only)",
)
async def list_calibration_reviews(
    limit: int = Query(default=10, ge=1, le=100),
    _admin: CurrentUser = Depends(require_admin),
    cal_repo: ICalibrationRepository = Depends(get_calibration_repo),
    review_repo: ICalibrationReviewRepository = Depends(get_calibration_review_repo),
) -> list[CalibrationReviewResponse]:
    """Return the most recent calibration reviews in descending order."""
    service = CalibrationReviewService(
        review_repo=review_repo,
        calibration_repo=cal_repo,
    )
    reviews = await service.list_reviews(limit=limit)
    return [
        CalibrationReviewResponse(
            review_id=r.review_id,
            reviewed_by=r.reviewed_by,
            reviewed_at=r.reviewed_at,
            corr_at_review=r.corr_at_review,
            below_threshold=r.below_threshold,
            action_taken=r.action_taken,
            notes=r.notes,
        )
        for r in reviews
    ]
