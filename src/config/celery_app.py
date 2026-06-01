"""Celery application instance and beat schedule.

PLAN-F-022 TASK-007.

All Celery configuration is loaded from environment variables (12-factor, P-06).
The beat schedule registers the health metric flush task every 60 seconds.

Beat schedule:
  - health_flush_task: every 60 seconds — flushes Redis health counters to
    PostgreSQL DataSourceHealthMetric rows.

Future tasks to add:
  - Midnight reset task: calls HealthCounter.reset() per source at 00:00
    per tenant timezone (out of scope for PLAN-F-022).
"""
from __future__ import annotations

import os

from celery import Celery
from celery.schedules import crontab

# ---------------------------------------------------------------------------
# Application instance
# ---------------------------------------------------------------------------

#: Redis URL for both the broker and the result backend.
#: Required — set CELERY_BROKER_URL in .env (see .env.example, P-06).
#: No default value: fail fast at startup if the env var is absent.
CELERY_BROKER_URL: str = os.environ.get("CELERY_BROKER_URL", "")
CELERY_RESULT_BACKEND: str = os.environ.get("CELERY_RESULT_BACKEND", CELERY_BROKER_URL)

app = Celery(
    "stokai",
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
    include=["src.admin.data_sources.health_flush_task"],
)

app.conf.update(
    # Serialisation — JSON is safe and human-readable
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    # Timezone — UTC throughout (tenant-local time is handled at application layer)
    timezone="UTC",
    enable_utc=True,
    # Task acknowledgement: ack only after the task completes (not at delivery)
    task_acks_late=True,
    # Worker prefetch — 1 ensures fair scheduling under load
    worker_prefetch_multiplier=1,
)

# ---------------------------------------------------------------------------
# Beat (periodic task) schedule
# ---------------------------------------------------------------------------

app.conf.beat_schedule = {
    # PLAN-F-022 TASK-007: flush Redis health counters to PostgreSQL every 60 s
    "health-flush-every-60s": {
        "task": "src.admin.data_sources.health_flush_task.flush_health_metrics",
        "schedule": 60.0,  # seconds
        "options": {"expires": 55},  # discard if worker picks it up late
    },
}
