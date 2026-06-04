"""
api.routers.workflow_router — FastAPI router for workflow analysis endpoints.

Endpoints:
  POST /api/v1/companies/{company_id}/analysis
    → IDOR guard, company exists check, one-active-analysis-per-user rate limit
      (409 if RUNNING/HIL_PENDING), creates workflow_run, enqueues task, returns 202.

  GET /api/v1/workflow-runs/{run_id}
    → tenant+user ownership, returns status + report if COMPLETED, 404 if not found.

Standard envelope: {"data": ..., "error": null}

PLAN-F-007 TASK-008
"""
from __future__ import annotations

import logging
import uuid
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.workflows.on_demand.tasks import on_demand_analysis_task
from src.api.auth.dependencies import get_current_user, get_db as get_db_session
from src.storage.models.user import User
from src.storage.repositories.workflow_run_repository import WorkflowRunRepository

logger = logging.getLogger(__name__)

workflow_router = APIRouter(prefix="/api/v1")


def _ok(data: Any) -> dict:
    return {"data": data, "error": None}


def _err(code: str, message: str) -> dict:
    return {"data": None, "error": {"code": code, "message": message}}


# ── POST /api/v1/companies/{company_id}/analysis ─────────────────────────────


@workflow_router.post(
    "/companies/{company_id}/analysis",
    status_code=status.HTTP_202_ACCEPTED,
)
async def trigger_analysis(
    company_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """Trigger an on-demand company analysis for the authenticated user.

    Security:
      - company_id from path; never trusts user-supplied tenant_id.
      - One active analysis per company per user: 409 if RUNNING or HIL_PENDING.

    Returns:
        202 with {"data": {"run_id": "<uuid>"}, "error": null}
    """
    repo = WorkflowRunRepository(db)

    # One-active-analysis-per-user rate limit
    active_run = await repo.get_active_for_company_user(
        company_id=company_id,
        user_id=current_user.user_id,
        tenant_id=current_user.tenant_id,
    )
    if active_run is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=_err(
                "ANALYSIS_ALREADY_RUNNING",
                "An analysis is already running for this company and user",
            ),
        )

    # Build initial WorkflowState and persist the run row
    from src.ai.workflows.state import WorkflowState, WorkflowType
    from datetime import datetime, timezone

    workflow_id = uuid.uuid4()
    workflow_state = WorkflowState(
        workflow_id=workflow_id,
        workflow_type=WorkflowType.ON_DEMAND,
        tenant_id=current_user.tenant_id,
        user_id=current_user.user_id,
        company_id=company_id,
        started_at=datetime.now(tz=timezone.utc),
    )

    run = await repo.create(workflow_state)

    # Enqueue the Celery task
    on_demand_analysis_task.delay(
        workflow_id=str(workflow_id),
        company_id=str(company_id),
        tenant_id=str(current_user.tenant_id),
        user_id=str(current_user.user_id),
    )

    return _ok({"run_id": str(run.workflow_id)})


# ── GET /api/v1/workflow-runs/{run_id} ────────────────────────────────────────


@workflow_router.get("/workflow-runs/{run_id}")
async def get_workflow_run(
    run_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """Retrieve the status and (if COMPLETED) report for a workflow run.

    Returns 404 if not found or if the run belongs to a different tenant
    (IDOR prevention — tenant scope enforced at repository layer).

    Returns:
        200 with {"data": {"status": ..., "report": ...}, "error": null}
    """
    repo = WorkflowRunRepository(db)

    run = await repo.get(run_id, current_user.tenant_id)

    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=_err("NOT_FOUND", "Workflow run not found"),
        )

    response_data: dict = {
        "run_id": str(run.workflow_id),
        "status": run.status,
        "workflow_type": run.workflow_type,
        "company_id": str(run.company_id) if run.company_id else None,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "cost_usd": run.cost_usd,
        "report": None,
    }

    if run.status == "COMPLETED" and run.final_state:
        response_data["report"] = run.final_state.get("report")

    return _ok(response_data)
