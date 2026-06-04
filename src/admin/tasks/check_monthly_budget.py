"""
admin.tasks.check_monthly_budget — Daily Celery beat task for budget threshold alerts.

Runs daily at 09:00 UTC (configured in src/config/celery_app.py).

Behaviour:
  1. Fetches the current-month MonthlyBudgetSummary from MonthlyBudgetMonitor.
  2. If summary.over_budget:
       - Logs ERROR with structured fields.
       - Sends admin alert email (subject: hard-limit notice).
  3. If summary.over_alert_threshold and not summary.over_budget:
       - Logs WARNING with structured fields.
       - Sends admin alert email (subject: 80% warning).
  4. If neither threshold crossed: logs INFO with combined_total_usd.

Email deduplication:
  - Redis key ``budget_alert_sent:{YYYY-MM}`` with 25-hour TTL.
  - If key exists the email is skipped, but structured log is always written.

Idempotent: running multiple times on the same day produces at most one alert
email per month-key (per alert level per day guarded by TTL).

No automatic system shutdown is triggered.

Introduced by PLAN-N-005 TASK-006.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, date, datetime

import redis as redis_lib

from src.config.celery_app import celery_app
from src.config.settings import get_settings

logger = logging.getLogger(__name__)

# Redis TTL: 25 hours — ensures at most one email per calendar day even if
# the task is retried within the same hour.
_DEDUP_TTL_SECONDS: int = 25 * 3600


def _first_day_of_current_month() -> date:
    today = date.today()
    return date(today.year, today.month, 1)


def _dedup_key(billing_month: date, level: str) -> str:
    """Return the Redis deduplication key for a given month and alert level."""
    return f"budget_alert_sent:{billing_month.strftime('%Y-%m')}:{level}"


def _build_email_body(summary) -> str:
    """Format a plain-text email body from a MonthlyBudgetSummary."""
    lines: list[str] = [
        f"StokAI Monthly Budget Report — {summary.billing_month.strftime('%B %Y')}",
        "=" * 60,
        "",
        f"Combined total:  ${summary.combined_total_usd:.2f} / ${summary.budget_usd:.2f}  "
        f"({summary.pct_of_budget:.1f}%)",
        "",
        "AI costs by model:",
    ]
    if summary.ai_costs:
        for line in summary.ai_costs:
            lines.append(
                f"  {line.model_id:<40} ${line.cost_usd:.4f}  ({line.call_count} calls)"
            )
    else:
        lines.append("  (no AI cost records this month)")

    lines += [
        f"  {'AI TOTAL':<40} ${summary.ai_total_usd:.4f}",
        "",
        "Infrastructure costs:",
    ]
    if summary.infra_costs:
        for line in summary.infra_costs:
            lines.append(
                f"  [{line.category:<14}] {line.description:<28} ${line.cost_usd:.4f}"
            )
    else:
        lines.append("  (no infrastructure cost records this month)")

    lines += [
        f"  {'INFRA TOTAL':<40} ${summary.infra_total_usd:.4f}",
        "",
        "Note: Infrastructure costs must be entered manually by the 5th of each month.",
        "      Missing entries will cause the combined total to understate real spend.",
    ]

    return "\n".join(lines)


def _send_alert_email(subject: str, body: str) -> None:
    """Deliver the alert email via SendGrid.

    Raises nothing — on failure, logs ERROR so the structured log is always
    the authoritative record. Email delivery is best-effort.
    """
    settings = get_settings()

    if not settings.SENDGRID_API_KEY:
        logger.warning(
            "budget_alert.email_skipped: SENDGRID_API_KEY not configured; "
            "email not sent. subject=%r",
            subject,
        )
        return

    if not settings.ADMIN_ALERT_EMAIL:
        logger.warning(
            "budget_alert.email_skipped: ADMIN_ALERT_EMAIL not configured; "
            "email not sent. subject=%r",
            subject,
        )
        return

    try:
        from sendgrid import SendGridAPIClient
        from sendgrid.helpers.mail import Mail

        message = Mail(
            from_email=settings.SENDGRID_FROM_EMAIL or settings.ADMIN_ALERT_EMAIL,
            to_emails=settings.ADMIN_ALERT_EMAIL,
            subject=subject,
            plain_text_content=body,
        )
        client = SendGridAPIClient(api_key=settings.SENDGRID_API_KEY)
        response = client.send(message)
        status_code: int = response.status_code
        if status_code >= 400:
            logger.error(
                "budget_alert.email_failed: SendGrid returned HTTP %d subject=%r",
                status_code,
                subject,
            )
        else:
            logger.info(
                "budget_alert.email_sent: status=%d subject=%r",
                status_code,
                subject,
            )
    except Exception as exc:
        # Never suppress the structured log; email failure is non-fatal.
        logger.error(
            "budget_alert.email_exception: %s: %s subject=%r",
            type(exc).__name__,
            exc,
            subject,
        )


def _check_and_send_deduped(
    redis_client: redis_lib.Redis,
    dedup_key: str,
    subject: str,
    body: str,
) -> bool:
    """Send alert email once per TTL window using a Redis dedup key.

    Returns True if email was (attempted to be) sent, False if deduplication
    guard was active.
    """
    if redis_client.exists(dedup_key):
        return False  # already sent in the current window

    _send_alert_email(subject, body)
    redis_client.set(dedup_key, "1", ex=_DEDUP_TTL_SECONDS)
    return True


async def _run_budget_check() -> None:
    """Async body of check_monthly_budget_task."""
    from src.admin.budget_monitor import MonthlyBudgetMonitor
    from src.storage.repositories.cost_record_repo import PostgresCostRecordRepository
    from src.storage.repositories.infrastructure_cost_repo import (
        PostgresInfrastructureCostRepository,
    )

    # We need a DB session — get one via the async engine directly.
    from src.api.dependencies import get_db as get_db_gen

    settings = get_settings()
    redis_client = redis_lib.from_url(settings.REDIS_URL, decode_responses=True)

    billing_month = _first_day_of_current_month()

    try:
        async for db in get_db_gen():
            cost_record_repo = PostgresCostRecordRepository(db)
            infra_cost_repo = PostgresInfrastructureCostRepository(db)
            monitor = MonthlyBudgetMonitor(
                cost_record_repo=cost_record_repo,
                infra_cost_repo=infra_cost_repo,
            )
            summary = await monitor.summarise(
                billing_month=billing_month,
                tenant_id=None,
            )
            break  # consumed one yielded session

    except Exception as exc:
        logger.error(
            "budget_check.db_error: failed to fetch monthly summary: %s: %s",
            type(exc).__name__,
            exc,
        )
        raise  # let Celery retry

    finally:
        redis_client.close()

    body = _build_email_body(summary)

    if summary.over_budget:
        logger.error(
            "budget_check.hard_limit: combined_total_usd=%.2f budget_usd=%.2f "
            "pct_of_budget=%.1f billing_month=%s",
            summary.combined_total_usd,
            summary.budget_usd,
            summary.pct_of_budget,
            billing_month.isoformat(),
        )
        dedup_key = _dedup_key(billing_month, "hard_limit")
        subject = (
            "StokAI budget HARD LIMIT: $100/month reached — immediate review required"
        )
        sent = _check_and_send_deduped(redis_client, dedup_key, subject, body)
        if not sent:
            logger.info(
                "budget_check.dedup_active: hard_limit email already sent this window "
                "billing_month=%s",
                billing_month.isoformat(),
            )

    elif summary.over_alert_threshold:
        logger.warning(
            "budget_check.alert_threshold: combined_total_usd=%.2f budget_usd=%.2f "
            "pct_of_budget=%.1f billing_month=%s",
            summary.combined_total_usd,
            summary.budget_usd,
            summary.pct_of_budget,
            billing_month.isoformat(),
        )
        dedup_key = _dedup_key(billing_month, "warning")
        subject = (
            f"StokAI budget alert: 80% of $100/month used "
            f"(${summary.combined_total_usd:.2f} spent)"
        )
        sent = _check_and_send_deduped(redis_client, dedup_key, subject, body)
        if not sent:
            logger.info(
                "budget_check.dedup_active: warning email already sent this window "
                "billing_month=%s",
                billing_month.isoformat(),
            )

    else:
        logger.info(
            "budget_check.ok: combined_total_usd=%.2f budget_usd=%.2f "
            "pct_of_budget=%.1f billing_month=%s",
            summary.combined_total_usd,
            summary.budget_usd,
            summary.pct_of_budget,
            billing_month.isoformat(),
        )


@celery_app.task(
    name="admin.check_monthly_budget",
    bind=True,
    max_retries=3,
    default_retry_delay=60,  # 60 s base; Celery applies exponential backoff via autoretry
)
def check_monthly_budget_task(self) -> None:
    """Daily Celery beat task (09:00 UTC) — check monthly budget thresholds.

    Fetches the current-month MonthlyBudgetSummary, logs the result, and
    sends a deduplication-guarded alert email when spend crosses $80 (WARNING)
    or $100 (ERROR).

    No automatic system shutdown is triggered.
    """
    try:
        asyncio.run(_run_budget_check())
    except Exception as exc:
        logger.error(
            "check_monthly_budget_task.error: %s: %s — retrying",
            type(exc).__name__,
            exc,
        )
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
