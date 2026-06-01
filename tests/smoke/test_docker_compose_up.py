"""
CI smoke test — docker compose up on a Docker-only runner.

PLAN-N-008 TASK-006 — TDD: test written before the compose stack is fully verified.

Tests in this module are gated behind @pytest.mark.smoke.
Run only on CI runners with Docker Engine installed:
  pytest -m smoke

Do NOT run this test in regular unit/integration CI pipelines — it boots the
full Docker Compose stack and takes up to 5 minutes.

Required: Docker Engine and Docker Compose v2 must be available on the runner.
The runner must NOT have Python application dependencies installed — the test
verifies the containerised deployment, not the local dev environment.

Acceptance criteria: AC-001, AC-002, AC-004
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Generator

import pytest

try:
    import requests as _requests_lib
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

PROJECT_ROOT = Path(__file__).parent.parent.parent
APP_HEALTH_URL = "http://localhost:8000/health"
COMPOSE_UP_TIMEOUT = 300  # 5 minutes — AC-001 requirement
HEALTH_POLL_INTERVAL = 5  # seconds
STARTUP_ENV_FILE = PROJECT_ROOT / ".env"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def compose_stack() -> Generator[dict, None, None]:
    """
    Module-scoped fixture: boot the Docker Compose stack, yield metadata,
    then tear it down unconditionally (even on failure).
    """
    start_time = time.monotonic()

    # Boot stack
    result = subprocess.run(
        ["docker", "compose", "up", "-d", "--build", "--wait"],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        timeout=COMPOSE_UP_TIMEOUT,
    )

    boot_elapsed = time.monotonic() - start_time

    yield {
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "boot_elapsed": boot_elapsed,
        "start_time": start_time,
    }

    # Teardown — always, even on test failure
    subprocess.run(
        ["docker", "compose", "down", "-v"],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        timeout=120,
    )


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _poll_health(url: str, interval: int, timeout: int) -> tuple[bool, float]:
    """Poll url until HTTP 200 or timeout. Returns (success, elapsed_seconds)."""
    start = time.monotonic()
    while True:
        elapsed = time.monotonic() - start
        if elapsed > timeout:
            return False, elapsed
        try:
            if HAS_REQUESTS:
                resp = _requests_lib.get(url, timeout=5)
                if resp.status_code == 200:
                    return True, elapsed
            else:
                # Fallback: use subprocess curl
                result = subprocess.run(
                    ["curl", "-sf", url],
                    capture_output=True,
                    timeout=10,
                )
                if result.returncode == 0:
                    return True, elapsed
        except Exception:
            pass
        time.sleep(interval)


# ---------------------------------------------------------------------------
# Smoke tests
# ---------------------------------------------------------------------------

@pytest.mark.smoke
class TestDockerComposeUp:
    """AC-001: docker compose up → all services start, app accessible at localhost."""

    def test_compose_up_exits_zero(self, compose_stack: dict) -> None:
        """docker compose up -d --build --wait must exit with code 0."""
        assert compose_stack["returncode"] == 0, (
            f"docker compose up returned non-zero exit code {compose_stack['returncode']}.\n"
            f"stdout: {compose_stack['stdout'][-2000:]}\n"
            f"stderr: {compose_stack['stderr'][-2000:]}"
        )

    def test_app_accessible_at_localhost(self, compose_stack: dict) -> None:
        """AC-001: HTTP GET http://localhost:8000/health returns 200."""
        assert compose_stack["returncode"] == 0, "Stack did not start — skipping health check"

        healthy, elapsed = _poll_health(
            url=APP_HEALTH_URL,
            interval=HEALTH_POLL_INTERVAL,
            timeout=COMPOSE_UP_TIMEOUT,
        )
        assert healthy, (
            f"Application did not respond with HTTP 200 at {APP_HEALTH_URL} "
            f"within {COMPOSE_UP_TIMEOUT} seconds (AC-001 target: <= 300s). "
            f"Elapsed: {elapsed:.1f}s"
        )

    def test_startup_within_five_minutes(self, compose_stack: dict) -> None:
        """AC-001: all services healthy within 300 seconds (5 minutes)."""
        assert compose_stack["returncode"] == 0, "Stack did not start"
        assert compose_stack["boot_elapsed"] < COMPOSE_UP_TIMEOUT, (
            f"docker compose up took {compose_stack['boot_elapsed']:.1f}s — "
            f"exceeds the 300s (5-minute) target from AC-001."
        )


@pytest.mark.smoke
class TestAllServicesHealthy:
    """AC-004: all required services must be healthy after compose up."""

    def test_all_services_healthy(self, compose_stack: dict) -> None:
        """AC-004: parse docker compose ps JSON; assert every service is running/healthy."""
        assert compose_stack["returncode"] == 0, "Stack did not start — skipping service health check"

        result = subprocess.run(
            ["docker", "compose", "ps", "--format", "json"],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, (
            f"docker compose ps failed: {result.stderr}"
        )

        # docker compose ps --format json may output one JSON object per line
        services = []
        for line in result.stdout.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                services.append(json.loads(line))
            except json.JSONDecodeError:
                pass

        assert services, (
            f"docker compose ps returned no services. "
            f"stdout: {result.stdout[:1000]}"
        )

        unhealthy = []
        for svc in services:
            name = svc.get("Name", svc.get("Service", "unknown"))
            state = svc.get("State", svc.get("Status", "")).lower()
            health = svc.get("Health", "").lower()

            # Services without explicit healthchecks have empty Health field
            is_running = "running" in state or "up" in state
            is_healthy = health in ("healthy", "")  # empty = no healthcheck = ok

            if not is_running or not is_healthy:
                unhealthy.append(
                    f"{name}: state={state!r} health={health!r}"
                )

        assert not unhealthy, (
            f"AC-004 violation: the following services are not healthy:\n"
            + "\n".join(f"  - {s}" for s in unhealthy)
        )


@pytest.mark.smoke
class TestNoAzureCallsDuringStartup:
    """AC-002: no Azure-specific calls during startup (architecture P-10, D6)."""

    def test_no_azure_calls_during_startup(self, compose_stack: dict) -> None:
        """
        Assert application logs contain no lines matching 'azure' (case-insensitive).
        Verifies that the MVP default code path makes zero Azure SDK calls.
        """
        assert compose_stack["returncode"] == 0, "Stack did not start — skipping log check"

        result = subprocess.run(
            ["docker", "compose", "logs", "stokai-app"],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, f"docker compose logs failed: {result.stderr}"

        logs = result.stdout
        azure_lines = [
            (i + 1, line)
            for i, line in enumerate(logs.splitlines())
            if "azure" in line.lower()
        ]

        assert not azure_lines, (
            f"AC-002 violation: stokai-app logs contain Azure-related lines "
            f"(architecture P-10: no Azure SDK in default code path):\n"
            + "\n".join(f"  line {lineno}: {line}" for lineno, line in azure_lines[:20])
        )
