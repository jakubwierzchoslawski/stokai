"""
Celery application factory for StokAI.

Uses get_settings() singleton so all broker/backend URLs come from environment
variables — never hardcoded. Module-level celery_app is created at import time
so ``celery -A src.config.celery_app worker`` works without additional calls.
"""
from celery import Celery
from celery.schedules import crontab

from src.config.settings import get_settings


def create_celery_app() -> Celery:
    """Create and configure the Celery application from Settings."""
    settings = get_settings()
    app = Celery("stokai")
    app.conf.broker_url = settings.CELERY_BROKER_URL
    app.conf.result_backend = settings.CELERY_RESULT_BACKEND
    app.conf.task_serializer = "json"
    app.conf.result_serializer = "json"
    app.conf.accept_content = ["json"]
    app.conf.timezone = "UTC"
    app.conf.enable_utc = True

    # Auto-discover tasks in all src sub-packages
    app.autodiscover_tasks(
        [
            "src.admin.data_sources",
            "src.events",
            "src.scoring",
            "src.ai.memory.tasks",
            "src.alerts",   # Mode B event_deep_dive task (PLAN-F-005)
            "src.ai.hil",   # HIL timeout task (PLAN-F-013)
            "src.ai.workflows.on_demand",      # on_demand_analysis_task (PLAN-F-007)
            "src.ai.workflows.on_demand.hil",  # hil_fallback_check_task (PLAN-F-007)
            "src.ai.workflows.event_deep_dive",  # event_deep_dive task (PLAN-F-010)
            "src.ai.evaluation.tasks",  # Tier-3 calibration (PLAN-F-016)
            "src.ai.tasks",  # detect_t1_earnings + earnings_brief_task + morning_brief (PLAN-F-009, PLAN-F-006)
            "src.ai.workflows.earnings_brief.hil",  # earnings_hil_fallback_task (PLAN-F-009)
            "src.scoring.geo_modifier_worker",  # scoring.apply_geo_modifier (PLAN-F-018)
            "src.ai.prompts.tasks",  # publish_all_prompts_to_langfuse (PLAN-F-014)
        ]
    )

    # Beat schedule
    app.conf.beat_schedule = {
        # ── Existing ──────────────────────────────────────────────────────────
        "health-flush-every-60s": {
            "task": "src.admin.data_sources.health_flush_task.health_flush",
            "schedule": 60.0,  # seconds
        },
        # ── Memory hygiene (Layer 2 decay) — Monday 02:00 UTC ─────────────────
        "run-semantic-hygiene-weekly": {
            "task": "src.ai.memory.tasks.hygiene_tasks.run_semantic_hygiene",
            "schedule": crontab(hour=2, minute=0, day_of_week=1),
        },
        # ── Procedural pattern mining — Tuesday 03:00 UTC ──────────────────────
        "run-pattern-mining-weekly": {
            "task": "src.ai.memory.tasks.mining_tasks.run_pattern_mining",
            "schedule": crontab(hour=3, minute=0, day_of_week=2),
        },
        # ── Improvement loop — Wednesday 04:00 UTC ────────────────────────────
        "run-improvement-loop-weekly": {
            "task": "src.ai.memory.tasks.improvement_tasks.run_improvement_loop",
            "schedule": crontab(hour=4, minute=0, day_of_week=3),
        },
        # ── HIL deadline enforcement — every 60 s (PLAN-F-013) ───────────────
        "expire-overdue-hil-items-every-60s": {
            "task": "src.ai.hil.hil_timeout_task.expire_overdue_hil_items",
            "schedule": 60.0,  # seconds
        },
        # ── On-demand HIL fallback — every 60 s (PLAN-F-007 TASK-009) ────────
        "hil-fallback-check-every-60s": {
            "task": "ai.hil_fallback_check",
            "schedule": 60.0,  # seconds
        },
        # ── Tier-3 calibration — daily 02:00 UTC (PLAN-F-016) ────────────────
        "run-daily-calibration": {
            "task": "src.ai.evaluation.tasks.calibration_tasks.run_daily_calibration",
            "schedule": crontab(hour=2, minute=0),
        },
        # ── Watchlist scan fan-out — daily 17:30 UTC (PLAN-F-008) ─────────────
        "watchlist-scan-fanout-1730": {
            "task": "ai.watchlist_scan_fanout",
            "schedule": crontab(hour=17, minute=30),
        },
        # ── T-1 earnings detection — daily 17:30 UTC (PLAN-F-009) ───────────────
        "detect-t1-earnings-1730": {
            "task": "ai.detect_t1_earnings",
            "schedule": crontab(hour=17, minute=30),
        },
        # ── Earnings HIL fallback — every 60 s (PLAN-F-009 TASK-010) ─────────
        "earnings-hil-fallback-every-60s": {
            "task": "ai.earnings_hil_fallback",
            "schedule": 60.0,  # seconds
        },
        # ── Morning Brief fan-out — daily 05:30 UTC (PLAN-F-006) ─────────────
        "morning-brief-dispatch": {
            "task": "morning_brief.dispatch_all_users",
            "schedule": crontab(hour=5, minute=30),
        },
    }

    return app


# Module-level singleton — created at import time for celery CLI compatibility.
celery_app = create_celery_app()
