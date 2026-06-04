"""FastAPI router for Admin AI Audit Console.

All endpoints require admin role (Depends(get_current_admin_user)).
Controllers: parse, validate, check role, delegate to AuditService, respond.
Zero business logic in this module.

Endpoints:
  GET    /api/v1/admin/audit/decisions
  GET    /api/v1/admin/audit/decisions/{decision_id}
  POST   /api/v1/admin/audit/decisions/{decision_id}/override
  GET    /api/v1/admin/audit/prompts/{agent_role}/history
  POST   /api/v1/admin/audit/prompts/{agent_role}/rollback
  GET    /api/v1/admin/audit/calibration
  GET    /api/v1/admin/audit/calibration/summary
  GET    /api/v1/admin/audit/workflows
  GET    /api/v1/admin/audit/workflows/{workflow_id}
  POST   /api/v1/admin/audit/workflows/{workflow_id}/rerun

PLAN-F-029 TASK-006
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.decision_log.interfaces.i_ai_decision_repository import (
    IAIDecisionRepository,
)
from src.ai.decision_log.repositories.ai_decision_repository import (
    AIDecisionRepository,
)
from src.ai.decision_log.schemas.ai_decision_schemas import (
    AIDecisionDetail,
    AIDecisionRow,
    DecisionLogFilter,
)
from src.ai.evaluation.services.golden_dataset_service import GoldenDatasetService
from src.ai.memory.interfaces.i_feedback_repository import IFeedbackRepository
from src.api.admin.audit.audit_api_schemas import (
    AdminOverrideRequest,
    AdminOverrideResponse,
    CalibrationResult,
    CalibrationSummary,
    PromptVersionEntry,
    RerunRequest,
    RerunResponse,
    RollbackRequest,
    RollbackResponse,
    WorkflowRunDetail,
    WorkflowRunSummary,
)
from src.api.admin.audit.audit_service import AuditService, NotFoundError, RollbackError
from src.api.auth.dependencies import get_current_user, get_db
from src.storage.models.user import User, UserRole

audit_router = APIRouter(prefix="/audit", tags=["admin-audit"])


# ── Auth helper ────────────────────────────────────────────────────────────────

async def get_current_admin_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Assert current_user.role == 'admin'; return 403 otherwise."""
    if current_user.role != UserRole.admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "Admin role required"},
        )
    return current_user


# ── Service factory ────────────────────────────────────────────────────────────

def _get_audit_service(
    db: AsyncSession = Depends(get_db),
) -> AuditService:
    """Build AuditService with all dependencies wired."""
    from src.ai.evaluation.interfaces.i_golden_dataset_repository import (
        IGoldenDatasetRepository,
    )
    from src.ai.evaluation.repositories.golden_dataset_repository import (
        GoldenDatasetRepository,
    )
    from src.ai.memory.repositories.feedback_repository import FeedbackRepository

    decision_repo = AIDecisionRepository(db)
    feedback_repo = FeedbackRepository(db)
    golden_dataset_repo = GoldenDatasetRepository(db)
    golden_dataset_service = GoldenDatasetService(golden_dataset_repo)

    # Late imports to avoid circular dependency on optional deps
    try:
        from src.ai.prompts.label_service import PromptLabelService
        prompt_label_service = PromptLabelService()
    except ImportError:
        prompt_label_service = None  # type: ignore[assignment]

    try:
        from src.ai.prompts.repositories.prompt_publication_repository import (
            PromptPublicationRepository,
        )
        prompt_pub_repo = PromptPublicationRepository(db)
    except ImportError:
        prompt_pub_repo = None  # type: ignore[assignment]

    try:
        from src.ai.evaluation.repositories.evaluation_repository import (
            EvaluationRepository,
        )
        eval_repo = EvaluationRepository(db)
    except ImportError:
        eval_repo = None  # type: ignore[assignment]

    try:
        from src.ai.memory.repositories.episodic_repository import EpisodicRepository
        episodic_repo = EpisodicRepository(db)
    except ImportError:
        episodic_repo = None  # type: ignore[assignment]

    try:
        from src.ai.workflows.runner import workflow_runner
    except ImportError:
        workflow_runner = None  # type: ignore[assignment]

    try:
        from src.ai.evaluation.repositories.calibration_repository import (
            CalibrationRepository,
        )
        calibration_repo = CalibrationRepository(db)
    except ImportError:
        calibration_repo = None  # type: ignore[assignment]

    try:
        from src.ai.evaluation.services.tier3_calibration_service import (
            Tier3CalibrationService,
        )
        calibration_service = Tier3CalibrationService(calibration_repo)
    except ImportError:
        calibration_service = None  # type: ignore[assignment]

    return AuditService(
        decision_repo=decision_repo,
        feedback_repo=feedback_repo,
        golden_dataset_service=golden_dataset_service,
        prompt_label_service=prompt_label_service,
        prompt_publication_repo=prompt_pub_repo,
        evaluation_repo=eval_repo,
        episodic_repo=episodic_repo,
        workflow_runner=workflow_runner,
        calibration_repo=calibration_repo,
        calibration_service=calibration_service,
    )


