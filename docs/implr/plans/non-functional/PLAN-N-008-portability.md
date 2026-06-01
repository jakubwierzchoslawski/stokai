---
plan_id: PLAN-N-008
slug: n-portability
title: NFR — Portability & Self-Hostability
linked_requirement: REQ-N-008
type: non-functional
status: done
blocked_reason:
complexity: M
tdd_required: true
linked_nfrs: []
dependencies:
  - { id: PLAN-F-013, reason: "Langfuse containers added to docker-compose.yml by F-013 execution" }
executed_at: 2026-06-01T00:00:00Z
reviewed_at:
review_id:
created_at: 2026-05-31T00:00:00Z
updated_at: 2026-06-01T00:00:00Z
---

# PLAN-N-008 — NFR — Portability & Self-Hostability

## Linked Requirement
**REQ-N-008** — NFR — Portability & Self-Hostability
Status: approved | Jira: —

## Objective

This plan delivers the infrastructure artefacts that make the full StokAI stack runnable on any
machine with only Docker installed. It produces: a multi-service `docker-compose.yml` defining
eight services (stokai-app, stokai-worker, stokai-scheduler, postgres, redis, langfuse-server,
langfuse-db, clickhouse); a multi-stage `Dockerfile` for the application image; a committed
`.env.example` covering every configuration variable; a `docker-compose.override.yml` for local
development ergonomics; and a `Makefile` with convenience targets. It then wires two automated
verification gates — a CI smoke test (`tests/smoke/`) that boots the stack on a Docker-only
runner and asserts all services are healthy, and a static analysis test (`tests/static/`) that
runs Bandit plus custom grep patterns to prove zero hardcoded connection strings or credentials
exist anywhere under `src/`. This plan does not implement application logic; it verifies that the
VaultProvider abstraction (PLAN-F-022) and the ProviderRegistry config swap (PLAN-F-002) already
satisfy their portability contracts at the infrastructure boundary.

## Architecture Context

This plan sits entirely in the **Deployment Architecture** layer described in ARCHITECTURE.md §15
and enforces **P-06 (12-Factor Compliance)** and **P-10 (Portability First)** from §2. The
confirmed decision **D6** (Docker Compose primary, no Azure-specific code in MVP) is the direct
authority for every task here.

Modules touched or introduced:

| Path | Role |
|------|------|
| `docker-compose.yml` (project root) | Primary service orchestration file; eight services |
| `docker-compose.override.yml` (project root) | Development overrides — bind-mount `src/`, expose debug ports |
| `Dockerfile` (project root) | Multi-stage build: `builder` stage + `runtime` stage; shared by stokai-app, stokai-worker, stokai-scheduler via `command:` override |
| `.env.example` (project root) | Committed template; no values; all variables required by the application |
| `.gitignore` (project root) | Ensures `.env` is never committed |
| `Makefile` (project root) | `make up`, `make down`, `make logs`, `make shell`, `make deploy-prompts` |
| `tests/smoke/test_docker_compose_up.py` | CI gate: starts compose stack on a Docker-only runner, polls /health, asserts all services healthy within 5 minutes |
| `tests/static/test_no_hardcoded_config.py` | Static analysis gate: Bandit B105/B106/B107 + grep for `localhost`, `127.0.0.1`, `postgres://`, `redis://`, `azure` literals in `src/` |

The `src/config/` module (architecture §4) is the application-layer counterpart: it reads all
variables from `os.environ` via the **VaultProvider** protocol delivered by PLAN-F-022 and
validated at startup. This plan does not implement `src/config/`; it verifies that once PLAN-F-022
exists the static analysis tests pass cleanly.

The **ProviderRegistry** (PLAN-F-002) is verified by TASK-004 through a config-only swap
integration test — no source changes permitted; only `provider_config.yaml` is edited.

**Soft dependency on PLAN-F-013**: The Langfuse service block in `docker-compose.yml` is
scaffolded here with image references and health-check stubs. When PLAN-F-013 executes, it fills
in the exact image tags, volume mounts, and startup commands. The compose file structure must
accommodate that without a merge conflict; this is ensured by isolating the Langfuse service
definitions in a clearly labelled section with `# LANGFUSE — populated by PLAN-F-013` comments.

## Applied NFR Constraints

