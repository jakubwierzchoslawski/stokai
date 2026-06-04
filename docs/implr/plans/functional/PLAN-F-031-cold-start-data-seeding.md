---
plan_id: PLAN-F-031
slug: cold-start-data-seeding
title: Cold-Start Historical Data Seeding
linked_requirement: REQ-F-031
type: functional
status: done
blocked_reason:
complexity: L
tdd_required: true
linked_nfrs:
  - { id: REQ-N-007, reason: "Seeding must run via docker compose up with no cloud dependencies — all downloads and DB writes are local-first" }
  - { id: REQ-N-011, reason: "Historical embeddings and price bars carry infinite TTL (immutable past rule); seeding state table uses finite TTL for in-progress markers only" }
dependencies: []
executed_at: 2026-06-03T00:00:00Z
reviewed_at:
review_id:
created_at: 2026-06-02T00:00:00Z
updated_at: 2026-06-02T00:00:00Z
---

# PLAN-F-031 — Cold-Start Historical Data Seeding

## Linked Requirement
**REQ-F-031** — Cold-Start Historical Data Seeding
Status: approved | Jira: —

## Objective

Build a one-time, resumable seeding pipeline that populates the production database with the full GDELT historical event archive (1979 to configured end date), pairs each event with historical OHLCV price data to compute `price_change_t1d`, generates OpenAI `text-embedding-3-small` embeddings for every event, and builds the HNSW index on `event_embedding` — all before system go-live. The pipeline is admin-triggered (management command or Celery task), idempotent at the row level, and resumable on failure via a `seeding_checkpoint` DB table. An ACLED fallback adapter with identical output shape is included so the operator can switch providers without touching business logic.

## Architecture Context

This plan touches three architecture layers:

- **Layer 1 / `data_providers` module** — two new `HistoricalEventProvider` implementations: `GdeltHistoricalAdapter` and `AcledHistoricalAdapter`. These are the only classes that call external APIs or download remote files (Architecture Principle 1).
- **Layer 2 / `ingestion` module** — the seeding orchestrator (`SeedingOrchestrator`), state tracker (`SeedingCheckpointRepository`), OHLCV fetcher service, and the management command / Celery task entrypoint. Cold-start lives in `ingestion` per Architecture section 5.
- **Layer 3 / `storage` module** — one new migration adds the `seeding_checkpoint` table. All DB writes go through repository classes.
- **Layer 4 / `historical` module (read path)** — after seeding, the HNSW index on `event_embedding` is available to the `find_historical_analogies` step of Mode A (Architecture section 6, step 7) and to the `historical_context_agent` Tool Library.

Key architectural rules applied:
- GDELT parser sits behind a `HistoricalEventProvider` protocol (Architecture Principle 1 / SOLID Open/Closed). Switching to ACLED is a config/environment variable change.
- Seeding checkpoint state lives in a DB table, never in-memory or in a file, so resumability survives container restarts (12-factor, REQ-N-007).
- Embedding calls reuse the same `EmbeddingService` abstraction used by Mode A step 6 — no parallel embedding interface (Architecture Principle 1 / DI).
- Historical data rows carry `ttl = NULL` (infinite) per Architecture Principle 2 and REQ-N-011.

## Applied NFR Constraints

| NFR | Constraint | Impact on this plan |
|-----|-----------|---------------------|
| REQ-N-007 | Full system runs via `docker compose up`; no cloud-managed services | GDELT bulk CSV download fetched via HTTP (no SDK); seeding checkpoint in PostgreSQL; no Azure Blob Storage dependency |
| REQ-N-011 | Historical data has infinite TTL; never re-fetched | `geo_event`, `event_embedding`, `price_bar`, and `event_exposure` rows seeded by this pipeline carry `ttl = NULL`; the idempotency check treats existing rows as permanent |

## Component Design

### New Components

