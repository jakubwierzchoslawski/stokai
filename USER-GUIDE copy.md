# StokAI — User Guide

StokAI is a geopolitical intelligence platform for retail investors. It compresses 20–40 minutes
of manual news analysis into a 90-second interactive briefing by combining reactive event
processing (Mode A) with deliberative AI workflows (Mode B).

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Prerequisites](#prerequisites)
3. [First-Time Setup](#first-time-setup)
4. [Running the Full Stack (Docker)](#running-the-full-stack-docker)
5. [Running the Backend Manually](#running-the-backend-manually)
6. [Running the Frontend](#running-the-frontend)
7. [Database Migrations](#database-migrations)
8. [Seeding Initial Data](#seeding-initial-data)
9. [Service URLs & Ports](#service-urls--ports)
10. [Environment Variables Reference](#environment-variables-reference)
11. [Makefile Cheat-Sheet](#makefile-cheat-sheet)
12. [Testing](#testing)
13. [Observability](#observability)
14. [Key Concepts](#key-concepts)
15. [Backend Module Reference](#backend-module-reference)

---

## Architecture Overview

```
External sources (GDELT, Finnhub, FMP, FRED, SEC EDGAR)
        │
        ▼
Ingestion / Cache layer
        │
        ▼
PostgreSQL (TimescaleDB + pgvector)  ←  Redis (cache + Celery broker)
        │
   ┌────┴────┐
   │         │
Mode A     Mode B
(reactive  (agentic
 pipeline)  workflows)
   │         │
   └────┬────┘
        ▼
  FastAPI REST + WebSocket API
        │
        ▼
  React 18 SPA (served by FastAPI static files)
```

**Mode A** — Reactive pipeline, 12 deterministic steps, < 90 s latency, ~$0.05/event.
Runs on every incoming geopolitical event: classify → extract tickers → compute exposure →
embed → find analogies → generate alert → evaluate rules → dispatch.

**Mode B** — Deliberative LangGraph workflows, 2–5 min, $0.50–$2.00/report.
Five workflows: Morning Brief, On-Demand Analysis, Watchlist Scan, Earnings Risk Brief,
Event Deep-Dive. Powered by nine named Claude agents (Sonnet + Opus).

---

## Prerequisites

| Tool | Minimum version | Notes |
|------|----------------|-------|
| Docker Desktop | 24+ | Compose v2 included |
| Python | 3.12 | Only needed for manual backend runs |
| Node.js | 20+ | Only needed for frontend tests |
| make | any | Optional; commands also listed raw |

API keys required before first run:

- `ANTHROPIC_API_KEY` — Claude models (primary reasoning)
- `OPENAI_API_KEY` — OpenAI embeddings (`text-embedding-3-small`)
- `LANGFUSE_SECRET_KEY` + `LANGFUSE_PUBLIC_KEY` — self-hosted Langfuse (see below)

Optional (features degrade gracefully if absent):

- `FINNHUB_API_KEY` — live price data
- `FMP_API_KEY` — Financial Modeling Prep
- `SENDGRID_API_KEY` — email alert delivery
- `ACLED_API_KEY` — alternative event seeding source

---

## First-Time Setup

```bash
# 1. Copy the environment template
cp .env.example .env

# 2. Open .env and replace every REPLACE_ME value:
#    - POSTGRES_PASSWORD
#    - ANTHROPIC_API_KEY
#    - OPENAI_API_KEY
#    - LANGFUSE_SECRET_KEY / LANGFUSE_PUBLIC_KEY / LANGFUSE_DB_PASSWORD
#    - JWT_SECRET_KEY / JWT_REFRESH_SECRET_KEY   (min 32 random chars each)
#    - SEED_ADMIN_EMAIL / SEED_ADMIN_PASSWORD     (initial admin account)

# 3. Generate strong JWT secrets quickly:
python -c "import secrets; print(secrets.token_hex(32))"
```

> **Never commit `.env` to source control.** It is already in `.gitignore`.

---

## Running the Full Stack (Docker)

```bash
# Build images and start all services (postgres, redis, langfuse, api, worker, beat)
make up
# or
docker compose up -d --build

# Follow logs across all services
make logs
# or follow a single service
docker compose logs -f api

# Show running containers
make ps

# Stop everything
make down
```

The first `up` takes 2–4 minutes while Docker builds the Python image and pulls service
images. Subsequent starts are faster because layers are cached.

---

## Running the Backend Manually

Use this when you want hot-reload during development without rebuilding Docker images.

**Requirements:** PostgreSQL, Redis, and Langfuse must be reachable. The easiest way is to
start only the infrastructure services from Docker and run the API process on the host:

```bash
# Start only infrastructure
docker compose up -d postgres redis langfuse-db clickhouse langfuse-server

# Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux

# Install dependencies
pip install -e ".[dev]"

# Point the app at localhost services (override DATABASE_URL and REDIS_URL)
# Either edit .env or export inline:
set DATABASE_URL=postgresql+asyncpg://stokai:<password>@localhost:5432/stokai
set REDIS_URL=redis://localhost:6379/0
set LANGFUSE_HOST=http://localhost:3000

# Run with auto-reload
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

**Celery workers** (required for Mode B workflows and scheduled jobs):

```bash
# In a second terminal (same venv, same env vars)
celery -A src.config.celery_app worker --loglevel=info

# In a third terminal — periodic task scheduler
celery -A src.config.celery_app beat --scheduler celery.schedulers.PersistentScheduler
```

---

## Running the Frontend

The frontend is a React 18 SPA (`src/frontend/`). In production it is served as static files
by the FastAPI backend.

**For development**, a Vite or similar bundler config has not been included in the repo yet.
The current `package.json` (at project root) only contains test scripts. To work on frontend
components:

```bash
# Install dependencies
npm install

# Run component tests
npm test
# or in watch mode
npm run test:watch
```

To serve the SPA locally during development, the recommended approach is to run the full
Docker stack — FastAPI will serve the built frontend from its static file mount. Check
`docker-compose.override.yml` for the source-mount path if you want live edits reflected.

---

## Database Migrations

Migrations are managed with Alembic. Always run them after starting the stack or after pulling
new code that includes schema changes.

```bash
# Run all pending migrations (in Docker)
make migrate
# or
docker compose exec api alembic upgrade head

# Create a new migration (when you change SQLAlchemy models)
docker compose exec api alembic revision --autogenerate -m "describe_your_change"

# Roll back one step
docker compose exec api alembic downgrade -1
```

---

## Seeding Initial Data

On first run you need an admin user and optional historical event data.

```bash
# Open a shell inside the API container
make shell-api
# or
docker compose exec api bash

# Inside the container — run the seed script
python scripts/seed.py

# Optionally seed historical GDELT events (can take several minutes)
# Configure SEEDING_PROVIDER, GDELT_START_DATE, SEEDING_BATCH_SIZE in .env first
python scripts/seed_events.py
```

The admin credentials are taken from `SEED_ADMIN_EMAIL` and `SEED_ADMIN_PASSWORD` in `.env`.

---

## Service URLs & Ports

| Service | URL | Notes |
|---------|-----|-------|
| FastAPI (REST + WebSocket) | http://localhost:8000 | Main application API |
| API interactive docs | http://localhost:8000/docs | Swagger UI |
| API health check | http://localhost:8000/health | No auth required |
| Langfuse observability UI | http://localhost:3000 | AI traces, prompt versions |
| PostgreSQL | localhost:5432 | Direct DB access (local dev only) |
| Redis | localhost:6379 | Cache / Celery broker (local dev only) |

---

## Environment Variables Reference

All variables are documented in `.env.example`. Key groups:

| Group | Variables | Required |
|-------|-----------|----------|
| Database | `DATABASE_URL`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | Yes |
| Redis | `REDIS_URL` | Yes |
| AI providers | `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` | Yes |
| Langfuse | `LANGFUSE_SECRET_KEY`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_HOST`, `LANGFUSE_DB_*` | Yes |
| JWT auth | `JWT_SECRET_KEY`, `JWT_REFRESH_SECRET_KEY` | Yes |
| Seed account | `SEED_ADMIN_EMAIL`, `SEED_ADMIN_PASSWORD` | First run |
| Financial data | `FINNHUB_API_KEY`, `FMP_API_KEY` | No (optional) |
| Email alerts | `SENDGRID_API_KEY`, `SENDGRID_FROM_EMAIL` | No (optional) |
| Event seeding | `SEEDING_PROVIDER`, `GDELT_START_DATE`, `ACLED_API_KEY` | No (optional) |

---

## Makefile Cheat-Sheet

```
make up               Build images and start all services (detached)
make down             Stop and remove containers
make logs             Stream logs from all services
make ps               Show container status
make migrate          Run Alembic migrations inside the api container
make shell-api        Open bash inside the api container
make test             Run unit tests (excludes integration)
make test-integration Run integration tests only
make scan-azure       Check for forbidden Azure SDK imports
make help             Print this list
```

---

## Testing

```bash
# Unit tests (fast, no external deps)
make test
# or directly:
pytest tests/ -v --ignore=tests/integration

# Integration tests (requires running postgres + redis)
make test-integration
# or:
pytest tests/integration/ -v -m integration

# Frontend component tests
npm test
```

Load tests live in `tests/load/` and are run separately with Locust or similar.

---

## Observability

Langfuse is bundled in the Docker stack at http://localhost:3000.

It captures:
- **Traces** — every Mode A pipeline run and Mode B workflow invocation
- **Prompt versions** — each prompt template promoted through Draft → Staging → Production
- **Evaluation scores** — Tier 1 online LLM-as-Judge scores attached to every generation
- **Cost tracking** — per-trace token spend

Log into Langfuse with the credentials you set in `LANGFUSE_DB_*` and the generated
`LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY`.

Application logs are structured JSON at the level set by `LOG_LEVEL` (default `INFO`).
Stream them with `make logs` or `docker compose logs -f <service>`.

---

## Key Concepts

**Agent registry** — YAML files in `agents/` define every LangGraph agent (name, model,
tools, memory config). They are loaded at startup and validated before the API accepts
traffic.

**Prompt management** — Prompt templates live in `prompts/` as Markdown files. The
`PromptVersionResolver` first checks Langfuse for a promoted version; if none is found it
falls back to the file on disk. This lets prompts be updated in production without a
redeploy.

**Multi-tenancy** — Every database entity carries a `tenant_id`. The JWT middleware
extracts the tenant from the token and injects it into every query. Do not share API
tokens across tenants.

**Scoring DSL** — Custom indicator formulas are parsed by the scoring DSL engine in
`src/scoring/`. The Indicator Builder UI in `src/frontend/components/indicator-builder/`
provides a visual canvas for building and previewing formulas live.

**Intelligence Map** — The home screen renders a MapLibre GL globe with Supercluster
event clustering. Events pulse in real-time via WebSocket. Clicking a cluster reveals
individual events; clicking an event opens the progressive-disclosure detail panel.

---

## Backend Module Reference

All modules live under `src/`. Every module follows constructor-based dependency injection
and reads configuration exclusively from `src/config/settings.py` (pydantic `BaseSettings`).
No module reads env vars directly.

---

### `admin` — Administrative Operations

Manages data source configuration, runtime health counters, monthly budget tracking, feature
flags, and cache management.

Key sub-packages: `data_sources/`, `health/`, `system/`, `tasks/`.

| Configurable | Default | Notes |
|---|---|---|
| `ADMIN_ALERT_EMAIL` | `""` | Recipient for budget threshold alerts; empty = skip |
| Feature flags | DB-driven | Stored in `feature_flag` table; toggled at runtime without restart |

Health counters track per-source API call count and cost, keyed by `(source_id, cost_tier)`.
Feature flags are mutable at runtime — no redeploy needed.

---

### `ai` — AI Orchestration Hub

Owns everything AI-related: agent YAML registry, 16 tool families, five LangGraph workflows,
four-layer memory system, prompt management pipeline, evaluation harness, and Langfuse
observability integration. All agent definitions are loaded and validated at startup
(fail-fast before the API accepts traffic).

Key sub-packages: `registry/`, `tools/`, `workflows/`, `memory/`, `prompts/`, `evaluation/`,
`guards/`, `qa/`, `embedding/`, `observability/`, `cost/`.

| Configurable | Default | Notes |
|---|---|---|
| `AGENTS_DIR` | `"agents"` | Path to agent YAML definitions |
| `PROMPTS_DIR` | `"prompts"` | Path to prompt template files |
| `ANTHROPIC_API_KEY` | — | Required; Claude Sonnet 4.6 / Opus |
| `OPENAI_API_KEY` | — | Required; `text-embedding-3-small` |
| `LANGFUSE_PROMPTS_ENABLED` | `True` | Publish prompt versions to Langfuse on deploy |
| `CANARY_TRAFFIC_PCT` | `10` | Percentage of LLM calls routed to canary prompt version (0–100) |
| `LANGFUSE_SECRET_KEY` / `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_HOST` | — | Observability; optional but strongly recommended |
| `EVIDENCE_GATE_MIN_COUNT` | `3` | Min evidence observations before a semantic fact is committed to memory |
| `SEMANTIC_DECAY_MONTHS` | `6` | Months after which unconfirmed semantic facts decay |

The 15 canonical prompt role IDs (`exposure_analyst`, `historical_context`,
`anomaly_detector`, `recommendation_synthesizer`, `narrative_writer`, `morning_brief_analyst`,
`watchlist_analyst`, `earnings_analyst`, `qa_analyst`, `recommendation_judge`,
`factuality_judge`, `calibration_judge`, `event_classifier`, `ticker_extractor`,
`sentiment_analyzer`) are the stable keys used across the agent registry, CLI, and Langfuse.

---

### `alerts` — Alert Rules & Dispatch

Evaluates pipeline events against user-defined alert rules, applies anti-fatigue filters
(dedup window + daily cap + quiet hours), enforces budget ceilings, generates
LLM-written alert narratives (Claude Sonnet 4.6), and delivers via SendGrid.

Key sub-packages: `services/`, `integrations/`, `api/`, `repositories/`.

| Configurable | Default | Notes |
|---|---|---|
| `SENDGRID_API_KEY` | `""` | Email delivery; alerts disabled when blank |
| `SENDGRID_FROM_EMAIL` | `""` | Sender address; required when alerts enabled |
| `_DEFAULT_DAILY_PUSH_LIMIT` | `20` | Max push alerts per user per day |
| `_DEFAULT_DEDUP_WINDOW_MINUTES` | `60` | Same-event dedup window |
| Quiet hours | user-settable | Start/end time configurable per user via `AntiFatigueSettingsService` |

All anti-fatigue defaults can be overridden per-user through the API (`PUT /api/v1/anti-fatigue`).

---

### `api` — HTTP Transport Layer

FastAPI app factory: wires all domain routers, registers JWT middleware, rate limiting
(slowapi), and the AI disclaimer injection middleware. Exposes REST + WebSocket endpoints.

Key sub-packages: `auth/`, `middleware/`, `routers/`, `v1/`, `websocket/`,
`progressive_disclosure/`, `security/`.

Registered route prefixes:

| Prefix | Purpose |
|---|---|
| `/api/v1/auth` | Login, signup, token refresh |
| `/api/v1/portfolio` | Portfolio and position CRUD |
| `/api/v1/watchlist` | Watchlist management |
| `/api/v1/onboarding` | User onboarding flow |
| `/api/v1/admin` | Source config, system ops, cost monitor |
| `/api/v1/events` | Geo events and memos |
| `/api/v1/alert*` | Alert rules and anti-fatigue settings |
| `/api/v1/qa` | Q&A chat interface |
| `/api/v1/briefs` | Morning and earnings briefs |
| `/api/v1/compliance` | Audit track record |
| `/api/v1/evaluation` | Evaluation framework |
| `/api/v1/hil` | Human-in-the-loop admin queue |

| Configurable | Default | Notes |
|---|---|---|
| `JWT_SECRET_KEY` | — | Required; signs access tokens (HS256) |
| `JWT_REFRESH_SECRET_KEY` | — | Required; signs refresh tokens |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | `15` | Short-lived access token TTL |
| `JWT_REFRESH_TOKEN_EXPIRE_DAYS` | `7` | Refresh token TTL |
| `BCRYPT_ROUNDS` | `12` | Password hashing cost factor |
| `DISCLAIMER_SAMPLE_SIZE_THRESHOLD` | `5` | Inject AI disclaimer when sample_size < this |
| `DISCLAIMER_TEXT` | (see `.env.example`) | Text injected by disclaimer middleware |
| `DISCLAIMER_MIDDLEWARE_PATH_PREFIXES` | `[]` | Path prefixes where disclaimer middleware applies |

---

### `briefs` — Brief Content Management

Read/filter/feedback service for morning briefs and earnings risk briefs. Handles tenant
isolation, brief listing, detail retrieval, and user feedback collection.

Key files: `services/brief_service.py`, `repositories/`, `schemas/`.

| Configurable | Default | Notes |
|---|---|---|
| `MORNING_BRIEF_DEFAULT_SEND_TIME` | `"06:00"` | Default dispatch time (UTC, HH:MM) |
| `SENDGRID_MORNING_BRIEF_TEMPLATE_ID` | `""` | SendGrid dynamic template ID for HTML email |
| `EARNINGS_BRIEF_COST_CEILING_USD` | `1.50` | Per-brief cost cap; workflow aborted if exceeded |
| `EARNINGS_BRIEF_HIL_DEADLINE_TIME` | `"17:45"` | Hard deadline (UTC) for human-in-the-loop review |
| `EARNINGS_BRIEF_HARD_TIMEOUT_SECONDS` | `600` | Maximum workflow wall-clock time |

---

### `cli` — Prompt Operations CLI

Command-line tool for managing prompt labels in production: inspect current versions,
promote a SHA to production, and roll back to a prior label.

Key file: `cli/prompts_cli.py`.

Commands: `cmd_status`, `cmd_promote`, `cmd_rollback`.

| Configurable | Default | Notes |
|---|---|---|
| `PROMPTS_ROOT` | `<repo_root>/prompts` | Hardcoded relative path; override by running CLI from repo root |
| `LANGFUSE_HOST` | from env | Required for label persistence |
| `DATABASE_URL` | from env | Required for persisting label changes |

---

### `compliance` — Audit & Auditability

Provides read-only compliance APIs and a Celery beat task (runs hourly) that checks
episodic completeness over a rolling lookback window. Queries `workflow_run`,
`agent_invocation`, and `ai_recommendation` tables.

Key files: `compliance_check_service.py`, `compliance_tasks.py`, `compliance_router.py`.

| Configurable | Default | Notes |
|---|---|---|
| `COMPLIANCE_CHECK_LOOKBACK_DAYS` | `90` | Rolling window for episodic coverage check |

---

### `config` — Centralized Settings

Single pydantic `BaseSettings` class that reads and validates every environment variable.
All other modules import `from src.config.settings import settings` — nothing else reads
`os.environ` directly. See [Environment Variables Reference](#environment-variables-reference)
for the full list.

Key file: `config/settings.py`.

---

### `data_providers` — External Event Adapters

Protocol-based adapters for historical event sources. GDELT adapter covers 1979 to present;
ACLED adapter covers African conflict data. A `CredentialsResolver` handles per-provider
API key lookup.

Key files: `gdelt_historical_adapter.py`, `acled_historical_adapter.py`,
`credentials_resolver.py`.

| Configurable | Default | Notes |
|---|---|---|
| `SEEDING_PROVIDER` | `"gdelt"` | `"gdelt"` or `"acled"` |
| `GDELT_START_DATE` | `1979-01-01` | ISO date; start of GDELT ingestion range |
| `ACLED_API_KEY` | `""` | Required only when `SEEDING_PROVIDER=acled` |
| `FINNHUB_API_KEY` | `""` | Optional; live price feed |
| `FMP_API_KEY` | `""` | Optional; Financial Modeling Prep |

---

### `db` — Migrations & Seeds

Houses Alembic migration files (`db/migrations/versions/`, 41+ revisions) and seed scripts.
No application logic; purely schema versioning.

| Configurable | Notes |
|---|---|
| `DATABASE_URL` | Read by Alembic at migration time |
| `alembic.ini` | Controls migration logging and script location |

---

### `events` — Mode A Reactive Pipeline

The core 12-step pipeline that processes every incoming geopolitical event end-to-end in
under 90 seconds. Each step is an isolated module in `steps/`. The `PipelineExecutor`
orchestrates them, accumulates per-step cost, and surfaces a `PipelineResult`.

Steps in order: `persist_raw_event` → `classify_event` → `extract_tickers` →
`embed_event` → `compute_exposure_map` → `persist_event_record` →
`find_historical_analogies` → `generate_alert_text` → `evaluate_alert_rules` →
`dispatch_or_log_silent` → `enqueue_deep_dive` → `return_pipeline_result`.

Key files: `pipeline_executor.py`, `steps/`, `cost_accumulator.py`, `models.py`.

| Configurable | Default | Notes |
|---|---|---|
| `ANALOGY_K` | `5` | Number of historical analogies surfaced per event (1–50) |
| Cost ceiling | inherited | `EARNINGS_BRIEF_COST_CEILING_USD` and per-step limits enforced by guards |

All LLM calls inside steps use Claude Sonnet 4.6 via the injected `ai` module client.

---

### `ingestion` — Three-Tier Cache Cascade

Implements a cache-or-fetch pattern: Redis hot cache → PostgreSQL persistent cache →
external provider. Manages TTL contracts, write-time TTL enforcement, per-source sliding-
window rate limiting, event-driven cache invalidation, and cold-start seeding orchestration.

Key files: `cache_or_fetch.py`, `redis_cache.py`, `pg_cache_repository.py`,
`ttl_contract.py`, `rate_limiter.py`, `invalidation.py`, `cold_start/`.

| Configurable | Default | Notes |
|---|---|---|
| `PRICE_BAR_TTL_SECONDS` | `900` | Delayed / free-tier price data (15 min) |
| `PRICE_BAR_REALTIME_TTL_S` | `5` | Real-time price feed |
| `FUNDAMENTALS_TTL_S` | `86400` | Company fundamentals (24 h) |
| `NEWS_EVENT_TTL_S` | `3600` | News events (1 h) |
| `MACRO_TTL_S` | `86400` | Macro indicators (24 h) |
| `HISTORICAL_PRICE_BAR_TTL_S` | `None` | Immutable; never evicted |
| `EVENT_EMBEDDING_TTL_S` | `None` | Immutable; never evicted |
| `COMPANY_SCORE_TTL_S` | `None` | Event-driven invalidation only |
| `SEEDING_BATCH_SIZE` | `500` | Events per cold-start seeding batch |
| `EMBEDDING_CONCURRENCY` | `5` | Parallel OpenAI embedding calls per sub-batch |

---

### `markets` — Source Routing Registry

In-process singleton registry that maps `(market_id, interface_type, role)` tuples to live
source configurations. Loaded from `source_config` + `market_source_binding` DB tables.
Supports atomic hot-reload (replaces the entire dict in one step) so routing changes take
effect without restart.

Key files: `registry.py`, `registry_refresher.py`.

No tunable parameters — entirely DB-driven. To change routing, update the
`market_source_binding` table and trigger a registry refresh via the admin API.

---

### `portfolio` — Portfolio & Watchlist

Domain services for portfolio CRUD, position management, watchlist management, user
onboarding flows, and CSV portfolio import. All data access goes through injected
repository interfaces.

Key files: `portfolio_service.py`, `watchlist_service.py`, `onboarding_service.py`,
`csv_import_service.py`.

No environment-level configurables; all behavior is driven by the injected repositories
and the tenant derived from the JWT.

---

### `scoring` — Company Scoring Pipeline

Nine-step pipeline: load indicators → parse DSL expressions → evaluate AST → normalize
scores → apply geo modifier → compute peer benchmarks → persist scores → detect score
changes → emit invalidation events. Powers the Indicator Builder UI.

Key sub-packages: `dsl/` (tokenizer → parser → AST → validator), `evaluator/`,
`normalization/` (min-max, percentile, z-score), `repositories/`, `benchmark_engine.py`,
`geo_modifier.py`.

| Configurable | Notes |
|---|---|
| Indicator DSL expressions | Stored in the `indicator` DB table; edited via Indicator Builder UI |
| Normalization strategy | Stored per-indicator in DB (`min_max` / `percentile` / `z_score`) |
| Peer cohort definition | Stored per scoring profile in DB |
| Geo modifier weights | Maintained in DB; updated by `geo_modifier_worker` Celery task |

No hardcoded thresholds — all scoring parameters live in the database and are editable
through the UI or admin API.

---

### `storage` — Repository Layer

Central data-access layer implementing the Repository pattern over all 30+ DB entities.
Provides interface definitions (`interfaces/`) and SQLAlchemy 2.0 async concrete
implementations. All ORM models are in `models/`; all repository contracts in
`repositories/`.

Notable entities: `User`, `Portfolio`, `Position`, `WatchlistItem`, `GeoEvent`,
`EventExposure`, `AiRecommendation`, `Brief`, `WorkflowRun`, `CostRecord`,
`FeatureFlag`, `IngestionJob`, `PromptPublication`, `RefreshToken`.

| Configurable | Default | Notes |
|---|---|---|
| `DATABASE_URL` | — | Required asyncpg DSN |
| `DATABASE_POOL_SIZE` | `10` | SQLAlchemy connection pool size |
| `DATABASE_MAX_OVERFLOW` | `5` | Extra connections above pool_size |
