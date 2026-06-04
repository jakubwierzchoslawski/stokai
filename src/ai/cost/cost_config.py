"""
src.ai.cost.cost_config — Typed cost ceiling constants and budget defaults (PLAN-N-004).

WorkflowCeilings provides in-code fallback values that match the canonical
per-workflow YAML files.  The YAML files are the authoritative source; these
constants exist only as a safety net when a YAML ceiling is not provided
(startup validation should prevent that scenario).

BudgetDefaults provides per-user daily budget configuration defaults used
by UserBudgetEnforcer when user.settings JSONB does not contain the keys.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WorkflowCeilings:
    """Hard cost ceilings per workflow type, in USD.

    Source of truth: workflow YAML files (agents/*.yaml).
    These constants are fallback defaults for when a YAML ceiling is absent.
    """

    WATCHLIST_SCAN: float = 1.00
    ON_DEMAND_ANALYSIS: float = 1.50
    MORNING_BRIEF: float = 2.00
    EARNINGS_RISK_BRIEF: float = 1.50
    EVENT_DEEP_DIVE: float = 2.00


@dataclass(frozen=True)
class BudgetDefaults:
    """Default per-user daily budget configuration values.

    All values are overridden by user.settings JSONB keys:
      - daily_budget_usd
      - daily_alert_threshold_pct
      - daily_hard_stop_pct
    """

    DAILY_BUDGET_USD: float = 10.00
    DAILY_ALERT_THRESHOLD_PCT: float = 80.0
    DAILY_HARD_STOP_PCT: float = 100.0