| NFR | Constraint | Impact on this plan |
|-----|-----------|---------------------|
| REQ-N-008 (this plan) | `docker compose up` → all services healthy ≤ 5 minutes; 0 Azure dependencies in default path; 100% config from env vars; 0 provider-swap code changes | All five tasks directly serve these measurable targets |
| C-001 (cost) | AI + infrastructure < $100/month total | Docker Compose self-hosted approach is the mechanism that keeps infra cost within budget; no Azure managed services in default path means no surprise cloud billing |
| P-06 (12-factor) | All config from env vars; `.env.example` committed; `.env` never committed | Enforced by TASK-002 (.env.example) and TASK-005 (static analysis gate) |
| P-10 (Portability First) | No Azure-specific code in MVP default path | Enforced by TASK-005 (grep/Bandit) and TASK-003 (azure_vault_provider.py isolation check) |
| REQ-N-007 (security) | Secrets never in source; vault-abstracted | Enforced by TASK-005 Bandit B105/B106/B107 checks |

## Component Design

### New Infrastructure Files

```
project root/
├── docker-compose.yml              # production/CI compose; eight services
├── docker-compose.override.yml     # dev overrides; bind-mount src/; debug ports
├── Dockerfile                      # multi-stage; builder + runtime
├── .env.example                    # all vars, no values
├── .gitignore                      # ensures .env never committed
└── Makefile                        # make up / down / logs / shell / deploy-prompts

tests/
├── smoke/
│   ├── __init__.py
│   └── test_docker_compose_up.py   # CI smoke test
└── static/
    ├── __init__.py
    └── test_no_hardcoded_config.py # Bandit + grep static analysis
```

### docker-compose.yml Service Topology

```
services:
  stokai-app          FastAPI application; image: stokai-app:latest; build: .
  stokai-worker       Celery worker; same image; command override
  stokai-scheduler    Celery beat scheduler; same image; command override
  postgres            postgres:16-alpine + init.sql for TimescaleDB + pgvector
  redis               redis:7-alpine
  langfuse-server     # LANGFUSE — populated by PLAN-F-013
  langfuse-db         # LANGFUSE — populated by PLAN-F-013
  clickhouse          # LANGFUSE — populated by PLAN-F-013

networks:
  stokai-net          internal bridge

volumes:
  postgres-data
  redis-data
  langfuse-db-data    # LANGFUSE — populated by PLAN-F-013
  clickhouse-data     # LANGFUSE — populated by PLAN-F-013
```

Health checks:
- `postgres`: `pg_isready -U ${POSTGRES_USER}`
- `redis`: `redis-cli ping`
- `stokai-app`: `curl -f http://localhost:8000/health`
- `stokai-worker`: `celery -A src.celery_app inspect ping`
- `langfuse-server`: `curl -f http://localhost:3000/api/public/health` (stub; exact path confirmed by PLAN-F-013)
- `clickhouse`: `clickhouse-client --query "SELECT 1"` (stub)

Startup order (depends_on with `condition: service_healthy`):
```
postgres (healthy) ─────────────────────────────┐
redis (healthy) ──────────────────────────────── ├─► stokai-app (healthy)
langfuse-db (healthy) → langfuse-server (healthy) ┘        │
                                                            └─► stokai-worker
                                                            └─► stokai-scheduler
```

### Dockerfile Stages

```dockerfile
# Stage 1: builder
FROM python:3.14-slim AS builder
WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Stage 2: runtime
FROM python:3.14-slim AS runtime
WORKDIR /app
COPY --from=builder /install /usr/local
COPY src/ ./src/
COPY agents/ ./agents/
COPY alembic.ini ./
# No secrets baked in; all config injected via env vars
ENV PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

stokai-worker and stokai-scheduler use the same image with `command:` overrides in compose:
```yaml
stokai-worker:
  image: stokai-app:latest
  command: ["celery", "-A", "src.celery_app", "worker", "--loglevel=info"]

stokai-scheduler:
  image: stokai-app:latest
  command: ["celery", "-A", "src.celery_app", "beat", "--loglevel=info"]
```

### .env.example Variables

```
# Application
DATABASE_URL=
REDIS_URL=
SECRET_KEY=
ACCESS_TOKEN_EXPIRE_MINUTES=
REFRESH_TOKEN_EXPIRE_DAYS=

# Vault / Config
PROVIDER_REGISTRY_CONFIG_PATH=

# AI providers
ANTHROPIC_API_KEY=

# Langfuse observability
LANGFUSE_HOST=
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=

# Memory decay
MEMORY_DECAY_HALF_LIFE_DAYS=
MEMORY_DECAY_FLOOR=

