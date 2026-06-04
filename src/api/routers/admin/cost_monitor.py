"""
api.routers.admin.cost_monitor — FastAPI router for the monthly budget monitor.

Endpoint:
  GET /api/v1/admin/cost-monitor
    Returns the current-month MonthlyBudgetSummary (AI + infrastructure costs).
    Requires admin role (JWT, role="admin").
    Response envelope: {"data": <MonthlyBudgetSummary>, "meta": null, "error": null}

Introduced by PLAN-N-005 TASK-005.
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.admin.budget_monitor import MonthlyBudgetMonitor, MonthlyBudgetSummary
from src.api.auth.dependencies import get_db, require_admin
from src.storage.models.user import User
from src.storage.repositories.cost_record_repo import PostgresCostRecordRepository
from src.storage.repositories.infrastructure_cost_repo import (
    PostgresInfrastructureCostRepository,
)

router = APIRouter(prefix="/admin/cost-monitor", tags=["admin"])


def _first_day_of_current_month() -> date:
    """Return the first day of the current calendar month."""
    today = date.today()
    return date(today.year, today.month, 1)


@router.get(
    "",
    summary="Monthly AI + infrastructure cost breakdown vs $100 budget",
    response_model=None,  # We return the envelope dict directly
)
async def get_cost_monitor(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return the current-month MonthlyBudgetSummary.

    - billing_month is always the first day of the current calendar month.
    - Requires admin role (JWT role="admin").
    - No query parameters for MVP (single-tenant; month is always current month).
    - Response envelope: {"data": <MonthlyBudgetSummary>, "meta": null, "error": null}
    """
    cost_record_repo = PostgresCostRecordRepository(db)
    infra_cost_repo = PostgresInfrastructureCostRepository(db)
    monitor = MonthlyBudgetMonitor(
        cost_record_repo=cost_record_repo,
        infra_cost_repo=infra_cost_repo,
    )

    billing_month = _first_day_of_current_month()
    summary: MonthlyBudgetSummary = await monitor.summarise(
        billing_month=billing_month,
        tenant_id=None,  # global view — single-tenant MVP
    )

    return {
        "data": summary.model_dump(),
        "meta": None,
        "error": None,
    }
