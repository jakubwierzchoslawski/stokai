"""
admin.budget_monitor — MonthlyBudgetMonitor service and MonthlyBudgetSummary schema.

Aggregates AI costs (from cost_record via ICostRecordRepository) and infrastructure
costs (from infrastructure_cost via IInfrastructureCostRepository) into a single
MonthlyBudgetSummary for the admin cost monitor endpoint and Celery beat task.

Introduced by PLAN-N-005 TASK-004.
"""
from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from pydantic import BaseModel

if TYPE_CHECKING:
    from src.storage.repositories.cost_record_repo import ICostRecordRepository
    from src.storage.repositories.infrastructure_cost_repo import (
        IInfrastructureCostRepository,
    )

# ── Budget constants ───────────────────────────────────────────────────────────

MONTHLY_BUDGET_USD: float = 100.0
ALERT_THRESHOLD_USD: float = 80.0  # 80% of MONTHLY_BUDGET_USD


# ── Pydantic sub-models ────────────────────────────────────────────────────────

class AiModelCostLine(BaseModel):
    """One row in the AI cost breakdown: a distinct model / workflow type."""

    model_id: str     # e.g. "claude-haiku-4-5", "claude-sonnet-4-6", "unknown"
    cost_usd: float
    call_count: int


class InfraCostLine(BaseModel):
    """One row in the infrastructure cost breakdown."""

    category: str     # InfraCostCategory.value
    description: str
    cost_usd: float


class MonthlyBudgetSummary(BaseModel):
    """Full monthly budget summary returned by the admin cost-monitor endpoint."""

    billing_month: date          # first day of the month, e.g. 2026-06-01
    ai_costs: list[AiModelCostLine]
    ai_total_usd: float
    infra_costs: list[InfraCostLine]
    infra_total_usd: float
    combined_total_usd: float
    budget_usd: float            # always MONTHLY_BUDGET_USD ($100.00)
    pct_of_budget: float         # 0.0 – 100.0+ (can exceed 100 if over budget)
    alert_threshold_usd: float   # always ALERT_THRESHOLD_USD ($80.00)
    over_alert_threshold: bool   # combined_total_usd >= ALERT_THRESHOLD_USD
    over_budget: bool            # combined_total_usd >= MONTHLY_BUDGET_USD


# ── Service ────────────────────────────────────────────────────────────────────

class MonthlyBudgetMonitor:
    """Aggregates AI + infrastructure costs into a single MonthlyBudgetSummary.

    Read-only service: no side effects, no external API calls.
    All intermediate arithmetic uses decimal.Decimal to avoid float drift.
    """

    def __init__(
        self,
        cost_record_repo: "ICostRecordRepository",
        infra_cost_repo: "IInfrastructureCostRepository",
    ) -> None:
        self._cost_record_repo = cost_record_repo
        self._infra_cost_repo = infra_cost_repo

    async def summarise(
        self,
        billing_month: date,
        tenant_id: UUID | None = None,
    ) -> MonthlyBudgetSummary:
        """Build and return a MonthlyBudgetSummary for billing_month.

        Args:
            billing_month: Must be the first day of a calendar month.
                           Raises ValueError otherwise.
            tenant_id: When None, the global (single-tenant MVP) view is used.

        Returns:
            MonthlyBudgetSummary with AI costs, infra costs, combined total,
            pct_of_budget, over_alert_threshold, and over_budget populated.

        Raises:
            ValueError: if billing_month.day != 1.
        """
        if billing_month.day != 1:
            raise ValueError(
                f"billing_month must be the first day of a month; "
                f"got {billing_month.isoformat()}"
            )

        # ── 1. AI costs ───────────────────────────────────────────────────────
        ai_by_model = await self._cost_record_repo.monthly_total_by_model(
            year=billing_month.year,
            month=billing_month.month,
            tenant_id=tenant_id,
        )

        ai_cost_lines: list[AiModelCostLine] = [
            AiModelCostLine(
                model_id=model_id,
                cost_usd=round(float(cost_usd), 6),
                call_count=call_count,
            )
            for model_id, (cost_usd, call_count) in ai_by_model.items()
        ]

        ai_total_dec = sum(
            Decimal(str(line.cost_usd)) for line in ai_cost_lines
        ) if ai_cost_lines else Decimal("0")

        # ── 2. Infrastructure costs ───────────────────────────────────────────
        infra_rows = await self._infra_cost_repo.monthly_by_category(
            billing_month=billing_month,
            tenant_id=tenant_id,
        )

        infra_cost_lines: list[InfraCostLine] = [
            InfraCostLine(
                category=category.value,
                description=description,
                cost_usd=round(float(cost_usd), 6),
            )
            for category, description, cost_usd in infra_rows
        ]

        infra_total_dec = sum(
            Decimal(str(line.cost_usd)) for line in infra_cost_lines
        ) if infra_cost_lines else Decimal("0")

        # ── 3. Combined totals ────────────────────────────────────────────────
        combined_dec = ai_total_dec + infra_total_dec
        budget_dec = Decimal(str(MONTHLY_BUDGET_USD))

        pct_raw = (combined_dec / budget_dec * Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        combined_total_usd = float(combined_dec)
        ai_total_usd = float(ai_total_dec)
        infra_total_usd = float(infra_total_dec)
        pct_of_budget = float(pct_raw)

        return MonthlyBudgetSummary(
            billing_month=billing_month,
            ai_costs=ai_cost_lines,
            ai_total_usd=ai_total_usd,
            infra_costs=infra_cost_lines,
            infra_total_usd=infra_total_usd,
            combined_total_usd=combined_total_usd,
            budget_usd=MONTHLY_BUDGET_USD,
            pct_of_budget=pct_of_budget,
            alert_threshold_usd=ALERT_THRESHOLD_USD,
            over_alert_threshold=combined_total_usd >= ALERT_THRESHOLD_USD,
            over_budget=combined_total_usd >= MONTHLY_BUDGET_USD,
        )