```
Module: data_providers (src/data_providers/)
  ├── HistoricalEventProvider       — protocol/interface (ABC)
  │     fetch_batches(start_date, end_date, batch_size) -> Iterator[list[RawHistoricalEvent]]
  ├── GdeltHistoricalAdapter        — downloads GDELT master CSV list, streams event files
  └── AcledHistoricalAdapter        — calls ACLED export API, emits same RawHistoricalEvent shape

Module: ingestion (src/ingestion/cold_start/)
  ├── seeding_orchestrator.py       — SeedingOrchestrator: top-level coordinator
  │     orchestrate(config: SeedingConfig) -> SeedingResult
  ├── seeding_checkpoint_repository.py
  │     — SeedingCheckpointRepository: reads/writes seeding_checkpoint rows
  ├── event_parser.py               — parse_raw_event(raw: RawHistoricalEvent) -> GeoEventCreate
  ├── price_seeder.py               — PriceSeeder: fetches historical OHLCV, computes price_change_t1d
  ├── embedding_batch_processor.py  — EmbeddingBatchProcessor: rate-limited OpenAI calls, retry
  ├── hnsw_index_builder.py         — HnswIndexBuilder: issues REINDEX CONCURRENTLY on event_embedding
  ├── seeding_validator.py          — SeedingValidator: post-seeding query health check
  └── management/
        seed_command.py             — CLI entrypoint: python -m src.ingestion.cold_start.management.seed_command
        seed_task.py                — Celery task wrapper (admin-triggerable from Admin panel)

Module: storage (src/storage/)
  └── migrations/
        XXXX_add_seeding_checkpoint.py   — Alembic migration

Shared types (src/ingestion/cold_start/types.py):
  ├── RawHistoricalEvent            — Pydantic model (provider-agnostic)
  ├── SeedingConfig                 — provider, date_range, batch_size, embedding_concurrency
  ├── SeedingResult                 — events_seeded, embeddings_created, exposures_created, errors
  └── CheckpointState               — enum: pending | in_progress | done | failed
```

### Modified Components

| File | Change | Reason |
|------|--------|--------|
| `src/data_providers/__init__.py` | Export `HistoricalEventProvider`, adapters | Register new provider interface |
| `src/config/settings.py` | Add `GDELT_START_DATE`, `SEEDING_PROVIDER`, `SEEDING_BATCH_SIZE`, `EMBEDDING_CONCURRENCY` | Config-driven seeding without code changes |
| `docker-compose.yml` | No change needed — seeding runs inside existing `worker` container | Confirmed portable |

### Interfaces and Contracts

```python
# src/data_providers/historical_event_provider.py
from abc import ABC, abstractmethod
from collections.abc import Iterator
from datetime import date

class HistoricalEventProvider(ABC):
    @abstractmethod
    def fetch_batches(
        self,
        start_date: date,
        end_date: date,
        batch_size: int = 500,
    ) -> Iterator[list[RawHistoricalEvent]]:
        """Yield successive batches of raw historical events in ascending date order."""
        ...

    @abstractmethod
    def provider_name(self) -> str:
        """Return canonical provider identifier, e.g. 'gdelt' or 'acled'."""
        ...
```

```python
# src/ingestion/cold_start/types.py
from pydantic import BaseModel
from datetime import date, datetime
from enum import Enum
from uuid import UUID

class RawHistoricalEvent(BaseModel):
    external_id: str          # GDELT GlobalEventID or ACLED event_id_no
    occurred_at: datetime
    title: str
    summary: str
    lat: float | None
    lon: float | None
    geo_regions: list[str]
    cameo_code: str | None
    intensity_raw: float      # normalized to 1–5 by parser
    sentiment_raw: float      # normalized to [-1,1] by parser
    source_provider: str      # 'gdelt' | 'acled'
    raw_payload: dict         # original row for audit

class CheckpointState(str, Enum):
    pending = "pending"
    in_progress = "in_progress"
    done = "done"
    failed = "failed"

class SeedingConfig(BaseModel):
    provider: str             # 'gdelt' | 'acled'
    start_date: date
    end_date: date
    batch_size: int = 500
    embedding_concurrency: int = 5   # parallel OpenAI calls per batch
    dry_run: bool = False

class SeedingResult(BaseModel):
    events_seeded: int
    events_skipped: int       # already existed (idempotent)
    embeddings_created: int
    exposures_created: int
    errors: list[str]
```