# Scheduling
MORNING_BRIEF_DEFAULT_TIME=

# Postgres (for compose init)
POSTGRES_USER=
POSTGRES_PASSWORD=
POSTGRES_DB=

# Langfuse DB (for compose init) — LANGFUSE section populated by PLAN-F-013
LANGFUSE_DB_USER=
LANGFUSE_DB_PASSWORD=
LANGFUSE_DB_NAME=

# ClickHouse — LANGFUSE section populated by PLAN-F-013
CLICKHOUSE_USER=
CLICKHOUSE_PASSWORD=
```

### VaultProvider Interface (verified, not implemented here)

PLAN-F-022 delivers this protocol. This plan verifies the contract is honoured:

```python
class VaultProvider(Protocol):
    def get_secret(self, key: str) -> str: ...

class EnvVaultProvider:
    """MVP implementation — reads from os.environ. No Azure SDK import."""
    def get_secret(self, key: str) -> str:
        value = os.environ.get(key)
        if value is None:
            raise MissingConfigError(key)
        return value
```

`azure_vault_provider.py` must exist only in `src/providers/vault/` and must not be imported
anywhere in the default code path. The static analysis test (TASK-005) verifies this.

### ProviderRegistry Config Swap (verified, not implemented here)

PLAN-F-002 delivers `provider_config.yaml` loading via `PROVIDER_REGISTRY_CONFIG_PATH`. The
AC-003 verification test (TASK-004) swaps `PriceProvider` by editing one line in
`tests/fixtures/provider_config_stub.yaml` — zero source changes permitted.

## Implementation Tasks

### TASK-001: Docker Compose file and Dockerfile
**Complexity**: M | **TDD**: true
**Files**:
- `docker-compose.yml`
- `docker-compose.override.yml`
- `Dockerfile`
- `Makefile`

Write failing tests first that assert the structural contract of these files, then produce the
files to make the tests pass.

The `docker-compose.yml` defines exactly eight services: `stokai-app`, `stokai-worker`,
`stokai-scheduler`, `postgres`, `redis`, `langfuse-server`, `langfuse-db`, `clickhouse`. Every
service must have: `image` or `build` key, `healthcheck`, `depends_on` with
`condition: service_healthy` where applicable, and `env_file: [.env]` (no inline env values).
Service `stokai-app` exposes port 8000; `stokai-worker` and `stokai-scheduler` share the same
built image via `image:` reference with different `command:` overrides. Langfuse-related services
carry `# LANGFUSE — populated by PLAN-F-013` comments on every field that PLAN-F-013 must fill.

`docker-compose.override.yml` adds bind-mount of `./src:/app/src` and `./agents:/app/agents`
for stokai-app so code changes are visible without a rebuild. Exposes ports for debugger (5678)
and Celery Flower (5555).

The `Dockerfile` is a two-stage build: `builder` installs Python dependencies;
`runtime` copies the install prefix and application source. No secrets or hardcoded values.

The `Makefile` provides: `make up` (docker compose up -d --build), `make down` (docker compose
down -v), `make logs` (docker compose logs -f), `make shell` (exec into stokai-app),
`make deploy-prompts` (placeholder for Langfuse prompt publish, to be wired by PLAN-F-013).

**Tests to write first (TDD)**:
- `tests/static/test_compose_structure.py::test_all_required_services_present` — parse
  `docker-compose.yml` with PyYAML and assert services list == expected eight-element set
- `tests/static/test_compose_structure.py::test_all_services_have_healthcheck` — assert every
  service entry has a `healthcheck` key
- `tests/static/test_compose_structure.py::test_no_inline_env_values` — assert no service has
  an inline `environment:` block that contains a value (only `env_file:` is allowed)
- `tests/static/test_compose_structure.py::test_langfuse_services_have_placeholder_comments` —
  assert langfuse-server, langfuse-db, clickhouse services each contain the PLAN-F-013 marker
- `tests/static/test_compose_structure.py::test_dockerfile_has_no_secret_instructions` — scan
  `Dockerfile` for ENV or ARG lines that contain key names matching `PASSWORD|SECRET|KEY|TOKEN`

**Acceptance criteria covered**: AC-001 (compose file exists and is structurally valid), AC-004 (all required services present)

---

### TASK-002: .env.example and .gitignore
**Complexity**: S | **TDD**: false
**Files**:
- `.env.example`
- `.gitignore` (create or append)

