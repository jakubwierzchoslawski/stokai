---
plan_id: PLAN-N-007
slug: portability-self-host
title: Portability and Self-Hostability
linked_requirement: REQ-N-007
type: non-functional
status: done
blocked_reason:
complexity: M
tdd_required: true
linked_nfrs:
  - { id: REQ-N-005, reason: "Self-hosted stack must keep AI + infra cost below $100/month; free OSS images (timescaledb-ha, redis:7, clickhouse) replace managed services at zero licensing cost" }
dependencies: []
executed_at: 2026-06-03T00:00:00Z
reviewed_at:
review_id:
created_at: 2026-06-02T00:00:00Z
updated_at: 2026-06-02T00:00:00Z
---

# PLAN-N-007 — Portability and Self-Hostability

## Linked Requirement
**REQ-N-007** — Portability and Self-Hostability
Status: approved | Jira:

## Objective
Produce all infrastructure-as-code artefacts that make the full StokAI stack bootable with `docker compose up` on any machine that has Docker installed and a populated `.env` file. This plan delivers: (1) a `docker-compose.yml` defining all eight services (`api`, `worker`, `beat`, `postgres`, `redis`, `langfuse-server`, `langfuse-db`, `clickhouse`); (2) a `Dockerfile` for the Python API/worker image; (3) a `.env.example` covering every required environment variable; (4) a Pydantic `Settings` class in `src/config/settings.py` that reads all configuration from environment variables and raises a hard startup error for any missing required variable; (5) a static-analysis CI job that scans `src/` for forbidden Azure SDK imports; and (6) a smoke-test CI job that validates `docker compose up` succeeds on a clean environment. No hardcoded URLs, ports, credentials, or service addresses may appear anywhere in application code; every value must be read from environment variables.

## Architecture Context
This plan implements Architecture Principle 4 (Containerized and Portable) and section 12.5 (Portability and Self-Host Parity). It also satisfies the 12-factor app requirements described in section 12.2 (Secrets Management — D3) and the fail-fast startup check mandated by that section. The `Settings` class (`src/config/settings.py`) is the single centralized config object consumed by every module across the six-layer model. All service-to-service addresses (`DATABASE_URL`, `REDIS_URL`, `LANGFUSE_HOST`, etc.) listed in Architecture section 15 are read exclusively from this class. The `docker-compose.yml` maps one-to-one to the Azure service equivalents tabulated in Architecture section 12.5, so switching between cloud and self-host is purely an environment variable change. The `Dockerfile` produces the same image used for both local development and production, achieving dev/prod parity (12-factor factor VI).

## Applied NFR Constraints
| NFR | Constraint | Impact on this plan |
|-----|-----------|---------------------|
| REQ-N-005 | AI + infrastructure combined < $100/month | All self-hosted container images are open-source with no licensing fee. The compose file must not reference any paid managed service. Service sizing (memory limits) must be documented so operators can target a sub-$100/month VPS footprint |

## Component Design

### New Components
```
Project root:
  docker-compose.yml          — eight-service compose definition
  docker-compose.override.yml — local-dev overrides (hot-reload, exposed ports)
  Dockerfile                  — multi-stage Python image for api / worker / beat
  .env.example                — all required env vars with safe placeholder values

src/config/
  __init__.py
  settings.py                 — Pydantic BaseSettings; single Settings instance
  celery_app.py               — Celery application configured from Settings

docker/
  postgres/
    init.sql                  — TimescaleDB + pgvector extension bootstrap

tests/
  test_settings.py            — unit tests for Settings validation
  integration/
    test_smoke.py             — docker compose up health-check test (CI only)

.github/
  workflows/
    ci.yml                    — CI pipeline: lint + tests + azure-import scan + compose smoke test
```

### Modified Components
| File | Change | Reason |
|------|--------|--------|
| `Makefile` | Add `make up`, `make down`, `make test`, `make scan-azure` targets | Developer ergonomics; no hardcoded commands in CI |
| `.gitignore` | Ensure `.env` is listed; never committed | D3 / 12-factor |

### Interfaces and Contracts
The executor must implement these exactly.