```python
# src/storage/repositories/seeding_checkpoint_repository.py
from abc import ABC, abstractmethod
from uuid import UUID
from datetime import date

class ISeedingCheckpointRepository(ABC):
    @abstractmethod
    async def get_checkpoint(self, batch_key: str) -> CheckpointRow | None: ...
    @abstractmethod
    async def upsert_checkpoint(self, batch_key: str, state: CheckpointState, meta: dict) -> None: ...
    @abstractmethod
    async def list_pending_batches(self, start_date: date, end_date: date) -> list[str]: ...
```

### DB Schema Addition

```sql
-- seeding_checkpoint table (Alembic migration)
CREATE TABLE seeding_checkpoint (
    batch_key        TEXT PRIMARY KEY,   -- e.g. 'gdelt:1979-01-01:1979-01-31'
    state            TEXT NOT NULL,       -- pending | in_progress | done | failed
    events_seeded    INT  NOT NULL DEFAULT 0,
    embeddings_done  INT  NOT NULL DEFAULT 0,
    error_detail     TEXT,
    started_at       TIMESTAMPTZ,
    completed_at     TIMESTAMPTZ,
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

## Implementation Tasks

### TASK-001: HistoricalEventProvider protocol and shared types · S/no-TDD · src/data_providers/historical_event_provider.py,src/ingestion/cold_start/types.py

Define the `HistoricalEventProvider` ABC with `fetch_batches` and `provider_name` abstract methods. Define all shared Pydantic types (`RawHistoricalEvent`, `SeedingConfig`, `SeedingResult`, `CheckpointState`). No business logic in this task — pure contracts.

Export from `src/data_providers/__init__.py`.

**AC covered**: enables AC-001, AC-003

---

### TASK-002: Alembic migration — seeding_checkpoint table · S/no-TDD · src/storage/migrations/XXXX_add_seeding_checkpoint.py

Write an Alembic `upgrade` migration that creates the `seeding_checkpoint` table (columns: `batch_key TEXT PK`, `state TEXT NOT NULL`, `events_seeded INT`, `embeddings_done INT`, `error_detail TEXT`, `started_at TIMESTAMPTZ`, `completed_at TIMESTAMPTZ`, `updated_at TIMESTAMPTZ`). Include `downgrade` that drops the table.

**AC covered**: enables AC-002

---

### TASK-003: SeedingCheckpointRepository · M/TDD · src/storage/repositories/seeding_checkpoint_repository.py,tests/unit/storage/test_seeding_checkpoint_repository.py,tests/integration/storage/test_seeding_checkpoint_repository_integration.py

Implement `ISeedingCheckpointRepository` interface and its SQLAlchemy 2.0 async concrete class `SeedingCheckpointRepository`.

Methods: `get_checkpoint(batch_key)`, `upsert_checkpoint(batch_key, state, meta)`, `list_pending_batches(start_date, end_date)`.

**Tests to write first (TDD)**:
- `get_checkpoint` returns `None` when no row exists for the given key
- `upsert_checkpoint` creates a new row with state `in_progress`
- `upsert_checkpoint` updates an existing row without creating a duplicate
- `list_pending_batches` returns only batch keys whose state is not `done`
- Integration test: round-trip upsert against a test PostgreSQL DB

**AC covered**: enables AC-002

---

### TASK-004: GdeltHistoricalAdapter · L/TDD · src/data_providers/gdelt_historical_adapter.py,tests/unit/data_providers/test_gdelt_historical_adapter.py

Implement `HistoricalEventProvider` for GDELT.

Behavior:
1. Fetch the GDELT master file list (`http://data.gdeltproject.org/gdeltv2/masterfilelist.txt` for GDELTv2 or the v1 list for pre-2015 data) via `httpx` async client.
2. Filter file URLs to the configured `start_date`–`end_date` range.
3. For each batch window (monthly by default): download the ZIP, extract the CSV, parse rows into `RawHistoricalEvent` — mapping `GLOBALEVENTID` → `external_id`, `SQLDATE` → `occurred_at`, `Actor1Name`/`Actor2Name`/`EventCode` → `title`/`cameo_code`, `GoldsteinScale` → `intensity_raw`, `AvgTone` → `sentiment_raw`.
4. Yield each batch; do not hold all batches in memory.

