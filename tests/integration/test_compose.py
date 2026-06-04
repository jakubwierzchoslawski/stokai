"""
Integration tests for docker-compose.yml and docker/postgres/init.sql.

These tests use subprocess to invoke ``docker compose config`` — they do NOT
start any containers. Requires Docker CLI (Compose v2) on the PATH.

Run with:  pytest tests/integration/ -v -m integration
"""
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent
COMPOSE_FILE = PROJECT_ROOT / "docker-compose.yml"
INIT_SQL = PROJECT_ROOT / "docker" / "postgres" / "init.sql"

REQUIRED_SERVICES = {
    "api",
    "worker",
    "beat",
    "postgres",
    "redis",
    "langfuse-server",
    "langfuse-db",
    "clickhouse",
}


@pytest.mark.integration
def test_compose_file_parses_without_error():
    """docker compose config --quiet exits 0 for a valid compose file."""
    result = subprocess.run(
        ["docker", "compose", "-f", str(COMPOSE_FILE), "config", "--quiet"],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
    )
    assert result.returncode == 0, (
        f"docker compose config failed:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
    )


@pytest.mark.integration
def test_compose_defines_all_eight_services():
    """All eight canonical service names are present in the compose file."""
    result = subprocess.run(
        ["docker", "compose", "-f", str(COMPOSE_FILE), "config", "--services"],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
    )
    assert result.returncode == 0, (
        f"docker compose config --services failed:\n{result.stderr}"
    )
    found_services = set(result.stdout.strip().splitlines())
    missing = REQUIRED_SERVICES - found_services
    assert not missing, f"Missing services in docker-compose.yml: {missing}"


@pytest.mark.integration
def test_init_sql_creates_timescaledb_extension():
    """docker/postgres/init.sql must bootstrap TimescaleDB extension."""
    assert INIT_SQL.exists(), f"init.sql not found at {INIT_SQL}"
    content = INIT_SQL.read_text()
    assert "CREATE EXTENSION IF NOT EXISTS timescaledb" in content, (
        "init.sql must contain: CREATE EXTENSION IF NOT EXISTS timescaledb"
    )


@pytest.mark.integration
def test_init_sql_creates_vector_extension():
    """docker/postgres/init.sql must bootstrap pgvector extension."""
    assert INIT_SQL.exists(), f"init.sql not found at {INIT_SQL}"
    content = INIT_SQL.read_text()
    assert "CREATE EXTENSION IF NOT EXISTS vector" in content, (
        "init.sql must contain: CREATE EXTENSION IF NOT EXISTS vector"
    )