# ── Response helpers ───────────────────────────────────────────────────────────

def _ok(data: Any) -> dict:
    return {"data": data, "meta": {}, "error": None}


def _err(code: str, message: str) -> dict:
    return {"data": None, "error": {"code": code, "message": message}}


# ── Decision log endpoints ─────────────────────────────────────────────────────

@audit_router.get(
    "/decisions",
    summary="List AI decisions (paginated, filterable)",
)
async def list_decisions(
    date_from: Optional[datetime] = Query(default=None),
    date_to: Optional[datetime] = Query(default=None),
    agent_role: Optional[str] = Query(default=None),
    model: Optional[str] = Query(default=None),
    confidence_min: Optional[float] = Query(default=None, ge=0.0, le=1.0),
    confidence_max: Optional[float] = Query(default=None, ge=0.0, le=1.0),
    action_signal: Optional[str] = Query(default=None),
    company_ticker: Optional[str] = Query(default=None),
    cursor: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_admin_user),
    service: AuditService = Depends(_get_audit_service),
) -> dict:
    filters = DecisionLogFilter(
        date_from=date_from,
        date_to=date_to,
        agent_role=agent_role,
        model=model,
        confidence_min=confidence_min,
        confidence_max=confidence_max,
        action_signal=action_signal,
        company_ticker=company_ticker,
        cursor=cursor,
        limit=limit,
    )
    rows, next_cursor = await service.list_decisions(filters)
    return {
        "data": [r.model_dump() for r in rows],
        "next_cursor": next_cursor,
        "error": None,
    }


@audit_router.get(
    "/decisions/{decision_id}",
    summary="Get full AI decision detail",
)
async def get_decision_detail(
    decision_id: uuid.UUID,
    current_user: User = Depends(get_current_admin_user),
    service: AuditService = Depends(_get_audit_service),
) -> dict:
    try:
        detail = await service.get_decision_detail(decision_id)
    except NotFoundError:
        raise HTTPException(status_code=404, detail=_err("NOT_FOUND", f"Decision {decision_id} not found"))
    return _ok(detail.model_dump())


@audit_router.post(
    "/decisions/{decision_id}/override",
    status_code=status.HTTP_201_CREATED,
    summary="Apply admin override to an AI decision",
)
async def apply_override(
    decision_id: uuid.UUID,
    body: AdminOverrideRequest,
    current_user: User = Depends(get_current_admin_user),
    service: AuditService = Depends(_get_audit_service),
) -> dict:
    # Ensure URL decision_id matches body
    body = body.model_copy(update={"decision_id": decision_id})
    try:
        result = await service.apply_override(body, current_user.user_id, current_user.tenant_id)
    except NotFoundError:
        raise HTTPException(
            status_code=404, detail=_err("NOT_FOUND", f"Decision {decision_id} not found")
        )
    return _ok(result.model_dump())


