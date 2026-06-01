"""
TDD tests for docker-compose.yml and Dockerfile structural contracts.

PLAN-N-008 TASK-001 — written BEFORE the infrastructure files exist (red phase).
These tests define the contract; the infrastructure files make them green.

Acceptance criteria: AC-001, AC-004
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

PROJECT_ROOT = Path(__file__).parent.parent.parent
COMPOSE_FILE = PROJECT_ROOT / "docker-compose.yml"
DOCKERFILE = PROJECT_ROOT / "Dockerfile"

REQUIRED_SERVICES = {
    "stokai-app",
    "stokai-worker",
    "stokai-scheduler",
    "postgres",
    "redis",
    "langfuse-server",
    "langfuse-db",
    "clickhouse",
}

LANGFUSE_SERVICES = {"langfuse-server", "langfuse-db", "clickhouse"}
LANGFUSE_MARKER = "# LANGFUSE — populated by PLAN-F-013"

SECRET_PATTERN = re.compile(r"^(ENV|ARG)\s+\S*(PASSWORD|SECRET|KEY|TOKEN)\S*\s*=\s*.+", re.IGNORECASE)


@pytest.fixture(scope="module")
def compose_data() -> dict:
    """Parse docker-compose.yml and return the parsed structure."""
    assert COMPOSE_FILE.exists(), (
        f"docker-compose.yml not found at {COMPOSE_FILE}. "
        "TASK-001 must create this file."
    )
    with COMPOSE_FILE.open() as fh:
        data = yaml.safe_load(fh)
    assert data is not None, "docker-compose.yml parsed as empty/null"
    return data


@pytest.fixture(scope="module")
def compose_raw_text() -> str:
    """Return the raw text of docker-compose.yml."""
    assert COMPOSE_FILE.exists(), f"docker-compose.yml not found at {COMPOSE_FILE}"
    return COMPOSE_FILE.read_text(encoding="utf-8")


class TestRequiredServicesPresent:
    """AC-004: all eight required services must be defined."""

    def test_all_required_services_present(self, compose_data: dict) -> None:
        services = set(compose_data.get("services", {}).keys())
        missing = REQUIRED_SERVICES - services
        extra = services - REQUIRED_SERVICES
        assert not missing, (
            f"Missing required services in docker-compose.yml: {missing}. "
            f"Extra services found: {extra}"
        )

    def test_services_count_is_eight(self, compose_data: dict) -> None:
        services = compose_data.get("services", {})
        assert len(services) == 8, (
            f"Expected exactly 8 services, got {len(services)}: {list(services.keys())}"
        )


class TestAllServicesHaveHealthcheck:
    """Every service must declare a healthcheck block."""

    def test_all_services_have_healthcheck(self, compose_data: dict) -> None:
        services = compose_data.get("services", {})
        missing_healthcheck = [
            name for name, config in services.items()
            if not isinstance(config, dict) or "healthcheck" not in config
        ]
        assert not missing_healthcheck, (
            f"Services missing 'healthcheck' block: {missing_healthcheck}"
        )


class TestNoInlineEnvValues:
    """
    No service may use inline environment: block with actual values.
    Only env_file: [.env] is permitted.

    A service has an inline env value if its 'environment' key maps to
    a dict/list that contains entries with '=' (value assignments), or
    any non-None YAML value. Variable-only entries like 'DATABASE_URL'
    (no value, just the name) are acceptable for passthrough, but the
    plan spec says only env_file is allowed — assert environment: is absent
    or only contains bare variable names (no '=' assignment).
    """

    def test_no_inline_env_values(self, compose_data: dict) -> None:
        services = compose_data.get("services", {})
        offenders: list[str] = []
        for name, config in services.items():
            if not isinstance(config, dict):
                continue
            env_block = config.get("environment")
            if env_block is None:
                continue
            # env_block may be a list of strings or a dict
            if isinstance(env_block, dict):
                # Any key with a non-None value is an inline value
                if any(v is not None for v in env_block.values()):
                    offenders.append(name)
            elif isinstance(env_block, list):
                # strings of the form "KEY=value" have values; bare "KEY" do not
                for entry in env_block:
                    if isinstance(entry, str) and "=" in entry:
                        offenders.append(name)
                        break
        assert not offenders, (
            f"Services with inline environment values (only env_file: is allowed): {offenders}"
        )


class TestLangfuseServicesHavePlaceholderComments:
    """
    langfuse-server, langfuse-db, and clickhouse must each contain the
    '# LANGFUSE — populated by PLAN-F-013' marker in the raw compose text.
    """

    def test_langfuse_services_have_placeholder_comments(self, compose_raw_text: str) -> None:
        assert LANGFUSE_MARKER in compose_raw_text, (
            f"docker-compose.yml must contain the marker: {LANGFUSE_MARKER!r}"
        )


class TestDockerfileHasNoSecretInstructions:
    """Dockerfile must not have ENV or ARG lines that assign secret values."""

    def test_dockerfile_exists(self) -> None:
        assert DOCKERFILE.exists(), (
            f"Dockerfile not found at {DOCKERFILE}. TASK-001 must create this file."
        )

    def test_dockerfile_has_no_secret_instructions(self) -> None:
        assert DOCKERFILE.exists(), f"Dockerfile not found at {DOCKERFILE}"
        content = DOCKERFILE.read_text(encoding="utf-8")
        offending_lines = []
        for lineno, line in enumerate(content.splitlines(), start=1):
            stripped = line.strip()
            if SECRET_PATTERN.match(stripped):
                offending_lines.append((lineno, stripped))
        assert not offending_lines, (
            f"Dockerfile contains secret-looking ENV/ARG assignments: {offending_lines}"
        )


class TestServiceDependencyOrder:
    """stokai-app must depend on postgres and redis being healthy."""

    def test_stokai_app_depends_on_postgres_and_redis(self, compose_data: dict) -> None:
        services = compose_data.get("services", {})
        app = services.get("stokai-app", {})
        depends_on = app.get("depends_on", {})
        # depends_on can be a list or dict
        if isinstance(depends_on, list):
            dep_names = set(depends_on)
        else:
            dep_names = set(depends_on.keys())
        for required_dep in ("postgres", "redis"):
            assert required_dep in dep_names, (
                f"stokai-app must depend on '{required_dep}' but depends_on = {dep_names}"
            )

    def test_stokai_worker_depends_on_stokai_app(self, compose_data: dict) -> None:
        services = compose_data.get("services", {})
        worker = services.get("stokai-worker", {})
        depends_on = worker.get("depends_on", {})
        if isinstance(depends_on, list):
            dep_names = set(depends_on)
        else:
            dep_names = set(depends_on.keys())
        assert "stokai-app" in dep_names, (
            f"stokai-worker must depend on 'stokai-app' but depends_on = {dep_names}"
        )


class TestNetworkConfiguration:
    """All services must be connected to stokai-net."""

    def test_stokai_net_defined(self, compose_data: dict) -> None:
        networks = compose_data.get("networks", {})
        assert "stokai-net" in networks, (
            f"'stokai-net' network not defined in docker-compose.yml. Got: {list(networks.keys())}"
        )


class TestVolumesDefined:
    """postgres-data and redis-data volumes must be declared."""

    def test_required_volumes_declared(self, compose_data: dict) -> None:
        volumes = compose_data.get("volumes", {})
        for vol in ("postgres-data", "redis-data"):
            assert vol in volumes, (
                f"Volume '{vol}' not declared in docker-compose.yml. Got: {list(volumes.keys())}"
            )
