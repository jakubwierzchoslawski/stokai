"""
ai.budget_guard — BudgetGuard enforces the $100/month AI spend cap.

Rules:
  - Threshold stored in user.settings JSONB key "budget_threshold_usd" (default 100.0).
  - >= 100% → raise BudgetHardStopError + write audit WARNING.
  - >= 80%  → write audit WARNING, does not raise.
  - < 80%   → silent pass.

PLAN-F-030 TASK-005
"""
from __future__ import annotations

import dataclasses
import logging
import uuid
from datetime import date, datetime, timezone

logger = logging.getLogger(__name__)

DEFAULT_BUDGET_USD = 100.0
_WARNING_PCT = 80.0
_HARD_STOP_PCT = 100.0


class BudgetHardStopError(RuntimeError):
    """Raised when monthly spend reaches or exceeds the budget threshold."""


@dataclasses.dataclass
class BudgetStatus:
    """Budget status snapshot for a tenant."""

    spend_usd: float
    threshold_usd: float
    pct_used: float
    warning_active: bool
    hard_stop_active: bool


class BudgetGuard:
    """Enforces per-tenant monthly AI spend caps.

    Args:
        cost_repo: ICostRecordRepository — used to read aggregate monthly spend.
        user_repo: UserRepository — used to read/write the budget_threshold_usd
                   setting from user.settings JSONB.
        audit_logger: Optional callable(level, msg) used to write audit events.
                      Defaults to the module logger.
    """

    def __init__(
        self,
        cost_repo,
        user_repo=None,
        audit_logger=None,
    ) -> None:
        self._cost_repo = cost_repo
        self._user_repo = user_repo
        self._audit_logger = audit_logger or self._default_audit

    @staticmethod
    def _default_audit(level: str, msg: str) -> None:
        if level == "WARNING":
            logger.warning("AUDIT: %s", msg)
        else:
            logger.critical("AUDIT: %s", msg)

    async def _get_threshold(self, tenant_id: uuid.UUID) -> float:
        """Read threshold from admin user settings JSONB, defaulting to 100.0."""
        if self._user_repo is None:
            return DEFAULT_BUDGET_USD
        try:
            # Fetch any admin user for this tenant — threshold is tenant-wide
            admin_user = await self._user_repo.get_admin_for_tenant(tenant_id)
            if admin_user is None:
                return DEFAULT_BUDGET_USD
            settings = admin_user.settings or {}
            return float(settings.get("budget_threshold_usd", DEFAULT_BUDGET_USD))
        except Exception:
            return DEFAULT_BUDGET_USD

    async def _get_spend(self, tenant_id: uuid.UUID) -> float:
        """Return current month spend for the tenant."""
        now = datetime.now(timezone.utc)
        return await self._cost_repo.aggregate_monthly(tenant_id, now.year, now.month)

    async def get_budget_status(self, tenant_id: uuid.UUID) -> BudgetStatus:
        """Return a BudgetStatus snapshot for the tenant."""
        spend = await self._get_spend(tenant_id)
        threshold = await self._get_threshold(tenant_id)
        pct = (spend / threshold * 100.0) if threshold > 0 else 0.0
        return BudgetStatus(
            spend_usd=spend,
            threshold_usd=threshold,
            pct_used=pct,
            warning_active=pct >= _WARNING_PCT,
            hard_stop_active=pct >= _HARD_STOP_PCT,
        )

    async def assert_under_limit(self, tenant_id: uuid.UUID) -> None:
        """Check spend and enforce the budget cap.

        Raises:
            BudgetHardStopError: if spend >= threshold.
        """
        status = await self.get_budget_status(tenant_id)

        if status.hard_stop_active:
            self._audit_logger(
                "CRITICAL",
                f"Budget HARD STOP: tenant={tenant_id} "
                f"spend={status.spend_usd:.2f} threshold={status.threshold_usd:.2f} "
                f"({status.pct_used:.1f}%)",
            )
            raise BudgetHardStopError(
                f"Monthly budget exceeded: {status.spend_usd:.2f} USD >= "
                f"{status.threshold_usd:.2f} USD ({status.pct_used:.1f}%)"
            )

        if status.warning_active:
            self._audit_logger(
                "WARNING",
                f"Budget WARNING: tenant={tenant_id} "
                f"spend={status.spend_usd:.2f} threshold={status.threshold_usd:.2f} "
                f"({status.pct_used:.1f}%)",
            )

    async def set_threshold(
        self, tenant_id: uuid.UUID, threshold_usd: float
    ) -> None:
        """Persist a new budget threshold in the admin user's settings JSONB.

        Raises:
            ValueError: if threshold_usd <= 0.
            RuntimeError: if no user_repo is configured.
        """
        if threshold_usd <= 0:
            raise ValueError("threshold_usd must be positive")
        if self._user_repo is None:
            raise RuntimeError("BudgetGuard: no user_repo configured for set_threshold")

        admin_user = await self._user_repo.get_admin_for_tenant(tenant_id)
        if admin_user is None:
            raise ValueError(f"No admin user found for tenant {tenant_id}")

        settings = dict(admin_user.settings or {})
        settings["budget_threshold_usd"] = threshold_usd
        await self._user_repo.update_settings(admin_user.user_id, settings)
