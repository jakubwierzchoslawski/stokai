"""Alerts module — rule evaluation, dispatch, and anti-fatigue logic.

Public surface:
- AlertRuleEvaluator / IAlertRuleEvaluator — evaluate pipeline events against user rules
- AlertDispatcher / IAlertDispatcher — dispatch passing alerts or log silent events
- Factory functions for dependency-injection wiring
"""
from __future__ import annotations

from src.alerts.models import (
    ActionSignal,
    AlertRow,
    AlertRuleRow,
    AlertStatus,
    AlertTextResult,
    AntiFatigueState,
    BudgetState,
    DispatchDecision,
)
from src.alerts.exceptions import AlertDispatchError, BudgetHardStopError, SendGridError
from src.alerts.interfaces.i_alert_rule_evaluator import IAlertRuleEvaluator
from src.alerts.interfaces.i_alert_dispatcher import IAlertDispatcher
from src.alerts.services.alert_rule_evaluator import AlertRuleEvaluator
from src.alerts.services.alert_dispatcher import AlertDispatcher

__all__ = [
    # models
    "ActionSignal",
    "AlertRow",
    "AlertRuleRow",
    "AlertStatus",
    "AlertTextResult",
    "AntiFatigueState",
    "BudgetState",
    "DispatchDecision",
    # exceptions
    "AlertDispatchError",
    "BudgetHardStopError",
    "SendGridError",
    # interfaces
    "IAlertRuleEvaluator",
    "IAlertDispatcher",
    # concrete implementations
    "AlertRuleEvaluator",
    "AlertDispatcher",
    # factories
    "create_alert_rule_evaluator",
    "create_alert_dispatcher",
]


def create_alert_rule_evaluator(session) -> IAlertRuleEvaluator:
    """Factory: build a fully-wired AlertRuleEvaluator for injection.

    Args:
        session: SQLAlchemy 2.0 async session.

    Returns:
        AlertRuleEvaluator satisfying IAlertRuleEvaluator.
    """
    from src.alerts.repositories.alert_rule_repository import AlertRuleRepository

    repo = AlertRuleRepository(session)
    return AlertRuleEvaluator(rule_repo=repo)


def create_alert_dispatcher(session, llm_client, tracer) -> IAlertDispatcher:
    """Factory: build a fully-wired AlertDispatcher for injection.

    Args:
        session: SQLAlchemy 2.0 async session.
        llm_client: ILLMClient for alert text generation (Sonnet 4.6).
        tracer: ILangfuseTracer for observability span recording.

    Returns:
        AlertDispatcher satisfying IAlertDispatcher.
    """
    from src.alerts.repositories.alert_repository import AlertRepository
    from src.alerts.services.anti_fatigue_checker import AntiFatigueChecker
    from src.alerts.services.budget_enforcer import BudgetEnforcer
    from src.alerts.integrations.sendgrid_email_sender import SendGridEmailSender
    from src.config.settings import get_settings

    settings = get_settings()
    alert_repo = AlertRepository(session)
    anti_fatigue_checker = AntiFatigueChecker()
    budget_enforcer = BudgetEnforcer()
    email_sender = SendGridEmailSender(
        api_key=settings.SENDGRID_API_KEY,
        from_email=settings.SENDGRID_FROM_EMAIL,
    )

    return AlertDispatcher(
        fatigue_repo=alert_repo,
        anti_fatigue_checker=anti_fatigue_checker,
        budget_enforcer=budget_enforcer,
        email_sender=email_sender,
        alert_repo=alert_repo,
    )