Map `GoldsteinScale` [-10, +10] → intensity [1, 5]. Map `AvgTone` → sentiment [-1, 1].

`provider_name()` returns `'gdelt'`.

**Tests to write first (TDD)**:
- `fetch_batches` with a mock HTTP client returns expected `RawHistoricalEvent` objects for a single sample CSV
- Goldstein scale -10 maps to intensity 1; +10 maps to intensity 5; 0 maps to intensity 3
- AvgTone -100 maps to sentiment -1.0; +100 maps to +1.0
- Date filter: files outside `start_date`–`end_date` are skipped
- HTTP 404 on a file raises a domain error (not a raw `httpx` error)
- Malformed CSV rows are logged and skipped; valid rows in the same file are still returned

**AC covered**: AC-001, AC-003

---

### TASK-005: AcledHistoricalAdapter · M/TDD · src/data_providers/acled_historical_adapter.py,tests/unit/data_providers/test_acled_historical_adapter.py

Implement `HistoricalEventProvider` for ACLED (fallback, AC-003).

Behavior: call ACLED export REST API (`https://api.acleddata.com/acled/read`) with API key from `ACLED_API_KEY` env var. Paginate using `page` param. Map ACLED fields to `RawHistoricalEvent`:
- `data_id` → `external_id`
- `event_date` → `occurred_at`
- `notes` → `summary`, `event_type` → `title`
- `latitude`/`longitude` → `lat`/`lon`
- `fatalities` scaled → `intensity_raw` (1–5 proportional to fatalities capped at 1000)
- hardcoded `cameo_code = None` (ACLED does not use CAMEO)

`provider_name()` returns `'acled'`.

**Tests to write first (TDD)**:
- `fetch_batches` with a mock HTTP client maps ACLED response fields to `RawHistoricalEvent` correctly
- Fatalities = 0 → intensity 1; fatalities ≥ 1000 → intensity 5
- `provider_name()` returns `'acled'`
- Missing `latitude` produces `lat = None` without raising
- Pagination: when API returns `count == page_size`, the adapter fetches the next page

**AC covered**: AC-003

---

### TASK-006: EventParser — raw event to GeoEvent domain model · M/TDD · src/ingestion/cold_start/event_parser.py,tests/unit/ingestion/cold_start/test_event_parser.py

Implement `parse_raw_event(raw: RawHistoricalEvent, tenant_id: UUID) -> GeoEventCreate`.

Behavior:
- Normalize `intensity_raw` to `int` in [1, 5] (clamp).
- Normalize `sentiment_raw` to `float` in [-1.0, 1.0] (clamp).
- Derive `category[]` from `cameo_code` using a CAMEO root-code → category map (e.g., `01x` → `VERBAL_COOPERATION`, `19x` → `ARMED_CONFLICT`). Unknown codes map to `UNKNOWN`.
- Set `detected_at = datetime.utcnow()` (seeding time).
- Set `source_provider = raw.source_provider`.
- `geo_regions` and `affected_sectors` passed through from `raw.geo_regions`; `affected_sectors` defaults to `[]` (sector classification is a Mode A LLM step, not available in cold-start).
- `event_id` is a deterministic UUID5 derived from `(source_provider, external_id)` to ensure idempotency across re-runs.

**Tests to write first (TDD)**:
- CAMEO code `190` maps to category `ARMED_CONFLICT`
- CAMEO code `010` maps to category `VERBAL_COOPERATION`
- Unknown CAMEO code maps to `UNKNOWN`
- `intensity_raw = 7.0` is clamped to `5`
- `intensity_raw = -2.0` is clamped to `1`
- Deterministic `event_id`: same `(source_provider, external_id)` → same UUID across two calls
- Different `external_id` → different UUID

**AC covered**: AC-001, AC-002

---

