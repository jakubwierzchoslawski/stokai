"""
src.ai.cost.user_budget_enforcer — UserBudgetEnforcer: per-user daily budget enforcement (PLAN-N-004).

Called at Celery task dispatch time (ARCHITECTURE §12.6) before any Mode B
workflow is invoked.

Three outcomes:
  1. Under alert threshold   → returns None (dispatch allowed).
  2. At/above alert threshold but below hard stop → logs BudgetAlertEvent WARNING;
     returns None (dispatch continues).
  3. At/above hard stop      → raises UserDailyBudgetExceededError.

Budget config is read from user.settings JSONB:
  - daily_budget_usd          (float, default BudgetDefaults.DAILY_BUDGET_USD)
  - daily_alert_threshold_pct (float, default 80.0)
  - daily_hard_stop_pct       (float, default 100.0)

If daily_budget_usd is absent or 0.0, the enforcer logs a WARNING about
unconfigured budget and allows dispatch.
"""
from __future__ import annotations

import logging
from datetime import date
from uuid import UUID

from src.ai.cost.cost_config import BudgetDefaults
from src.ai.cost.errors import BudgetAlertEvent, UserDailyBudgetExceededError

logger = logging.getLogger(__name__)


class UserBudgetEnforcer:
    """Checks per-user daily AI cost budget before dispatching a Mode B workflow.

    Depends on ICostRecordRepository and IUserRepository via constructor injection
    (DIP — ARCHITECTURE §5).

    Args:
        cost_record_repo: Repository that provides daily_total_for_user().
        user_repo: Repository that provides getById() to load user.settings.
    """

    def __init__(
        self,
        cost_record_repo: object,
        user_repo: object,
    ) -> None:
        self._cost_repo = cost_record_repo
        self._user_repo = user_repo

    async def check_and_alert(
        self,
        user_id: UUID,
        tenant_id: UUID,
        workflow_type: str,
    ) -> None:
        """Check per-user daily budget before dispatching a workflow.

        Steps:
          1. Loads user row to read daily_budget_usd, threshold, hard_stop.
          2. Queries cost_record for today's total spend.
          3. If pct_used >= daily_hard_stop_pct: raises UserDailyBudgetExceededError.
          4. If pct_used >= daily_alert_threshold_pct: logs BudgetAlertEvent WARNING.
          5. Otherwise: returns None (dispatch allowed).

        Args:
            user_id: UUID of the user dispatching the workflow.
            tenant_id: UUID of the tenant (multi-tenancy scope).
            workflow_type: Workflow type string for structured log context.

        Raises:
            UserDailyBudgetExceededError: When daily spend >= hard stop threshold.
        """
        user = await self._user_repo.getById(user_id, tenant_id)
        settings: dict = {}
        if user is not None:
            settings = user.settings or {}

        daily_budget_usd: float = float(
            settings.get("daily_budget_usd", BudgetDefaults.DAILY_BUDGET_USD)
        )
        alert_threshold_pct: float = float(
            settings.get(
                "daily_alert_threshold_pct", BudgetDefaults.DAILY_ALERT_THRESHOLD_PCT
            )
        )
        hard_stop_pct: float = float(
            settings.get("daily_hard_stop_pct", BudgetDefaults.DAILY_HARD_STOP_PCT)
        )

        if daily_budget_usd == 0.0:
            logger.warning(
                "UserBudgetEnforcer: no daily_budget_usd configured for "
                "user_id=%s tenant_id=%s — allowing dispatch without budget check",
                user_id,
                tenant_id,
            )
            return

        today = date.today()
        spent_today_usd: float = await self._cost_repo.daily_total_for_user(
            user_id, tenant_id, today
        )

        pct_used = spent_today_usd / daily_budget_usd * 100.0

        if pct_used >= hard_stop_pct:
            raise UserDailyBudgetExceededError(
                user_id=user_id,
                daily_budget_usd=daily_budget_usd,
                spent_today_usd=spent_today_usd,
            )

        if pct_used >= alert_threshold_pct:
            alert = BudgetAlertEvent(
                user_id=user_id,
                tenant_id=tenant_id,
                spent_today_usd=spent_today_usd,
                daily_budget_usd=daily_budget_usd,
                pct_used=pct_used,
                alert_threshold_pct=alert_threshold_pct,
                workflow_type=workflow_type,
            )
            logger.warning(
                "UserBudgetEnforcer: BudgetAlertEvent user_id=%s tenant_id=%s "
                "spent_today_usd=%.4f daily_budget_usd=%.4f pct_used=%.2f "
                "alert_threshold_pct=%.1f workflow_type=%r",
                alert.user_id,
                alert.tenant_id,
                alert.spent_today_usd,
                alert.daily_budget_usd,
                alert.pct_used,
                alert.alert_threshold_pct,
                alert.workflow_type,
            )
