"""
BudgetEnforcer — stateless budget gate service.

Checks whether a user's daily spend has reached or exceeded the configured
hard-stop percentage.  Returns SUPPRESSED_BUDGET when the gate fires.
Raises BudgetHardStopError instead of returning a status so the pipeline
is forced to handle it explicitly (never silently swallowed).

Guard: zero daily_budget_usd raises BudgetHardStopError immediately to
prevent divide-by-zero and to signal misconfiguration.
"""
from __future__ import annotations

from src.alerts.exceptions import BudgetHardStopError
from src.alerts.models import AlertStatus, BudgetState


class BudgetEnforcer:
    """Stateless service that applies the cost-governance budget gate.

    No constructor dependencies — all state is passed to *check()* at call
    time for ease of testing and side-effect-free composition.
    """

    def check(self, budget_state: BudgetState) -> AlertStatus | None:
        """Evaluate whether the user's daily budget hard-stop has been reached.

        Args:
            budget_state: Current budget configuration and today's spend.

        Returns:
            None if the user is within budget and the alert may proceed.
            SUPPRESSED_BUDGET if the hard-stop threshold has been reached.

        Raises:
            BudgetHardStopError: When daily_budget_usd is zero (misconfiguration)
                or when the hard-stop threshold is reached (so callers are forced
                to record a silent-log row explicitly).
        """
        if budget_state.daily_budget_usd == 0:
            raise BudgetHardStopError(
                "daily_budget_usd is zero — budget gate misconfigured",
                spent_today_usd=budget_state.spent_today_usd,
                daily_budget_usd=0.0,
            )

        spend_pct = (budget_state.spent_today_usd / budget_state.daily_budget_usd) * 100.0

        if spend_pct >= budget_state.hard_stop_pct:
            raise BudgetHardStopError(
                f"Daily budget hard stop reached: {spend_pct:.1f}% >= {budget_state.hard_stop_pct}%",
                spent_today_usd=budget_state.spent_today_usd,
                daily_budget_usd=budget_state.daily_budget_usd,
            )

        return None