### TASK-007: PriceSeeder — historical OHLCV fetch and price_change_t1d computation · M/TDD · src/ingestion/cold_start/price_seeder.py,tests/unit/ingestion/cold_start/test_price_seeder.py

Implement `PriceSeeder` which, given a list of seeded `event_id`s and their `occurred_at` dates, fetches `price_bar` rows for tracked companies from the DB (already seeded via Finnhub/FMP) and computes `price_change_t1d = (close_t1 - close_t0) / close_t0` for each `(event, company)` pair within the event's `geo_regions`/`affected_sectors` exposure.

If `price_bar` for `T+1` does not exist for a company (e.g., weekend/holiday), find the next available trading day up to `T+5`. If still absent, log a warning and skip without error.

Write each `(event_id, company_id, price_change_t1d)` to `event_exposure` via the repository, using INSERT ... ON CONFLICT DO NOTHING for idempotency.

**Tests to write first (TDD)**:
- `compute_price_change_t1d(close_t0=100.0, close_t1=105.0)` returns `0.05`
- `compute_price_change_t1d(close_t0=100.0, close_t1=95.0)` returns `-0.05`
- Missing T+1 price bar: finder advances to T+2, then T+3 (up to T+5); returns first found
- Missing price bar through T+5: returns `None` and logs warning; no exception raised
- Repository `upsert_event_exposure` called with ON CONFLICT DO NOTHING semantics verified via mock

**AC covered**: AC-005

---

### TASK-008: EmbeddingBatchProcessor — rate-limited OpenAI embedding generation · M/TDD · src/ingestion/cold_start/embedding_batch_processor.py,tests/unit/ingestion/cold_start/test_embedding_batch_processor.py

Implement `EmbeddingBatchProcessor` that accepts a list of `(event_id, text)` pairs and calls OpenAI `text-embedding-3-small` via the shared `EmbeddingService` abstraction (used by Mode A step 6).

Behavior:
- Process events in sub-batches of `embedding_concurrency` (default 5) using `asyncio.gather`.
- Apply exponential-backoff retry (max 3 attempts) on `openai.RateLimitError` and `openai.APIError`.
- Write each `(event_id, embedding VECTOR(1536))` to `event_embedding` via repository; INSERT ... ON CONFLICT DO NOTHING.
- Skip events that already have an `event_embedding` row (idempotency).
- Log progress every 1,000 embeddings (count, elapsed, estimated remaining).

**Tests to write first (TDD)**:
- Happy path: `process_batch` calls `EmbeddingService.embed` once per event text, writes to repository
- Already-embedded event_id: repository check returns existing; `embed` is not called
- `RateLimitError` on first attempt: retried; succeeds on second attempt
- Three consecutive `RateLimitError`s: raises `EmbeddingBatchError` after max retries
- Concurrency: with `concurrency=3` and 6 events, `embed` is called in two parallel batches of 3 (verified with asyncio mock timing)

**AC covered**: AC-001, AC-002, AC-004

---

### TASK-009: HnswIndexBuilder — HNSW index build and rebuild · S/no-TDD · src/ingestion/cold_start/hnsw_index_builder.py

Implement `HnswIndexBuilder` with a single async method `rebuild(session)`.

Behavior:
- Check if the HNSW index `event_embedding_hnsw_idx` exists via `pg_indexes` system view.
- If absent: `CREATE INDEX CONCURRENTLY event_embedding_hnsw_idx ON event_embedding USING hnsw (embedding vector_cosine_ops)`.
- If present: `REINDEX INDEX CONCURRENTLY event_embedding_hnsw_idx`.
- Log start and completion with row count.
- This is a DDL operation; it must run outside a transaction (`AUTOCOMMIT` mode on the connection).

**AC covered**: AC-004

---

### TASK-010: SeedingValidator — post-seeding health check · S/no-TDD · src/ingestion/cold_start/seeding_validator.py

Implement `SeedingValidator.validate(session) -> ValidationReport`.