```python
# src/config/settings.py

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import AnyUrl, field_validator
from functools import lru_cache

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ── Application ──────────────────────────────────────────────────────────
    ENVIRONMENT: str = "local"        # local | test | staging | production
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    # ── Database ─────────────────────────────────────────────────────────────
    DATABASE_URL: str                 # required — no default
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 5

    # ── Redis / Celery ────────────────────────────────────────────────────────
    REDIS_URL: str                    # required — no default
    CELERY_BROKER_URL: str = ""       # defaults to REDIS_URL at startup if blank
    CELERY_RESULT_BACKEND: str = ""   # defaults to REDIS_URL at startup if blank

    # ── AI Providers ──────────────────────────────────────────────────────────
    ANTHROPIC_API_KEY: str            # required
    OPENAI_API_KEY: str               # required (embeddings)

    # ── External Integrations ─────────────────────────────────────────────────
    FINNHUB_API_KEY: str = ""         # optional; resolved via source_config at runtime
    FMP_API_KEY: str = ""             # optional
    SENDGRID_API_KEY: str = ""        # optional; alerts disabled if blank

    # ── Langfuse Observability ────────────────────────────────────────────────
    LANGFUSE_SECRET_KEY: str = ""     # optional; no-op if blank
    LANGFUSE_PUBLIC_KEY: str = ""     # optional
    LANGFUSE_HOST: str = "http://langfuse-server:3000"

    # ── JWT ───────────────────────────────────────────────────────────────────
    JWT_SECRET_KEY: str               # required
    JWT_REFRESH_SECRET_KEY: str       # required
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # ── Filesystem paths ──────────────────────────────────────────────────────
    AGENTS_DIR: str = "agents"
    PROMPTS_DIR: str = "prompts"

    # ── Port binding (12-factor) ──────────────────────────────────────────────
    PORT: int = 8000

    @field_validator("ENVIRONMENT")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        allowed = {"local", "test", "staging", "production"}
        if v not in allowed:
            raise ValueError(f"ENVIRONMENT must be one of {allowed}, got {v!r}")
        return v

    @field_validator("CELERY_BROKER_URL", mode="before")
    @classmethod
    def default_broker_to_redis(cls, v: str, info) -> str:
        if not v:
            return info.data.get("REDIS_URL", "")
        return v

    @field_validator("CELERY_RESULT_BACKEND", mode="before")
    @classmethod
    def default_backend_to_redis(cls, v: str, info) -> str:
        if not v:
            return info.data.get("REDIS_URL", "")
        return v


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the singleton Settings instance.
    Called once at module import; subsequent calls return the cached object.
    Raises ValidationError on first call if any required variable is missing."""
    return Settings()
```

```python
# src/config/celery_app.py

from celery import Celery
from src.config.settings import get_settings

def create_celery_app() -> Celery:
    settings = get_settings()
    app = Celery("stokai")
    app.conf.broker_url = settings.CELERY_BROKER_URL
    app.conf.result_backend = settings.CELERY_RESULT_BACKEND
    app.conf.task_serializer = "json"
    app.conf.result_serializer = "json"
    app.conf.accept_content = ["json"]
    app.conf.timezone = "UTC"
    app.conf.enable_utc = True
    return app

celery_app = create_celery_app()
```

Docker Compose service structure (canonical names — executor must use exactly these names):

```
api             image: stokai-app  command: uvicorn src.main:app --host 0.0.0.0 --port ${PORT:-8000}
worker          image: stokai-app  command: celery -A src.config.celery_app worker --loglevel=info
beat            image: stokai-app  command: celery -A src.config.celery_app beat --loglevel=info
postgres        image: timescale/timescaledb-ha:pg16
redis           image: redis:7-alpine
langfuse-server image: langfuse/langfuse:latest
langfuse-db     image: postgres:16-alpine
clickhouse      image: clickhouse/clickhouse-server:24
```

---

## Implementation Tasks

### TASK-001: Pydantic Settings class with fail-fast validation · M/TDD · src/config/settings.py,src/config/__init__.py,tests/test_settings.py

Implement the `Settings` class using `pydantic-settings` `BaseSettings`. Every field defined in the Interfaces and Contracts section must be present with the exact type, default, and validator shown. Required fields (`DATABASE_URL`, `REDIS_URL`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `JWT_SECRET_KEY`, `JWT_REFRESH_SECRET_KEY`) must have no default value so Pydantic raises `ValidationError` immediately when the env var is absent. The `CELERY_BROKER_URL` and `CELERY_RESULT_BACKEND` fields default to `REDIS_URL` when blank. The `get_settings()` `@lru_cache` factory must be the sole entry point so the settings object is a true singleton per process. Ensure `Settings` reads from both the `.env` file and actual environment variables; real env vars take precedence over the file (Pydantic default behaviour).

