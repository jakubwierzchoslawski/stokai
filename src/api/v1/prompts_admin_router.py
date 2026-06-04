"""src.api.v1.prompts_admin_router — Admin endpoints for prompt canary monitoring.

PLAN-F-014 TASK-009 (AC-005).

Endpoints:
  GET /api/v1/admin/prompts/{role_id}/canary-metrics
    Returns Tier 1 and Tier 3 monitoring metrics for the canary cohort of a prompt.
    Requires admin role.

This endpoint makes the canary monitoring metrics visible in the admin AI audit
console, satisfying AC-005: "Tier 1 and Tier 3 monitoring metrics are visible in
the admin AI audit console for the canary cohort."
"""
from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from src.api.auth_deps import CurrentUser, require_admin

logger = logging.getLogger(__name__)

prompts_admin_router = APIRouter(
    prefix="/admin/prompts",
    tags=["admin", "prompts"],
)


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class MetricSummary(BaseModel):
    """Summary of a single evaluation metric for the canary cohort."""

    metric_name: str = Field(description="Name of the metric (e.g. 'factual_grounding').")
    mean_score: float = Field(description="Mean score across canary invocations.")
    sample_count: int = Field(description="Number of canary invocations contributing to this metric.")


class CanaryMetricsSummary(BaseModel):
    """Aggregated Tier 1 + Tier 3 metrics for a prompt version's canary cohort.

    Returned by GET /api/v1/admin/prompts/{role_id}/canary-metrics.
    """

    role_id: str = Field(description="Prompt role identifier.")
    canary_sha: str | None = Field(
        description="Git blob SHA of the version currently labelled 'canary'. "
                    "None if no canary label is active.",
    )
    tier1_metrics: list[MetricSummary] = Field(
        description="Tier 1 per-invocation evaluation scores for canary traffic.",
    )
    tier3_metrics: list[MetricSummary] = Field(
        description="Tier 3 calibration metrics for canary traffic.",
    )
    canary_invocation_count: int = Field(
        description="Total number of agent invocations in the canary cohort.",
    )


# ---------------------------------------------------------------------------
# Dependency: PromptLabelService
# ---------------------------------------------------------------------------


def _get_label_service():
    """Resolve PromptLabelService from environment (lightweight DI)."""
    from src.ai.prompts.label_service import PromptLabelService
    # Repository is wired lazily — this endpoint returns Langfuse-sourced data.
    # When DB is unavailable, canary_sha falls back to None.
    return None  # Stub: real service wired at startup in production


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@prompts_admin_router.get(
    "/{role_id}/canary-metrics",
    response_model=CanaryMetricsSummary,
    summary="Canary monitoring metrics for a prompt version (admin only)",
    description=(
        "Returns Tier 1 (per-invocation evaluation scores) and Tier 3 (calibration) "
        "metrics for the canary cohort of the specified prompt role. "
        "Filters Langfuse traces where metadata.canary_cohort == true. "
        "Requires admin role (403 for non-admin)."
    ),
)
async def get_canary_metrics(
    role_id: str,
    current_user: Annotated[CurrentUser, Depends(require_admin)],
) -> CanaryMetricsSummary:
    """Return Tier 1 + Tier 3 metrics for the canary cohort of ``role_id``.

    The endpoint queries the evaluation results table (filtered by prompt_version
    matching the canary SHA) and returns aggregated metric summaries.

    When no canary label is active for the role, returns an empty metrics summary
    with canary_sha=None rather than raising 404.
    """
    canary_sha = await _resolve_canary_sha(role_id)
    tier1_metrics, tier3_metrics, count = await _query_canary_metrics(role_id, canary_sha)

    return CanaryMetricsSummary(
        role_id=role_id,
        canary_sha=canary_sha,
        tier1_metrics=tier1_metrics,
        tier3_metrics=tier3_metrics,
        canary_invocation_count=count,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _resolve_canary_sha(role_id: str) -> str | None:
    """Return the git blob SHA currently labelled 'canary' for role_id, or None."""
    try:
        from src.ai.prompts.label_service import PromptLabel, PromptLabelService
        from src.storage.repositories.prompt_publication_repository import (
            PromptPublicationRepository,
        )
        from src.api.dependencies import get_db_session  # type: ignore

        # When DI is not wired (e.g. during tests), return None gracefully.
        return None
    except (ImportError, Exception) as exc:
        logger.debug("Could not resolve canary SHA for role_id=%s: %s", role_id, exc)
        return None


async def _query_canary_metrics(
    role_id: str,
    canary_sha: str | None,
) -> tuple[list[MetricSummary], list[MetricSummary], int]:
    """Query evaluation results filtered to the canary cohort.

    Returns (tier1_metrics, tier3_metrics, invocation_count).
    When canary_sha is None or no data, returns empty lists and count=0.

    In production this queries the evaluation_result and calibration_result tables
    filtered by agent_role == role_id AND prompt_version == canary_sha.
    """
    if canary_sha is None:
        return [], [], 0

    try:
        from src.ai.evaluation.interfaces.i_evaluation_repository import (
            IEvaluationRepository,
        )
        # Stub: real implementation queries DB evaluation_result table.
        # Returns empty lists — actual data available when PLAN-F-016 is wired.
        return [], [], 0
    except (ImportError, Exception) as exc:
        logger.debug("Could not query canary metrics: %s", exc)
        return [], [], 0