Checks:
1. `SELECT COUNT(*) FROM geo_event WHERE source_provider IN ('gdelt', 'acled')` — must be > 0.
2. `SELECT COUNT(*) FROM event_embedding` — must equal geo_event count above.
3. Execute a test pgvector cosine query (`SELECT ... FROM event_embedding ORDER BY embedding <=> $1 LIMIT 1`) using a zero vector — must return in under 2 seconds.
4. `SELECT COUNT(*) FROM event_exposure WHERE price_change_t1d IS NOT NULL` — must be > 0.

Returns a `ValidationReport` with per-check pass/fail and timing. Raises `SeedingValidationError` if any check fails.

**AC covered**: AC-001, AC-004, AC-005

---

### TASK-011: SeedingOrchestrator — top-level coordinator · L/TDD · src/ingestion/cold_start/seeding_orchestrator.py,tests/unit/ingestion/cold_start/test_seeding_orchestrator.py,tests/integration/ingestion/cold_start/test_seeding_orchestrator_integration.py

Implement `SeedingOrchestrator.orchestrate(config: SeedingConfig) -> SeedingResult`.

Sequence:
1. Resolve provider from `config.provider` → inject correct `HistoricalEventProvider` implementation.
2. Partition the date range into monthly batches; load checkpoint state for each batch.
3. For each non-`done` batch:
   a. Mark batch `in_progress` in `seeding_checkpoint`.
   b. Fetch raw events from provider (one batch at a time, streaming).
   c. Parse each raw event via `EventParser`.
   d. Insert `geo_event` rows via `GeoEventRepository`; skip duplicates via `event_id` conflict.
   e. Mark batch `done` in `seeding_checkpoint` with count.
4. After all batches: run `PriceSeeder` for newly inserted events.
5. Run `EmbeddingBatchProcessor` for events lacking embeddings.
6. Run `HnswIndexBuilder.rebuild()`.
7. Run `SeedingValidator.validate()`.
8. Return `SeedingResult`.

On any unhandled exception in a batch: mark batch `failed` with `error_detail`; continue to next batch (partial-failure tolerance). Raise `SeedingOrchestrationError` at end if any batch failed.

**Tests to write first (TDD)**:
- Full happy-path integration: mock provider yields 2 batches → events inserted → embeddings created → index built → validator passes → result has correct counts
- Idempotency: run orchestrator twice; second run skips all `done` batches; event count unchanged
- Partial failure: batch 2 raises provider error → marked `failed`; batch 1 and 3 complete → `SeedingOrchestrationError` raised at end with summary; batches 1 and 3 are `done` in checkpoint
- Provider selection: `config.provider = 'acled'` → `AcledHistoricalAdapter` injected (not GDELT)
- `dry_run = True`: no DB writes performed; log output contains "dry run" message

**AC covered**: AC-001, AC-002, AC-003, AC-004, AC-005

---

### TASK-012: Management command and Celery task entrypoint · S/no-TDD · src/ingestion/cold_start/management/seed_command.py,src/ingestion/cold_start/management/seed_task.py

Implement two entrypoints:

**`seed_command.py`** — `python -m src.ingestion.cold_start.management.seed_command` CLI:
- Parse args: `--provider [gdelt|acled]`, `--start-date`, `--end-date`, `--dry-run`.
- Load config from env vars (`GDELT_START_DATE`, `SEEDING_PROVIDER`, etc.) with CLI args as overrides.
- Instantiate `SeedingOrchestrator` with injected dependencies (DB session factory, correct adapter).
- Print `SeedingResult` summary on completion; exit code 1 on `SeedingOrchestrationError`.

**`seed_task.py`** — Celery task:
- Task name: `ingestion.cold_start.run_seeding`.
- Admin-triggerable from the Admin panel (System Operations section per Architecture section 11).
- Calls `SeedingOrchestrator.orchestrate(config)` and stores `SeedingResult` as Celery task result.
- Accepts same config params as CLI.

**AC covered**: enables AC-001, AC-002, AC-003

---

### TASK-013: Settings additions and .env.example update · XS/no-TDD · src/config/settings.py,.env.example

