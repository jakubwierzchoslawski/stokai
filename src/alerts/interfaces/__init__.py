"""Alerts interface protocols."""
from src.alerts.interfaces.i_alert_rule_evaluator import IAlertRuleEvaluator, RuleMatch
from src.alerts.interfaces.i_alert_dispatcher import IAlertDispatcher, AlertDispatchResult
from src.alerts.interfaces.i_alert_rule_repository import IAlertRuleRepository
from src.alerts.interfaces.i_alert_fatigue_repository import IAlertFatigueRepository
from src.alerts.interfaces.i_email_sender import IEmailSender

__all__ = [
    "IAlertRuleEvaluator",
    "RuleMatch",
    "IAlertDispatcher",
    "AlertDispatchResult",
    "IAlertRuleRepository",
    "IAlertFatigueRepository",
    "IEmailSender",
]