**Tests to write first (TDD):**
- `test_settings_raises_when_database_url_missing` — unset `DATABASE_URL`; assert `ValidationError` raised by `Settings()`
- `test_settings_raises_when_redis_url_missing` — same pattern for `REDIS_URL`
- `test_settings_raises_when_anthropic_api_key_missing`
- `test_settings_raises_when_jwt_secret_key_missing`
- `test_settings_raises_when_jwt_refresh_secret_key_missing`
- `test_settings_raises_when_openai_api_key_missing`
- `test_celery_broker_defaults_to_redis_url` — provide `REDIS_URL`; omit `CELERY_BROKER_URL`; assert `settings.CELERY_BROKER_URL == settings.REDIS_URL`
- `test_celery_result_backend_defaults_to_redis_url` — same for result backend
- `test_invalid_environment_value_raises` — `ENVIRONMENT=staging2` must fail
- `test_valid_full_settings_object_is_constructed` — all required vars set; assert object fields match
- `test_get_settings_returns_singleton` — two calls to `get_settings()` return the same object id

**AC covered**: AC-003

---

### TASK-002: Celery application module · S/no-TDD · src/config/celery_app.py

Implement `create_celery_app()` and the module-level `celery_app` singleton exactly as specified in the Interfaces and Contracts section. The function must call `get_settings()` — never construct `Settings()` directly — so the singleton is respected. Celery configuration must contain no hardcoded broker or backend URLs; every value is read from `Settings`. Set `task_serializer`, `result_serializer`, `accept_content`, `timezone`, and `enable_utc` as shown. The module-level `celery_app` is created at import time so `celery -A src.config.celery_app worker` works without additional factory calls.

**AC covered**: AC-003

---

### TASK-003: Dockerfile — multi-stage Python image · S/no-TDD · Dockerfile

Write a multi-stage `Dockerfile`. Stage 1 (`builder`): use `python:3.12-slim` as base; install build dependencies; copy `pyproject.toml` and lock file; run `pip install --no-cache-dir` into `/app/dist`; do not copy application source. Stage 2 (`runtime`): use `python:3.12-slim` as base; copy installed packages from builder stage; copy application source; set `WORKDIR /app`; create a non-root user `stokai` and switch to it; expose `${PORT:-8000}` via `ENV PORT 8000` and `EXPOSE $PORT`; set `CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]`. No secrets, passwords, API keys, or environment-specific values may appear in the Dockerfile. All runtime configuration is injected at container start via environment variables. The image must not bake in a `.env` file.

**AC covered**: AC-001, AC-003

---

### TASK-004: docker-compose.yml — full eight-service stack · M/TDD · docker-compose.yml,docker/postgres/init.sql

Write `docker-compose.yml` with exactly these eight services, all on a single internal bridge network named `stokai-net`. Every inter-service address must be a service DNS name (e.g. `postgres`, `redis`), never a hardcoded IP. Every credential or URL exposed to the application must be read from environment variable substitution (`${VAR}`), not hardcoded.

Service specifications:

**postgres**: image `timescale/timescaledb-ha:pg16`. Environment: `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` from env vars. Volume: named volume `postgres-data`. Init script: mounts `./docker/postgres/init.sql` into `/docker-entrypoint-initdb.d/`. Healthcheck: `pg_isready -U ${POSTGRES_USER}`.

**redis**: image `redis:7-alpine`. No password in compose (password optional; operator sets `requirepass` via command or env). Volume: named volume `redis-data`. Healthcheck: `redis-cli ping`.

**langfuse-db**: image `postgres:16-alpine`. Environment: `LANGFUSE_DB_USER`, `LANGFUSE_DB_PASSWORD`, `LANGFUSE_DB_NAME` from env vars. Volume: named volume `langfuse-db-data`. Healthcheck: `pg_isready`.

**clickhouse**: image `clickhouse/clickhouse-server:24`. Volume: named volume `clickhouse-data`. Healthcheck: `wget -q --tries=1 http://localhost:8123/ping -O-`.

**langfuse-server**: image `langfuse/langfuse:latest`. `depends_on` langfuse-db and clickhouse (condition: service_healthy). All required Langfuse env vars passed from host env (`LANGFUSE_SECRET_KEY`, `LANGFUSE_PUBLIC_KEY`, `DATABASE_URL` pointing to langfuse-db, `CLICKHOUSE_URL`).

**api**: build context `.`; image `stokai-app`. `depends_on` postgres and redis (condition: service_healthy). `env_file: .env`. Port published: `${API_PORT:-8000}:${PORT:-8000}`. Healthcheck: `wget -q --tries=1 http://localhost:${PORT:-8000}/health -O-`. Restart policy: `unless-stopped`.