# ── Prompt version history endpoints ──────────────────────────────────────────

@audit_router.get(
    "/prompts/{agent_role}/history",
    summary="List prompt version history for an agent role",
)
async def list_prompt_history(
    agent_role: str,
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_admin_user),
    service: AuditService = Depends(_get_audit_service),
) -> dict:
    entries = await service.list_prompt_history(agent_role, limit=limit)
    return _ok([e.model_dump() for e in entries])


@audit_router.post(
    "/prompts/{agent_role}/rollback",
    summary="Roll back an agent's prompt to a previous version",
)
async def rollback_prompt(
    agent_role: str,
    body: RollbackRequest,
    current_user: User = Depends(get_current_admin_user),
    service: AuditService = Depends(_get_audit_service),
) -> dict:
    body = body.model_copy(update={"agent_role": agent_role})
    try:
        result = await service.rollback_prompt(body)
    except RollbackError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=_err("ROLLBACK_FAILED", str(exc)),
        )
    return _ok(result.model_dump())


# ── Calibration dashboard endpoints ───────────────────────────────────────────

@audit_router.get(
    "/calibration",
    summary="Get calibration time-series data",
)
async def get_calibration(
    days: int = Query(default=30, description="Lookback window in days (30, 60, or 90)"),
    action_signal: Optional[str] = Query(default=None),
    current_user: User = Depends(get_current_admin_user),
    service: AuditService = Depends(_get_audit_service),
) -> dict:
    if days not in (30, 60, 90):
        raise HTTPException(
            status_code=400,
            detail=_err("INVALID_PARAM", "days must be 30, 60, or 90"),
        )
    results = await service.get_calibration_time_series(days=days, action_signal=action_signal)
    return _ok(results)


@audit_router.get(
    "/calibration/summary",
    summary="Get calibration summary with below_threshold indicator",
)
async def get_calibration_summary(
    days: int = Query(default=30),
    current_user: User = Depends(get_current_admin_user),
    service: AuditService = Depends(_get_audit_service),
) -> dict:
    summary = await service.get_calibration_summary(days=days)
    if hasattr(summary, "model_dump"):
        return _ok(summary.model_dump())
    return _ok(summary)


# ── Workflow history endpoints ─────────────────────────────────────────────────

@audit_router.get(
    "/workflows",
    summary="List workflow run history (paginated)",
)
async def list_workflows(
    cursor: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_admin_user),
    service: AuditService = Depends(_get_audit_service),
) -> dict:
    runs, next_cursor = await service.list_workflow_runs(cursor=cursor, limit=limit)
    return {
        "data": [r.model_dump() for r in runs],
        "next_cursor": next_cursor,
        "error": None,
    }


@audit_router.get(
    "/workflows/{workflow_id}",
    summary="Get full workflow run detail",
)
async def get_workflow_detail(
    workflow_id: uuid.UUID,
    current_user: User = Depends(get_current_admin_user),
    service: AuditService = Depends(_get_audit_service),
) -> dict:
    try:
        detail = await service.get_workflow_detail(workflow_id)
    except NotFoundError:
        raise HTTPException(
            status_code=404,
            detail=_err("NOT_FOUND", f"Workflow {workflow_id} not found"),
        )
    return _ok(detail.model_dump())


@audit_router.post(
    "/workflows/{workflow_id}/rerun",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Re-run a workflow with current production prompts",
)
async def rerun_workflow(
    workflow_id: uuid.UUID,
    current_user: User = Depends(get_current_admin_user),
    service: AuditService = Depends(_get_audit_service),
) -> dict:
    try:
        result = await service.rerun_workflow(
            RerunRequest(workflow_id=workflow_id), current_user.user_id
        )
    except NotFoundError:
        raise HTTPException(
            status_code=404,
            detail=_err("NOT_FOUND", f"Workflow {workflow_id} not found"),
        )
    return _ok(result.model_dump())
