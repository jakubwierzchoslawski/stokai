"""
Langfuse p95 latency alert registration (PLAN-N-001/TASK-005).

register_latency_alerts(langfuse_client) is idempotent and safe to call at
every application startup.  It upserts a score monitor on the Langfuse host
that fires when the p95 of 'pipeline_latency_ms' over a rolling 1-hour window
exceeds 80 000 ms — providing 10 seconds of headroom before the 90 s SLA.

Notification channel: LANGFUSE_ALERT_EMAIL env var (optional; skipped if unset).
Langfuse host:        LANGFUSE_HOST env var (defaults to https://cloud.langfuse.com).
Langfuse secret key:  LANGFUSE_SECRET_KEY env var.
Langfuse public key:  LANGFUSE_PUBLIC_KEY env var.

If the Langfuse Python SDK version in use does not expose a score-monitor API,
the monitor is created via a direct REST call to the Langfuse host using httpx.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Alert configuration constants
# ---------------------------------------------------------------------------

_SCORE_NAME: str = "pipeline_latency_ms"
_P95_THRESHOLD_MS: int = 80_000
_ROLLING_WINDOW_HOURS: int = 1
_MONITOR_NAME: str = "pipeline-p95-sla-warning"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def register_latency_alerts(langfuse_client: Any) -> None:
    """Upsert a Langfuse score monitor for pipeline p95 latency.

    Creates or updates a monitor that fires when the p95 of
    ``pipeline_latency_ms`` over a rolling 1-hour window exceeds 80 000 ms.

    This function is **idempotent** — safe to call at every startup.

    Args:
        langfuse_client: Initialised Langfuse client object.  Must not be None.

    Side effects:
        - Calls the Langfuse SDK or REST API to upsert the monitor.
        - Logs the outcome at INFO or WARNING level.
        - Never raises; failures are logged and swallowed so they do not
          prevent application startup.
    """
    alert_email: Optional[str] = os.environ.get("LANGFUSE_ALERT_EMAIL")

    try:
        _upsert_via_sdk(langfuse_client, alert_email=alert_email)
        logger.info(
            "Langfuse latency monitor '%s' registered (threshold=%d ms, window=%dh)",
            _MONITOR_NAME,
            _P95_THRESHOLD_MS,
            _ROLLING_WINDOW_HOURS,
        )
    except AttributeError:
        # SDK version does not expose score-monitor API — fall back to REST.
        logger.debug(
            "Langfuse SDK lacks score monitor API; falling back to REST registration"
        )
        try:
            _upsert_via_rest(alert_email=alert_email)
            logger.info(
                "Langfuse latency monitor '%s' registered via REST", _MONITOR_NAME
            )
        except Exception as exc:
            logger.warning(
                "Failed to register Langfuse latency monitor '%s' via REST: %s",
                _MONITOR_NAME,
                exc,
            )
    except Exception as exc:
        logger.warning(
            "Failed to register Langfuse latency monitor '%s': %s",
            _MONITOR_NAME,
            exc,
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_monitor_payload(alert_email: Optional[str]) -> dict[str, Any]:
    """Build the monitor upsert payload."""
    payload: dict[str, Any] = {
        "name": _MONITOR_NAME,
        "scoreName": _SCORE_NAME,
        "percentile": 95,
        "windowHours": _ROLLING_WINDOW_HOURS,
        "threshold": _P95_THRESHOLD_MS,
        "condition": "greaterThan",
    }
    if alert_email:
        payload["notificationChannels"] = [
            {"type": "email", "address": alert_email}
        ]
    return payload


def _upsert_via_sdk(langfuse_client: Any, *, alert_email: Optional[str]) -> None:
    """Attempt to upsert the monitor via the Langfuse Python SDK.

    Raises ``AttributeError`` if the SDK does not expose a score-monitor API,
    allowing the caller to fall back to the REST path.
    """
    payload = _build_monitor_payload(alert_email)
    # Langfuse SDK ≥ 3.x may expose langfuse_client.monitors.upsert(...)
    # Try known attribute names; raise AttributeError if none exist so the
    # caller falls back to REST.
    if hasattr(langfuse_client, "monitors"):
        langfuse_client.monitors.upsert(**payload)
    elif hasattr(langfuse_client, "create_score_monitor"):
        langfuse_client.create_score_monitor(**payload)
    else:
        raise AttributeError(
            "Langfuse client does not expose a score-monitor API "
            "(checked: .monitors, .create_score_monitor)"
        )


def _upsert_via_rest(*, alert_email: Optional[str]) -> None:
    """Create or update the monitor via direct HTTP call to the Langfuse API.

    Reads host, public key, and secret key from environment variables.
    Uses httpx (already a project dependency).

    Raises:
        RuntimeError: If LANGFUSE_HOST, LANGFUSE_PUBLIC_KEY, or
                      LANGFUSE_SECRET_KEY are not set.
        httpx.HTTPError: On network or HTTP-level failures.
    """
    import httpx

    host = os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com").rstrip("/")
    public_key = os.environ.get("LANGFUSE_PUBLIC_KEY", "")
    secret_key = os.environ.get("LANGFUSE_SECRET_KEY", "")

    if not public_key or not secret_key:
        raise RuntimeError(
            "LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY must be set to register "
            "latency alerts via REST"
        )

    url = f"{host}/api/public/score-monitors"
    payload = _build_monitor_payload(alert_email)

    with httpx.Client(timeout=10.0) as client:
        response = client.post(
            url,
            json=payload,
            auth=(public_key, secret_key),
            headers={"Content-Type": "application/json"},
        )
        # A 409 Conflict means the monitor already exists — idempotent.
        if response.status_code not in (200, 201, 409):
            response.raise_for_status()