**worker**: same image `stokai-app`. Command: `celery -A src.config.celery_app worker --loglevel=info --concurrency=2`. `depends_on` api (condition: service_healthy), postgres, redis. `env_file: .env`. No published ports.

**beat**: same image `stokai-app`. Command: `celery -A src.config.celery_app beat --loglevel=info --scheduler django_celery_beat.schedulers:DatabaseScheduler`. `depends_on` worker. `env_file: .env`. Restart policy: `unless-stopped`.

Write `docker/postgres/init.sql` to create extensions: `CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;` and `CREATE EXTENSION IF NOT EXISTS vector;`.

TDD for this task means a pytest test (marked `@pytest.mark.integration`) that uses `subprocess.run(["docker", "compose", "config", "--quiet"])` to validate the compose file parses without error, and `subprocess.run(["docker", "compose", "config", "--services"])` to assert all eight service names are present. These tests run against the file on disk and require only Docker CLI — no container is started.

**Tests to write first (TDD):**
- `test_compose_file_parses_without_error` — `docker compose config --quiet` exits 0
- `test_compose_defines_all_eight_services` — services output contains exactly: api, worker, beat, postgres, redis, langfuse-server, langfuse-db, clickhouse
- `test_init_sql_creates_timescaledb_extension` — file content contains `CREATE EXTENSION IF NOT EXISTS timescaledb`
- `test_init_sql_creates_vector_extension` — file content contains `CREATE EXTENSION IF NOT EXISTS vector`

**AC covered**: AC-001, AC-004

---

### TASK-005: docker-compose.override.yml — local development overrides · XS/no-TDD · docker-compose.override.yml

Write a `docker-compose.override.yml` that adds local-development convenience settings without modifying `docker-compose.yml`. Overrides: mount the project source as a volume into `api`, `worker`, and `beat` containers (`./:/app`) to enable hot-reload; expose postgres port `${POSTGRES_PORT:-5432}:5432` and redis port `${REDIS_PORT:-6379}:6379` so local tools (psql, redis-cli) can connect; set `DEBUG=true` and `LOG_LEVEL=DEBUG` for `api` via environment override. The override file must not duplicate service definitions — it may only extend existing services. Include a comment at the top explaining that this file is merged automatically by Docker Compose in local dev and must not be committed with production credentials.

**AC covered**: AC-001

---

### TASK-006: .env.example — complete variable catalogue · S/no-TDD · .env.example

Write `.env.example` with every environment variable consumed by `Settings`, `docker-compose.yml`, and `docker-compose.override.yml`. Organize variables into labelled sections matching the `Settings` class: Application, Database, Redis/Celery, AI Providers, External Integrations, Langfuse, JWT, Filesystem, Port Binding, and Docker Compose (postgres credentials, langfuse-db credentials). Every required variable (no default in `Settings`) must have a placeholder value that is obviously fake (e.g. `ANTHROPIC_API_KEY=sk-ant-REPLACE_ME`). Every optional variable must have a blank value or a sensible default matching the `Settings` default (e.g. `LOG_LEVEL=INFO`). Include inline comments on each non-obvious variable explaining its purpose. The file must be complete enough that a new developer can copy it to `.env`, fill in the `REPLACE_ME` values, run `docker compose up`, and have a working stack.

**AC covered**: AC-001, AC-003, AC-004

---

### TASK-007: Makefile targets for common developer workflows · XS/no-TDD · Makefile

Write a `Makefile` with the following targets: `up` (`docker compose up -d --build`); `down` (`docker compose down`); `logs` (`docker compose logs -f`); `test` (`pytest tests/ -v`); `test-integration` (`pytest tests/integration/ -v -m integration`); `scan-azure` (runs the ruff/grep check from TASK-008); `shell-api` (`docker compose exec api bash`); `migrate` (`docker compose exec api alembic upgrade head`); `ps` (`docker compose ps`). Each target must have a one-line `## comment` describing it. Include a `help` target that prints all targets with their descriptions by parsing the `##` comments. No shell scripts other than Makefile recipe lines; all logic expressed in `docker compose` and standard POSIX commands.

**AC covered**: AC-001

---

### TASK-008: Static analysis CI job — zero Azure SDK imports in src/ · M/TDD · .github/workflows/ci.yml,tests/test_azure_import_scan.py

