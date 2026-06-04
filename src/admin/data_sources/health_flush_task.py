"""
Celery periodic task: health heartbeat flush.

Runs every 60 seconds. Writes a timestamp to Redis so the /health endpoint
can determine whether the worker-to-Redis pathway is alive.

Key:    stokai:health:last_beat
Value:  ISO-8601 UTC timestamp
TTL:    120 seconds (2x beat interval — key expires if worker dies)
"""
from datetime import UTC, datetime

import redis as redis_lib

from src.config.celery_app import celery_app
from src.config.settings import get_settings

HEARTBEAT_KEY = "stokai:health:last_beat"
HEARTBEAT_TTL = 120  # seconds — 2x the beat period


@celery_app.task(name="src.admin.data_sources.health_flush_task.health_flush")
def health_flush() -> str:
    """Write a heartbeat timestamp to Redis and return the timestamp string."""
    settings = get_settings()
    client = redis_lib.from_url(settings.REDIS_URL, decode_responses=True)
    timestamp = datetime.now(UTC).isoformat()
    try:
        client.set(HEARTBEAT_KEY, timestamp, ex=HEARTBEAT_TTL)
    finally:
        client.close()
    return timestamp