Create `.env.example` at the project root containing all variable names listed in the Component
Design section above — with no values. Group variables by subsystem with comment headers.
Ensure `.gitignore` contains `.env` and `.env.*` (except `.env.example`) so secrets are never
committed. Verify `git check-ignore .env` would return a match.

The static analysis test in TASK-005 will validate that every variable referenced in
`src/config/` (once PLAN-F-022 produces it) has a corresponding entry in `.env.example`.
For now, the test uses the variable list from the requirements spec as the ground truth.

**Acceptance criteria covered**: AC-005 (enables env-var-only config; .env.example committed)

---

### TASK-003: Azure isolation verification test
**Complexity**: S | **TDD**: false
**Files**:
- `tests/static/test_no_azure_in_default_path.py`

Write a pytest test that:
1. Recursively collects all `.py` files under `src/` (excluding `src/providers/vault/azure_vault_provider.py`).
2. For each file, asserts that neither `azure` nor `azure-identity` nor `azure-keyvault` appear in the file text (case-insensitive import lines only).
3. Asserts that `src/providers/vault/azure_vault_provider.py` itself does NOT appear in any `__init__.py` or module-level import in `src/`.

This test does not require a running application. It fails fast if any Azure SDK import
accidentally enters the default code path. It passes immediately on a greenfield `src/` directory
and continues to pass as source grows — enforcing the invariant stated in architecture P-10 and
decision D6.

**Acceptance criteria covered**: AC-002 (no Azure SDK in default code path)

---

### TASK-004: Provider swap integration test (AC-003 verification)
**Complexity**: M | **TDD**: true
**Files**:
- `tests/fixtures/provider_config_stub.yaml`
- `tests/fixtures/provider_config_stub_swapped.yaml`
- `tests/integration/test_provider_swap_config_only.py`

This task verifies the AC-003 contract delivered by PLAN-F-002 (ProviderRegistry). It does not
implement ProviderRegistry — it writes the test that will fail until PLAN-F-002 is executed.

Create two YAML fixture files:
- `provider_config_stub.yaml`: maps `price_provider` to `StubPriceProviderA`
- `provider_config_stub_swapped.yaml`: maps `price_provider` to `StubPriceProviderB` (only this
  one line differs)

Both `StubPriceProviderA` and `StubPriceProviderB` are minimal in-test implementations of the
`PriceProvider` protocol — defined inline in the test module, not in `src/`.

Write tests:
- `test_provider_swap_config_only::test_registry_loads_provider_a` — instantiate ProviderRegistry
  with `provider_config_stub.yaml`; call `registry.get(PriceProvider)`; assert result is instance
  of `StubPriceProviderA`
- `test_provider_swap_config_only::test_swap_to_provider_b_requires_no_source_change` —
  instantiate ProviderRegistry with `provider_config_stub_swapped.yaml`; assert result is instance
  of `StubPriceProviderB`; assert the number of source files under `src/` that were touched
  during this test is zero (measured by recording `src/` mtimes before and after)
- `test_provider_swap_config_only::test_hot_reload_via_listen_notify` — mark as
  `@pytest.mark.integration`; requires a running postgres fixture; sends NOTIFY on the
  ProviderRegistry channel; asserts the registry reflects the updated config within 2 seconds

**Tests to write first (TDD)**:
- All three tests above are the TDD artefact — they are written before PLAN-F-002 is executed,
  and they drive the interface contract that PLAN-F-002 must satisfy.

**Acceptance criteria covered**: AC-003 (provider swap = config only, zero source changes)

---

### TASK-005: Static analysis hardcoded-config test (Bandit + grep)
**Complexity**: M | **TDD**: true
**Files**:
- `tests/static/test_no_hardcoded_config.py`
- `pyproject.toml` or `setup.cfg` (Bandit config section, append only)

Write failing tests that encode the static analysis rules, then ensure the rules produce clean
results on the current (initially empty) `src/` tree. As `src/` grows, the tests continue to
act as a ratchet.

Bandit rules enforced:
- B105 (hardcoded password string)
- B106 (hardcoded password function argument)
- B107 (hardcoded password in function default)

Custom grep rules (each is a separate parameterised test case):
- No `localhost` literal in `src/` Python files (allowed in `tests/` and `.env.example`)
- No `127.0.0.1` literal in `src/` Python files
- No `postgres://` or `postgresql://` URI scheme literal in `src/` Python files
- No `redis://` URI scheme literal in `src/` Python files
- No `http://localhost` in `src/` Python files
- No hardcoded JWT secret pattern (`SECRET_KEY\s*=\s*["'][^$]`) in `src/`