Write a pytest test in `tests/test_azure_import_scan.py` that uses Python's `ast` module to walk every `.py` file under `src/` and assert that no `import` or `from ... import` statement references a module whose name starts with `azure`. The test uses `pathlib.Path("src").rglob("*.py")` to discover all source files, builds an AST for each, and collects all import nodes. Any file containing an Azure import causes the test to fail with a message listing the offending file and import. This test is runnable locally and in CI without Docker. Additionally, write the GitHub Actions workflow in `.github/workflows/ci.yml` with jobs: `lint` (ruff check + ruff format --check), `test-unit` (pytest tests/ -v --ignore=tests/integration), `azure-import-scan` (runs `test_azure_import_scan.py` as a standalone pytest), and `compose-smoke` (calls `docker compose up -d --wait --timeout 120` on a fresh CI runner, then GETs `http://localhost:8000/health` and asserts HTTP 200, then calls `docker compose down`). The `compose-smoke` job depends on the other three jobs passing.

**Tests to write first (TDD):**
- `test_no_azure_imports_found_in_src` — the main scan test; fails if any `azure.*` import exists in `src/`
- `test_scan_detects_forbidden_import_in_fixture` — creates a temp `.py` file with `import azure.identity`; asserts the scanner reports it as a violation (validates the scanner logic itself)
- `test_scan_ignores_files_outside_src` — a file in `tests/` containing `import azure.identity` must not be flagged

**AC covered**: AC-002

---

### TASK-009: Admin health endpoint for smoke test · S/no-TDD · src/admin/data_sources/health_flush_task.py,src/main.py

Add a `GET /health` endpoint to the FastAPI application that returns `{"status": "ok", "environment": settings.ENVIRONMENT}` with HTTP 200. This endpoint must not require authentication (it is the compose smoke-test target). Additionally, implement a Celery periodic task `health_flush_task` in `src/admin/data_sources/health_flush_task.py` that runs every 60 seconds and writes a heartbeat timestamp to Redis (`SET stokai:health:last_beat <iso-timestamp> EX 120`). The health endpoint checks for this key and includes `"worker_alive": true/false` in the response based on whether the key exists. This design validates that the worker-to-Redis pathway is working in the smoke test without executing any business logic.

**AC covered**: AC-001

---

## Acceptance Criteria Coverage

- AC-001: Given a fresh machine with Docker and a populated `.env` file, `docker compose up` starts all services within 10 minutes → TASK-003, TASK-004, TASK-005, TASK-006, TASK-007, TASK-009
- AC-002: Given a codebase scan for Azure SDK imports in `src/`, zero results are found → TASK-008
- AC-003: All service URLs, credentials, and feature flags are read from environment variables; no hardcoded values in source files → TASK-001, TASK-002, TASK-003, TASK-006
- AC-004: Changing `.env` database URL from Azure PostgreSQL to localhost container requires no code changes → TASK-001, TASK-004, TASK-006

## Acceptance Notes

The `compose-smoke` CI job (TASK-008) requires a GitHub Actions runner with Docker Compose v2 installed. The job uses `--wait` flag (Compose v2.1+) to block until all services pass their healthchecks or timeout. The 120-second timeout matches the AC-001 "within 10 minutes" criterion at a conservative margin appropriate for CI cold-start (image pull included). Operators running on a machine with pre-pulled images should see a significantly shorter boot time.

## Risks and Notes

- The `timescale/timescaledb-ha:pg16` image is large (~700 MB compressed). First `docker compose up` on a fresh machine may take 3–5 minutes for image pulls alone. The 10-minute AC-001 target is achievable with a reasonable broadband connection but should be validated on the reference CI runner before committing to this SLA.
- `docker-compose.override.yml` mounts source code as a volume into the running containers for hot-reload in local dev. This override must not be used in production. The CI `compose-smoke` job must explicitly specify `docker compose -f docker-compose.yml up` (without the override) to test the production-equivalent configuration.
- The `beat` service uses `celery beat` with a database-backed scheduler (`django_celery_beat`). If `django_celery_beat` is not in the dependency stack (it is a Django extension), the scheduler should be changed to the filesystem scheduler (`celery.schedulers.PersistentScheduler`) with a volume mount for the schedule database file. The executor must confirm the scheduler package before implementing TASK-004.
- Langfuse self-hosted requires non-trivial `DATABASE_URL` and `CLICKHOUSE_URL` environment variables pointing to its companion services. The `langfuse-server` service's exact required environment variable names must be verified from the official Langfuse Docker Compose reference at the time of implementation — the variable names may differ from the Langfuse public cloud variable names.
- The `@lru_cache` on `get_settings()` means that unit tests must clear the cache between tests using `get_settings.cache_clear()` in teardown, otherwise a test that patches an env var will be masked by the cached instance from a previous test.