Add to `settings.py` (Pydantic Settings):
- `SEEDING_PROVIDER: str = "gdelt"` — `'gdelt'` or `'acled'`
- `GDELT_START_DATE: date = date(1979, 1, 1)`
- `SEEDING_BATCH_SIZE: int = 500`
- `EMBEDDING_CONCURRENCY: int = 5`
- `ACLED_API_KEY: str | None = None` — required only when `SEEDING_PROVIDER = 'acled'`

Add corresponding entries to `.env.example` with inline comments explaining valid values.

**AC covered**: enables AC-001, AC-003

---

## Acceptance Criteria Coverage

- AC-001: Given the cold-start seeding script is run, it ingests GDELT events from the configured start date, generates embeddings, and stores `event_embedding` rows; a subsequent analogy search returns at least one result with valid `price_change_t1d` → TASK-004, TASK-006, TASK-007, TASK-008, TASK-010, TASK-011, TASK-012
- AC-002: Given the script is run a second time, no duplicate `geo_event` or `event_embedding` rows are created → TASK-003, TASK-006, TASK-008, TASK-011
- AC-003: Given GDELT license is denied, the script can be configured to use ACLED with equivalent output format → TASK-001, TASK-005, TASK-011, TASK-012, TASK-013
- AC-004: Given seeding is complete, the HNSW index is built and pgvector cosine search returns results in under 2 seconds → TASK-008, TASK-009, TASK-010
- AC-005: Given historical price data exists in `price_bar`, `event_exposure.price_change_t1d` is populated for each (event, company) pair → TASK-007, TASK-010, TASK-011

## Acceptance Notes

The GDELT commercial license status (Open Question 1 from REQ-F-031) is unresolved. This plan mitigates the risk by implementing both adapters behind the same interface and making provider selection a runtime environment variable. If the license is denied before go-live, the operator sets `SEEDING_PROVIDER=acled` and `ACLED_API_KEY=<key>` — no code change required. Coverage and schema parity between providers must be manually verified before go-live.

The HNSW index build (TASK-009) uses `CREATE INDEX CONCURRENTLY` and must run outside a SQLAlchemy transaction. The `seed_command` must not wrap the index step in the ambient session transaction; it must acquire a raw `asyncpg` connection in autocommit mode.

## Open Questions Inherited

| # | Question | Resolution |
|---|----------|-----------|
| 1 | Has the GDELT commercial license been verified for MVP production use? If denied, what is ACLED's coverage scope for geopolitical events? | Mitigated by building both adapters (TASK-004, TASK-005) behind the `HistoricalEventProvider` interface and making provider selection a `SEEDING_PROVIDER` env var. Full resolution requires legal/business confirmation before go-live. |

## Risks and Notes

- **GDELT file volume**: The full GDELTv2 archive (2015–present) contains thousands of ZIP files. Monthly batch partitioning with checkpoint resume makes this tolerable, but the first full run may take several hours. Plan for an overnight seed window before go-live.
- **OpenAI rate limits**: The Embeddings API free tier has tight RPM limits. `EMBEDDING_CONCURRENCY=5` is the safe default; operators may reduce it to 1 for strict rate environments. The exponential backoff in TASK-008 handles transient throttling.
- **price_bar dependency**: TASK-007 (`PriceSeeder`) requires that `price_bar` rows for tracked companies already exist for the seeded date range. This data must be loaded separately (Finnhub/FMP historical price pull), which is out of scope for this plan but is a deployment prerequisite.
- **CAMEO code coverage**: The CAMEO mapping in TASK-006 covers root codes only (first two digits). Finer-grained category classification is deferred to Mode A's LLM classify step. Cold-start events will have broad categories, which is acceptable for analogy search but means `affected_sectors` will be empty until Mode A re-processes.
- **HNSW index build outside transaction**: Failure during index build does not roll back seeded rows. The index build is the last step before validation; if it fails, operators can re-run the orchestrator (checkpoint ensures event/embedding steps are skipped, only the index step re-runs as it is idempotent).
- **Infinite TTL compliance (REQ-N-011)**: All seeded rows must be inserted without a `ttl` value (or with `ttl = NULL`). The `SeedingCheckpointRepository` in-progress markers use `updated_at` timestamps; these are administrative metadata and are not subject to TTL eviction.