Tests implementation strategy:
- `test_bandit_scan_passes` — subprocess call to `bandit -r src/ -t B105,B106,B107 --exit-zero
  -f json`; parse JSON output; assert `results` list is empty
- `test_no_hardcoded_literals[{pattern}]` — parameterised with the grep patterns above;
  use Python `re` to scan all `.py` files under `src/`; assert zero matches

Configure Bandit in `pyproject.toml`:
```toml
[tool.bandit]
targets = ["src"]
tests = ["B105", "B106", "B107"]
skips = []
```

**Tests to write first (TDD)**:
- Write `test_bandit_scan_passes` and all `test_no_hardcoded_literals` parameterised cases first
- On a clean `src/` directory they pass immediately (no files to fail on)
- They become the enforcement net as PLAN-F-022, PLAN-F-024, PLAN-F-002, and other plans add
  source files

**Acceptance criteria covered**: AC-005 (zero hardcoded connection strings, credentials, or
env-specific values in src/)

---

### TASK-006: CI smoke test (docker-compose-up on Docker-only runner)
**Complexity**: M | **TDD**: true
**Files**:
- `tests/smoke/test_docker_compose_up.py`
- `tests/smoke/__init__.py`

Write a pytest smoke test that can be executed by a CI runner that has only Docker installed
(no Python application dependencies need to be installed on the runner itself — the test
orchestrates containers).

Test strategy:
- Use `subprocess` to call `docker compose up -d --build --wait` with a timeout of 300 seconds
- Poll `GET http://localhost:8000/health` every 5 seconds until HTTP 200 or timeout
- Assert HTTP 200 within 300 seconds (5 minutes — the ≤ 5-minute target from the requirement)
- Assert `docker compose ps --format json` reports all services as `running` / `healthy`
- On teardown: `docker compose down -v` (always, even on failure)

Additional assertions:
- `test_app_accessible_at_localhost` — HTTP GET `http://localhost:8000/health` returns 200
- `test_all_services_healthy` — parse `docker compose ps` JSON output; assert every service has
  `State == "running"` and `Health == "healthy"` (or `""` for services without healthcheck)
- `test_startup_within_five_minutes` — assert elapsed time from `compose up` to all-healthy
  is less than 300 seconds
- `test_no_azure_calls_during_startup` — assert application logs (captured via
  `docker compose logs stokai-app`) contain no lines matching `azure` (case-insensitive)

Mark all tests in this module with `@pytest.mark.smoke`. Gate this mark in CI to only run on
Docker-only runners via `pytest -m smoke`.

**Tests to write first (TDD)**:
- Write the full test module before the docker-compose.yml is complete — tests will fail
  (`subprocess` call returns non-zero) until TASK-001 produces a valid compose file. This is
  the TDD red phase. The tests define the contract; TASK-001 makes them green.

**Acceptance criteria covered**: AC-001 (docker compose up, all services start, app accessible
at localhost within 5 minutes), AC-002 (no Azure calls during startup confirmed via log scan),
AC-004 (all required services healthy)

## Acceptance Criteria Coverage

| AC | Description | Covered by |
|----|-------------|-----------|
| AC-001 | `docker compose up` on clean machine → all services start, app accessible at localhost; CI smoke test on Docker-only runner | TASK-001 (compose file), TASK-006 (smoke test) |
| AC-002 | All services running → full stack operates without ANY Azure-specific service dependency | TASK-003 (import isolation test), TASK-006 (log scan during smoke test) |
| AC-003 | New PriceProvider → swapping requires only one config entry change; zero service/agent/workflow file changes | TASK-004 (provider swap integration test) |
| AC-004 | docker-compose.yml includes all required services: app, PostgreSQL (TimescaleDB + pgvector), Redis, Langfuse server, Langfuse DB, ClickHouse, Celery worker | TASK-001 (compose structure), TASK-001 TDD test `test_all_required_services_present` |
| AC-005 | Application starts → all config from env vars; no hardcoded connection strings, credentials, or env-specific values (Bandit + grep) | TASK-002 (.env.example), TASK-005 (static analysis tests) |

## Definition of Done

- [ ] All six tasks complete
- [ ] `docker-compose.yml` passes structural tests: eight services present, all have healthchecks,
  no inline env values, Langfuse placeholder comments present
