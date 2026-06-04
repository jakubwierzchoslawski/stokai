"""
src.ai.cost.errors — Cost governance exception and event types (PLAN-N-004).

Three error types:
  - WorkflowBudgetExceededError: raised by WorkflowCostGuard at per-workflow ceiling.
  - UserDailyBudgetExceededError: raised by UserBudgetEnforcer at daily hard stop.
  - BudgetAlertEvent: structured log payload at daily_alert_threshold_pct.
"""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


class WorkflowBudgetExceededError(Exception):
    """Raised by WorkflowCostGuard when accumulated cost reaches the workflow ceiling.

    Attributes:
        workflow_type: Workflow type identifier string.
        ceiling_usd: The configured ceiling in USD.
        accumulated_usd: The accumulated cost that triggered the breach.
        workflow_id: UUID of the running workflow run.
    """

    def __init__(
        self,
        workflow_type: str,
        ceiling_usd: float,
        accumulated_usd: float,
        workflow_id: UUID,
    ) -> None:
        self.workflow_type = workflow_type
        self.ceiling_usd = ceiling_usd
        self.accumulated_usd = accumulated_usd
        self.workflow_id = workflow_id
        super().__init__(
            f"Workflow {workflow_type!r} (id={workflow_id}) exceeded cost ceiling "
            f"${ceiling_usd:.4f}: accumulated=${accumulated_usd:.4f}"
        )


class UserDailyBudgetExceededError(Exception):
    """Raised by UserBudgetEnforcer when user has hit daily_hard_stop_pct.

    Attributes:
        user_id: UUID of the user.
        daily_budget_usd: The configured daily budget in USD.
        spent_today_usd: Total cost accumulated today for this user.
    """

    def __init__(
        self,
        user_id: UUID,
        daily_budget_usd: float,
        spent_today_usd: float,
    ) -> None:
        self.user_id = user_id
        self.daily_budget_usd = daily_budget_usd
        self.spent_today_usd = spent_today_usd
        super().__init__(
            f"User {user_id} daily budget hard stop: "
            f"spent=${spent_today_usd:.4f} >= budget=${daily_budget_usd:.4f}"
        )


@dataclass
class BudgetAlertEvent:
    """Structured log payload for budget alert at daily_alert_threshold_pct.

    Emitted as a WARNING-level structured log when a user's daily spend
    crosses daily_alert_threshold_pct.  The admin cost monitor consumes
    this via log aggregation.  No email is sent from this path.
    """

    user_id: UUID
    tenant_id: UUID
    spent_today_usd: float
    daily_budget_usd: float
    pct_used: float
    alert_threshold_pct: float
    workflow_type: str