- [ ] `Dockerfile` passes no-secret-instruction test
- [ ] `.env.example` committed; `.env` in `.gitignore`
- [ ] `tests/static/test_no_azure_in_default_path.py` passes on current `src/` tree (zero Azure
  imports in default path)
- [ ] `tests/integration/test_provider_swap_config_only.py` — unit cases pass (integration case
  requires PLAN-F-002 to be executed first; marked `@pytest.mark.integration`)
- [ ] `tests/static/test_no_hardcoded_config.py` passes: zero Bandit B105/B106/B107 findings,
  zero grep hits for hardcoded URI patterns in `src/`
- [ ] `tests/smoke/test_docker_compose_up.py` passes on a Docker-only CI runner within 300 seconds
- [ ] All five acceptance criteria verified and ticked in REQ-N-008
- [ ] No TODO/FIXME in produced infrastructure files or test files
- [ ] dev-code-review run; Critical/High findings resolved
- [ ] `make up` works from a clean clone after `cp .env.example .env` and filling credentials

## Open Questions Inherited

| # | Question | Resolution |
|---|----------|-----------|
| 1 | C-005: If Azure OpenAI is used for classification, the system has a hard Azure dependency in the default configuration — violating this portability NFR. | Resolved 2026-05-31 by decision C-005: LLM provider is configurable per agent YAML (multi-provider architecture). Default is Anthropic-only (Haiku 4.5, Sonnet 4.6, Opus 4.7). No Azure OpenAI in MVP. No Azure SDK import in default code path. The `azure_vault_provider.py` file exists only as an optional, non-imported module in `src/providers/vault/`. TASK-003 enforces this at test time. |
| 2 | Docker Compose vs Kubernetes for production scale (REQ-N-008 open question from requirements index) | Non-blocking for this plan. Docker Compose is the confirmed MVP target (D6). Kubernetes manifests are post-MVP. 12-factor compliance of the application layer means container orchestrator is a deployment concern only. |

## Risks and Notes

- **PLAN-F-013 soft dependency**: The Langfuse service block in `docker-compose.yml` is
  scaffolded with placeholder comments. When PLAN-F-013 executes, it will fill in exact image
  tags, volume configs, and startup commands. The executor of PLAN-F-013 must be aware that
  `docker-compose.yml` already contains the service stubs — it should patch those stubs, not
  add duplicate entries. The `# LANGFUSE — populated by PLAN-F-013` comment markers are the
  merge contract.

- **TimescaleDB + pgvector init**: The `postgres` service needs a custom init SQL script
  (`docker/postgres/init.sql`) that runs `CREATE EXTENSION IF NOT EXISTS timescaledb;` and
  `CREATE EXTENSION IF NOT EXISTS vector;`. This init script must be volume-mounted as
  `/docker-entrypoint-initdb.d/init.sql`. The TimescaleDB image is
  `timescale/timescaledb-ha:pg16` (includes pgvector). TASK-001 must use this image, not vanilla
  `postgres:16`.

- **Smoke test runner requirements**: The CI job that runs `@pytest.mark.smoke` must have Docker
  Engine installed and the docker socket accessible. It must not have the Python app dependencies
  installed (the point is to test the containerised deployment). Use a dedicated CI job definition
  with `image: docker:latest` or equivalent.

- **Static analysis test on greenfield src/**: TASK-003, TASK-005 tests pass trivially on an
  empty `src/` directory. Their value accumulates as other plans add source files. They must be
  added to the CI pipeline's `test` stage so they run on every PR, not just at this NFR's
  execution time.

- **Provider swap test timing**: TASK-004's `test_hot_reload_via_listen_notify` depends on
  PLAN-F-002 and requires a running PostgreSQL instance. It is marked `@pytest.mark.integration`
  and will be skipped in the default test run until PLAN-F-002 is executed. The unit portion
  of TASK-004 (config loading without hot-reload) can run immediately and will fail until PLAN-F-002
  delivers the `ProviderRegistry` class — this is the intentional TDD red state.

- **Bandit version pinning**: Pin `bandit` version in `requirements-dev.txt` to avoid false
  positives from version drift. Recommended: `bandit>=1.8,<2.0`.

- **Docker image layer caching**: The `Dockerfile` must place `COPY requirements.txt` before
  `COPY src/` so that `pip install` is cached across builds that only change application code.
  Failing to do this will make the CI smoke test significantly slower.
