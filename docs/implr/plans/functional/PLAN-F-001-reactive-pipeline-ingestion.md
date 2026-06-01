---
plan_id: PLAN-F-001
slug: reactive-pipeline-ingestion
title: Event Ingestion & Reactive Pipeline (Mode A)
linked_requirement: REQ-F-001
type: functional
status: done
blocked_reason: ""
complexity: XL
tdd_required: true
linked_nfrs:
  - { id: REQ-N-001, reason: "Mode A end-to-end latency target < 90 s; < 30 s for tweet-class events. Per-step timestamp capture and Langfuse trace are mandatory." }
  - { id: REQ-N-003, reason: "Cost target ~$0.05/event enforced by Haiku 4.5 classification and cache-first lookups throughout the pipeline." }
dependencies:
  - { id: PLAN-F-002, reason: "Provider abstraction layer must exist: NewsProvider, SentimentProvider, PriceProvider Protocol interfaces and CacheFirstMixin are consumed directly by ingestion source adapters (TASK-003) and the exposure-scoring step (TASK-006)." }
brainstorm_decisions:
  - decision: Twitter/X ingestion adapter
    options_considered: [Live Free-tier API connection, Stub adapter implementing SocialProvider, Skip entirely]
    chosen: Stub adapter implementing SocialProvider Protocol interface; admin toggle defaults OFF
    rationale: "OQ-1 resolved. C-002 mandates Free API only; do not connect to live API in MVP. Interface must be wired so the toggle can activate it later without code changes."
    decided_at: 2026-05-31T00:00:00Z
  - decision: Classification LLM
    options_considered: [Azure OpenAI GPT-4o-mini, Anthropic Haiku 4.5 only, Multi-provider YAML]
    chosen: Anthropic Haiku 4.5 via multi-provider abstraction (YAML-configured per agent)
    rationale: "OQ-2 / C-005 resolved. Azure OpenAI excluded from MVP (C-005). Multi-provider YAML config enables future addition. Haiku 4.5 chosen for ~$0.01/classify cost target."
    decided_at: 2026-05-31T00:00:00Z
  - decision: Cost per event
    options_considered: [Haiku 4.5 classify + cheap embedding, Sonnet classify + Haiku embed, Full Sonnet pipeline]
    chosen: Haiku 4.5 for classify + confidence synthesis; standard embedding model for embed step; cache-first for all provider calls
    rationale: "OQ-3 / C-001 resolved. Target ~$0.05/event. Breakdown: classify ~$0.01, embed ~$0.01, confidence ~$0.03."
    decided_at: 2026-05-31T00:00:00Z
  - decision: Pipeline execution mechanism
    options_considered: [Synchronous FastAPI background task, Celery worker + Redis broker, Standalone asyncio loop]
    chosen: Celery task on dedicated celery_worker container; Redis 7 as broker and result backend
    rationale: "Aligns with ARCHITECTURE.md §15 docker-compose services. Celery provides retries, per-task visibility, and failure isolation outside the API request path."
    decided_at: 2026-05-31T00:00:00Z
  - decision: Deduplication store
    options_considered: [Redis SETEX fingerprint only, DB unique constraint only, Redis primary + DB secondary]
    chosen: Redis SETEX as primary (fast, TTL-bound); DB unique constraint on raw_events.fingerprint as secondary guard
    rationale: "Redis SETEX gives sub-millisecond dedup with configurable window. DB constraint is safety net for Redis miss (e.g. after Redis flush)."
    decided_at: 2026-05-31T00:00:00Z
executed_at: 2026-06-01T00:00:00Z
reviewed_at:
review_id:
created_at: 2026-05-31T00:00:00Z
updated_at: 2026-05-31T00:00:00Z
---

# PLAN-F-001 — Event Ingestion & Reactive Pipeline (Mode A)

## Linked Requirement
**REQ-F-001** — Event Ingestion & Reactive Pipeline (Mode A)
Status: approved | Jira: (blank)

## Objective
Build the complete Mode A reactive pipeline inside `src/event_pipeline/`. The pipeline is
triggered by four ingestion sources (GDELT HTTP poller, SEC EDGAR poller/webhook, internal
price-anomaly detector, and a stubbed Twitter/X adapter), executes as a Celery task on the
dedicated `celery_worker` container, and runs 13 deterministic ordered steps from raw-event
ingestion through deduplication, parsing, LLM-based classification (Haiku 4.5), pgvector
embedding, portfolio exposure scoring, historical analogy retrieval, confidence synthesis,
routing, record persistence, alert dispatch, and Langfuse trace closure — targeting < 90
seconds end-to-end per event at ~$0.05/event. Failure in any step halts the pipeline, marks
the raw event as `failed` with step name and error detail, and suppresses any partial alert
dispatch.

## Architecture Context
This plan targets `src/event_pipeline/` (ARCHITECTURE.md §4 — Module Map). The pipeline
touches the following layers and modules:

- `src/event_pipeline/ingest/` — four source adapters behind `NewsProvider` / `SocialProvider`
  / `PriceProvider` Protocols from `src/providers/` (PLAN-F-002 dependency).
- `src/event_pipeline/classify/` — Haiku 4.5 LLM call via multi-provider YAML abstraction
  (ARCHITECTURE.md §8 Agent Registry, §11 Provider and Market Abstraction, C-005).
- `src/event_pipeline/score/` — portfolio exposure computation; `inputs_hash` invalidation
  (ARCHITECTURE.md §6 Step 7, P-03 Inputs-Hash Invalidation).
- `src/event_pipeline/embed/` — pgvector 1536-dim embedding generation and ANN similarity
  search (ARCHITECTURE.md §5 Data Architecture, §6 Steps 5 and 8).
- `src/event_pipeline/dispatch/` — confidence routing, alert push via WebSocket + Web Push,
  HIL queue enqueue (ARCHITECTURE.md §6 Steps 10–12, C-003 confidence boundaries).
- `src/db/` — SQLAlchemy 2 models for `raw_events`, `geopolitical_events`, `event_scores`,
  `episodic_memory`, `ai_audit_log`; Alembic migrations (ARCHITECTURE.md §5 Core Schema).
- `src/cache/` — Redis `CacheFirstMixin` for deduplication fingerprint store and per-step
  cache lookups (ARCHITECTURE.md P-02 Cache-First Lookup).
- `src/observability/` — Langfuse client wrapper for trace open/step-span/trace-close
  (ARCHITECTURE.md §12 Observability).

Architecture principles directly enforced:
- **P-01** Provider Abstraction — all source adapters implement typed Protocols; no direct API
  calls from pipeline steps.
- **P-02** Cache-First Lookup — deduplication and exposure score check via Redis before DB.
- **P-03** Inputs-Hash Invalidation — exposure score recomputed only when `inputs_hash`
  changes; previous score record is preserved.
- **P-09** Full AI Lineage — `ai_audit_log` entry written per classify and confidence step
  with prompt SHA, model ID, Langfuse trace ID, confidence.
- **P-10** Portability First — no cloud SDK; Docker Compose is the only runtime target.

## Brainstorm Decisions
**Twitter/X ingestion adapter** — `TwitterStubAdapter` implementing `SocialProvider` Protocol
is wired into the adapter registry. Admin toggle defaults `enabled=false`. The stub raises
`ProviderDisabled` on `get_signals()` calls when toggled off. No live API connection in MVP.

**Classification LLM** — `classify` step calls the multi-provider abstraction (YAML-configured
`classify_agent.yaml`). Default model: `anthropic/claude-haiku-4-5`. Provider-level swap
requires only a YAML edit.

**Cost per event** — Haiku 4.5 for Steps 4 (classify) and 9 (confidence synthesis); standard
`text-embedding-3-small` or equivalent for Step 5. Cache-first lookups prevent redundant
external calls. Target ~$0.05/event.

**Pipeline execution** — Single Celery task `run_pipeline.apply_async(args=[raw_event_id,
tenant_id])`. The task is idempotent: re-queuing an already-`completed` event is a no-op.

**Deduplication** — Redis `SETEX event:dedup:{fingerprint} 1 {ttl_seconds}` as primary gate.
DB unique constraint on `raw_events.fingerprint` as safety net.

## Applied NFR Constraints
| NFR | Constraint | Impact on this plan |
|-----|-----------|---------------------|
| REQ-N-001 | Mode A end-to-end < 90 s; tweet-class < 30 s | `detected_at` set at ingestion; `generated_at` set at Step 13. Langfuse spans per step enable latency auditing. Celery task priority queue separates X-class events (high priority). |
| REQ-N-003 | ~$0.05/event; MVP AI + infra < $100/month | Haiku 4.5 for classify and confidence steps. Cache-first for all provider calls. `CacheFirstMixin` from PLAN-F-002 mandatory for Steps 6–8. |

## Component Design

### New Components
```
src/event_pipeline/
  ├── pipeline_task.py           — Celery task entry point; orchestrates the 13-step executor
  ├── pipeline_executor.py       — PipelineExecutor: sequential step runner, per-step error trap,
  │                                status transition, Langfuse span lifecycle
  ├── pipeline_state.py          — PipelineState: Pydantic model carrying context between steps
  │
  ├── ingest/
  │   ├── base.py                — IngestionAdapter Protocol (abstract interface)
  │   ├── gdelt_adapter.py       — GdeltAdapter: HTTP polling, GDELT event → RawEventPayload
  │   ├── edgar_adapter.py       — EdgarAdapter: SEC EDGAR webhook receiver + poller
  │   ├── price_anomaly_adapter.py — PriceAnomalyAdapter: internal price-feed anomaly trigger
  │   ├── twitter_stub_adapter.py — TwitterStubAdapter: SocialProvider stub; raises ProviderDisabled
  │   └── adapter_registry.py    — AdapterRegistry: maps source enum → IngestionAdapter instance
  │
  ├── steps/
  │   ├── base.py                — PipelineStep Protocol: execute(state) -> PipelineState
  │   ├── s01_ingest.py          — Step 1: route to IngestionAdapter; set detected_at
  │   ├── s02_deduplicate.py     — Step 2: compute fingerprint; Redis SETEX; DB guard
  │   ├── s03_parse.py           — Step 3: extract structured fields from raw_payload
  │   ├── s04_classify.py        — Step 4: Haiku 4.5 LLM call; validate category + intensity
  │   ├── s05_embed.py           — Step 5: generate 1536-dim embedding; upsert geopolitical_events
  │   ├── s06_portfolio_scan.py  — Step 6: identify affected holdings across active portfolios
  │   ├── s07_exposure_score.py  — Step 7: compute per-portfolio score; inputs_hash check
  │   ├── s08_analogy_search.py  — Step 8: pgvector ANN top-K historical analogues
  │   ├── s09_confidence_calc.py — Step 9: composite confidence; Haiku 4.5 synthesis call
  │   ├── s10_routing.py         — Step 10: confidence-threshold routing (C-003)
  │   ├── s11_record.py          — Step 11: write event_scores, ai_audit_log, episodic_memory
  │   ├── s12_dispatch.py        — Step 12: WebSocket push / Web Push / HIL enqueue
  │   └── s13_trace.py           — Step 13: Langfuse trace close; write generated_at
  │
  └── exceptions.py              — PipelineHalt, DuplicateEvent, ClassificationError,
                                   InvalidCategoryError, InvalidIntensityError

src/db/models/
  ├── raw_event.py               — RawEvent ORM model (new)
  └── event_record.py            — EventRecord ORM model (new; geopolitical_events table)

src/db/migrations/
  └── versions/
      └── XXXX_event_pipeline_tables.py  — Alembic migration: raw_events, raw_events.fingerprint
                                            unique index, pipeline_status enum

tests/unit/event_pipeline/
  ├── test_pipeline_executor.py
  ├── test_s02_deduplicate.py
  ├── test_s04_classify.py
  ├── test_s05_embed.py
  ├── test_s06_portfolio_scan.py
  ├── test_s07_exposure_score.py
  ├── test_s08_analogy_search.py
  ├── test_s09_confidence_calc.py
  ├── test_s10_routing.py
  ├── test_s11_record.py
  ├── test_s12_dispatch.py
  └── test_ingest/
      ├── test_gdelt_adapter.py
      ├── test_edgar_adapter.py
      └── test_twitter_stub_adapter.py

tests/integration/event_pipeline/
  └── test_pipeline_end_to_end.py
```

### Modified Components
| File | Change | Reason |
|------|--------|--------|
| `src/db/models/__init__.py` | Export `RawEvent`, `EventRecord` | Make models importable |
| `src/db/migrations/env.py` | Import new models for autogenerate | Alembic migration discovery |
| `docker-compose.yml` | Ensure `celery_worker` service runs `pipeline_task` queue | Celery worker must listen on `event_pipeline` queue |
| `src/config/settings.py` (new) | `DEDUP_TTL_SECONDS`, `PIPELINE_QUEUE`, `CLASSIFY_MODEL_YAML`, `TWITTER_ENABLED` env vars | 12-factor config; validate at startup |

### Interfaces and Contracts

```python
# src/event_pipeline/ingest/base.py
from typing import Protocol
from src.event_pipeline.pipeline_state import RawEventPayload

class IngestionAdapter(Protocol):
    source: str  # matches RawEventSource enum value

    def poll(self) -> list[RawEventPayload]: ...
    # For webhook-driven adapters (EDGAR): called by FastAPI endpoint, not by poll()
    def parse_webhook(self, body: dict) -> RawEventPayload: ...


# src/event_pipeline/steps/base.py
from typing import Protocol
from src.event_pipeline.pipeline_state import PipelineState

class PipelineStep(Protocol):
    step_name: str  # e.g. "s04_classify"

    async def execute(self, state: PipelineState) -> PipelineState: ...


# src/event_pipeline/pipeline_state.py  (Pydantic models)
class RawEventPayload(BaseModel):
    source: RawEventSource          # enum: X_FILTERED_STREAM | GDELT | SEC_EDGAR | PRICE_ANOMALY
    raw_payload: dict
    detected_at: datetime
    tenant_id: UUID

class PipelineState(BaseModel):
    raw_event_id: UUID
    tenant_id: UUID
    payload: RawEventPayload
    fingerprint: str | None = None
    category: EventCategory | None = None   # enum: 6 fixed categories
    intensity: int | None = None            # 1–5
    tickers: list[str] = []
    exposure_map: dict[UUID, float] = {}    # portfolio_id -> score
    embedding: list[float] | None = None
    analogues: list[UUID] = []
    confidence: float | None = None
    route: AlertRoute | None = None         # AUTO_SEND | HIL_QUEUE | BLOCKED
    alert_text: str | None = None
    langfuse_trace_id: str | None = None
    current_step: str = "s01_ingest"
    failed_step: str | None = None
    error_detail: str | None = None
    generated_at: datetime | None = None


# src/event_pipeline/exceptions.py
class PipelineHalt(Exception):
    def __init__(self, step_name: str, detail: str): ...

class DuplicateEvent(PipelineHalt): ...
class ClassificationError(PipelineHalt): ...
class InvalidCategoryError(ClassificationError): ...
class InvalidIntensityError(ClassificationError): ...
```

## Implementation Tasks

### TASK-001: Celery task scaffold, PipelineExecutor, and PipelineState
**Complexity**: L | **TDD**: true
**Files**:
- `src/event_pipeline/pipeline_task.py`
- `src/event_pipeline/pipeline_executor.py`
- `src/event_pipeline/pipeline_state.py`
- `src/event_pipeline/exceptions.py`
- `tests/unit/event_pipeline/test_pipeline_executor.py`

Define `PipelineState` Pydantic model with all fields listed in the Interfaces section.
Define `PipelineStep` Protocol and `PipelineExecutor` class. `PipelineExecutor.__init__`
accepts an ordered `list[PipelineStep]` and a `LangfuseClient`. `PipelineExecutor.run(state)`
iterates steps sequentially; on any exception it catches it, sets `state.failed_step`,
`state.error_detail`, writes `pipeline_status = failed` to the DB via a repository call,
and re-raises `PipelineHalt` to abort remaining steps. A `PipelineHalt` originating from
`DuplicateEvent` must set `pipeline_status = duplicate` instead of `failed`.

Define `run_pipeline` Celery task in `pipeline_task.py`. The task receives `(raw_event_id,
tenant_id)`, constructs the 13-step executor with all step instances injected, and calls
`executor.run(initial_state)`. Task is idempotent: if `raw_event_id` already has
`pipeline_status = completed`, return immediately.

**Tests to write first (TDD)**:
- `test_executor_runs_all_steps_in_order` — mock 13 steps; assert each called once in order
- `test_executor_halts_on_step_failure` — step 4 raises; assert steps 5–13 not called, state has `failed_step="s04_classify"`
- `test_executor_marks_duplicate_status` — step 2 raises `DuplicateEvent`; assert DB write sets `pipeline_status = duplicate`
- `test_executor_does_not_dispatch_on_failure` — step 4 raises; assert dispatch step not called
- `test_pipeline_task_idempotent` — pre-set `pipeline_status = completed`; assert executor not constructed

**Acceptance criteria covered**: AC-001, AC-005

---

### TASK-002: DB models and Alembic migration for raw_events and event_records
**Complexity**: M | **TDD**: true
**Files**:
- `src/db/models/raw_event.py`
- `src/db/models/event_record.py`
- `src/db/models/__init__.py`
- `src/db/migrations/versions/XXXX_event_pipeline_tables.py`
- `tests/unit/event_pipeline/test_db_models.py`

`RawEvent` SQLAlchemy 2 mapped class:
- Columns: `event_id UUID PK`, `tenant_id UUID NOT NULL`, `source TEXT NOT NULL`,
  `raw_payload JSONB`, `detected_at TIMESTAMPTZ`, `pipeline_status TEXT NOT NULL DEFAULT 'pending'`,
  `failed_step TEXT`, `error_detail TEXT`, `fingerprint TEXT`, `created_at TIMESTAMPTZ`
- Unique constraint on `(tenant_id, fingerprint)` for deduplication safety net.
- `pipeline_status` valid values: `pending | running | completed | failed | duplicate`.

`EventRecord` SQLAlchemy 2 mapped class (maps to `geopolitical_events` table):
- Columns as per ARCHITECTURE.md §5 schema: `event_id UUID PK`, `tenant_id UUID FK`,
  `source TEXT`, `detected_at TIMESTAMPTZ`, `category TEXT`, `intensity SMALLINT`,
  `geo_lat FLOAT`, `geo_lon FLOAT`, `embedding VECTOR(1536)`, `raw_payload JSONB`,
  `raw_event_id UUID FK → raw_events`
- `generated_at TIMESTAMPTZ` column added.

Alembic migration creates both tables plus:
- `raw_events.fingerprint` unique index.
- `pipeline_status` CHECK constraint.
- `pgvector` extension `CREATE EXTENSION IF NOT EXISTS vector`.

**Tests to write first (TDD)**:
- `test_raw_event_model_creates_and_queries` — integration test against test DB; create, read, assert fields
- `test_pipeline_status_constraint` — assert invalid status value raises IntegrityError
- `test_fingerprint_unique_constraint` — insert duplicate fingerprint for same tenant; assert UniqueViolation

**Acceptance criteria covered**: AC-001, AC-005, AC-006

---

### TASK-003: Ingestion source adapters (GDELT, EDGAR, PriceAnomaly, TwitterStub)
**Complexity**: L | **TDD**: true
**Files**:
- `src/event_pipeline/ingest/base.py`
- `src/event_pipeline/ingest/gdelt_adapter.py`
- `src/event_pipeline/ingest/edgar_adapter.py`
- `src/event_pipeline/ingest/price_anomaly_adapter.py`
- `src/event_pipeline/ingest/twitter_stub_adapter.py`
- `src/event_pipeline/ingest/adapter_registry.py`
- `tests/unit/event_pipeline/test_ingest/test_gdelt_adapter.py`
- `tests/unit/event_pipeline/test_ingest/test_edgar_adapter.py`
- `tests/unit/event_pipeline/test_ingest/test_twitter_stub_adapter.py`

`IngestionAdapter` Protocol as defined in Interfaces section.

`GdeltAdapter`: HTTP GET to GDELT v2 API (configurable URL env var `GDELT_API_URL`); parses
JSON response into `list[RawEventPayload]`; uses `httpx.AsyncClient`. Wraps HTTP errors in
`ProviderUnavailableError` (from `src/providers/exceptions.py`).

`EdgarAdapter`: accepts SEC EDGAR ATOM feed URL (`EDGAR_FEED_URL`); polling mode parses
ATOM entries into `RawEventPayload(source=SEC_EDGAR, ...)`. Webhook mode: FastAPI endpoint
`POST /api/v1/ingest/edgar` calls `adapter.parse_webhook(body)` directly.

`PriceAnomalyAdapter`: reads anomaly events from an internal Redis list key
`price_anomaly_queue:{tenant_id}` published by the price feed processing logic. Converts
to `RawEventPayload(source=PRICE_ANOMALY, ...)`.

`TwitterStubAdapter`: implements `IngestionAdapter` Protocol. `poll()` raises
`ProviderDisabled("Twitter/X toggle is OFF")`. Admin toggle consulted via
`AdapterRegistry.is_enabled(source)` before calling `poll()`.

`AdapterRegistry`: maps `RawEventSource → IngestionAdapter`. `is_enabled(source) -> bool`
checks the `provider_registry` DB table (via the registry from PLAN-F-002). Hot-reloads on
PostgreSQL LISTEN/NOTIFY via the `ProviderRegistry` from PLAN-F-002.

**Tests to write first (TDD)**:
- `test_gdelt_adapter_parses_valid_response` — mock `httpx` response; assert `RawEventPayload` fields
- `test_gdelt_adapter_wraps_http_error` — mock 503; assert `ProviderUnavailableError` raised
- `test_edgar_adapter_parse_webhook_produces_payload` — sample EDGAR ATOM body; assert fields
- `test_twitter_stub_raises_provider_disabled` — call `poll()`; assert `ProviderDisabled` raised
- `test_adapter_registry_skips_disabled_source` — mock `is_enabled=False`; assert no `poll()` call

**Acceptance criteria covered**: AC-001, AC-002, AC-003

---

### TASK-004: Step 1 (INGEST) and Step 2 (DEDUPLICATE)
**Complexity**: M | **TDD**: true
**Files**:
- `src/event_pipeline/steps/s01_ingest.py`
- `src/event_pipeline/steps/s02_deduplicate.py`
- `tests/unit/event_pipeline/test_s02_deduplicate.py`

`IngestStep` (Step 1): receives `PipelineState` with `payload` already populated by the
Celery task (set at enqueue time from the adapter); sets `state.detected_at` if not already
set; writes `RawEvent` to DB with `pipeline_status = running`; returns updated state.

`DeduplicateStep` (Step 2): computes `fingerprint = sha256(source + raw_payload_canonical_json)`;
checks Redis key `event:dedup:{fingerprint}` (SETEX with TTL from `DEDUP_TTL_SECONDS` env,
default 3600); if key exists: raises `DuplicateEvent(step_name="s02_deduplicate", detail=...)`
which the executor catches to set `pipeline_status = duplicate`; if not present: SET the key
and update `raw_event.fingerprint`; the DB unique constraint provides a secondary guard.

**Tests to write first (TDD)**:
- `test_dedup_step_passes_on_new_event` — Redis miss; assert state.fingerprint set, Redis key written
- `test_dedup_step_raises_on_redis_hit` — Redis hit; assert `DuplicateEvent` raised
- `test_dedup_step_raises_on_db_unique_violation` — Redis miss but DB raises UniqueViolation; assert `DuplicateEvent` raised
- `test_dedup_step_uses_configured_ttl` — assert SETEX called with correct TTL from settings

**Acceptance criteria covered**: AC-006

---

### TASK-005: Step 3 (PARSE) and Step 4 (CLASSIFY) — Haiku 4.5 classification with validation
**Complexity**: M | **TDD**: true
**Files**:
- `src/event_pipeline/steps/s03_parse.py`
- `src/event_pipeline/steps/s04_classify.py`
- `agents/classify_event.yaml`
- `tests/unit/event_pipeline/test_s04_classify.py`

`ParseStep` (Step 3): extracts structured fields from `raw_payload` depending on source
type; populates `state` with geo coordinates, entity text, and normalised event description.
Source-specific parsers are strategy classes implementing a `PayloadParser` Protocol — one
per `RawEventSource` value — selected by `ParseStep` at runtime (Open/Closed).

`ClassifyStep` (Step 4): loads `agents/classify_event.yaml` for model config; calls the
LLM provider abstraction (from PLAN-F-002 multi-provider layer) with a prompt requesting
`{category: str, intensity: int}` JSON output; validates category against the 6-value enum
(`GEOPOLITICAL_CONFLICT`, `ECONOMIC_POLICY`, `NATURAL_DISASTER`, `CORPORATE_ACTION`,
`REGULATORY_CHANGE`, `PRICE_ANOMALY`) — raises `InvalidCategoryError` on unknown value;
validates intensity is 1–5 integer — raises `InvalidIntensityError` otherwise; writes
`ai_audit_log` entry with prompt SHA, model ID, `langfuse_trace_id`, confidence; sets
`state.category` and `state.intensity`.

`classify_event.yaml`: specifies `provider: anthropic`, `model_id: claude-haiku-4-5`,
`timeout_seconds: 10`, `max_retries: 2`, `cost_ceiling_usd: 0.02`.

**Tests to write first (TDD)**:
- `test_classify_step_sets_category_and_intensity` — mock LLM returning valid JSON; assert state fields set
- `test_classify_step_raises_on_invalid_category` — mock LLM returning unknown category; assert `InvalidCategoryError` raised, pipeline halts
- `test_classify_step_raises_on_out_of_range_intensity` — mock LLM returning intensity=6; assert `InvalidIntensityError` raised
- `test_classify_step_writes_audit_log` — assert `ai_audit_log` write called with model_id and trace_id
- `test_parse_step_routes_to_correct_parser_by_source` — assert GDELT parser called for GDELT payload

**Acceptance criteria covered**: AC-004

---

### TASK-006: Step 5 (EMBED) and Step 6 (PORTFOLIO SCAN)
**Complexity**: M | **TDD**: true
**Files**:
- `src/event_pipeline/steps/s05_embed.py`
- `src/event_pipeline/steps/s06_portfolio_scan.py`
- `tests/unit/event_pipeline/test_s05_embed.py`
- `tests/unit/event_pipeline/test_s06_portfolio_scan.py`

`EmbedStep` (Step 5): calls the embedding provider (from PLAN-F-002) to generate a 1536-dim
vector from the event description text; upserts the embedding into `geopolitical_events.embedding`
(pgvector column); stores `state.embedding`; caches embedding in Redis keyed on event fingerprint
(TTL ∞ — never evicted for historical events, per P-02 Cache-First + P-03).

`PortfolioScanStep` (Step 6): queries all active portfolios for the tenant from DB; for each
portfolio's holdings (tickers / sectors) checks against `state.tickers` and `state.category`;
returns the set of `portfolio_id` values with potentially affected holdings into
`state.exposure_map` (initialised to `{portfolio_id: 0.0}`). Uses the `get_portfolio_summary`
tool interface (read-only). Result is cached per `(event_fingerprint, tenant_id)` key in
Redis for the duration of the pipeline run.

**Tests to write first (TDD)**:
- `test_embed_step_calls_embedding_provider` — assert provider called with event description text
- `test_embed_step_stores_embedding_in_state` — assert `state.embedding` is 1536-dim list
- `test_embed_step_writes_to_geopolitical_events` — assert DB upsert called
- `test_portfolio_scan_returns_affected_portfolios` — mock portfolio holdings overlapping event tickers; assert portfolios in state
- `test_portfolio_scan_returns_empty_for_no_overlap` — no matching tickers; assert `state.exposure_map` is empty

**Acceptance criteria covered**: AC-001

---

### TASK-007: Step 7 (EXPOSURE SCORE) and Step 8 (ANALOGY SEARCH)
**Complexity**: M | **TDD**: true
**Files**:
- `src/event_pipeline/steps/s07_exposure_score.py`
- `src/event_pipeline/steps/s08_analogy_search.py`
- `tests/unit/event_pipeline/test_s07_exposure_score.py`
- `tests/unit/event_pipeline/test_s08_analogy_search.py`

`ExposureScoreStep` (Step 7): for each portfolio in `state.exposure_map`, computes
`inputs_hash = sha256(portfolio_holdings_json + event_category + event_intensity + tickers)`;
queries `event_scores` for an existing record with matching `inputs_hash`; if found: reuses
score (cache hit); if not: computes weighted exposure score based on holding weights and
event intensity; writes new `event_scores` record; preserves previous record (P-03 score
history). Updates `state.exposure_map[portfolio_id]` with computed float score.

`AnalogySearchStep` (Step 8): executes pgvector ANN query:
`SELECT event_id FROM geopolitical_events ORDER BY embedding <-> $1 LIMIT 10` where `$1`
is `state.embedding`; excludes current event; filters to same `tenant_id` unless no
tenant-scoped analogues exist (then falls back to cross-tenant historical events); stores
`state.analogues` as list of `event_id` UUIDs.

**Tests to write first (TDD)**:
- `test_exposure_score_reuses_cached_hash` — existing `event_scores` row with same hash; assert no recompute
- `test_exposure_score_computes_and_writes_new_score` — no existing hash match; assert new row written
- `test_exposure_score_preserves_historical_record` — after recompute, old record still present in DB
- `test_analogy_search_returns_top_k` — mock pgvector query returning 10 IDs; assert `state.analogues` length 10
- `test_analogy_search_excludes_current_event` — assert current `raw_event_id` not in analogues

**Acceptance criteria covered**: AC-001

---

### TASK-008: Step 9 (CONFIDENCE CALC) and Step 10 (ROUTING)
**Complexity**: M | **TDD**: true
**Files**:
- `src/event_pipeline/steps/s09_confidence_calc.py`
- `src/event_pipeline/steps/s10_routing.py`
- `tests/unit/event_pipeline/test_s09_confidence_calc.py`
- `tests/unit/event_pipeline/test_s10_routing.py`

`ConfidenceCalcStep` (Step 9): calls Haiku 4.5 (via multi-provider abstraction, same
`classify_event.yaml` model config) with a prompt synthesising classification confidence
and analogy strength (count and similarity scores from Step 8); outputs a `confidence`
float in [0.0, 1.0]; writes a second `ai_audit_log` entry for this LLM call; sets
`state.confidence`.

`RoutingStep` (Step 10): applies the C-003 routing rule:
- `confidence >= 0.7` → `state.route = AlertRoute.AUTO_SEND`
- `0.4 <= confidence < 0.7` → `state.route = AlertRoute.HIL_QUEUE`
- `confidence < 0.4` → `state.route = AlertRoute.BLOCKED`

`AlertRoute` is a `str` enum. This step is a pure function — no I/O.

**Tests to write first (TDD)**:
- `test_routing_auto_send_at_0_7` — confidence=0.7; assert route=AUTO_SEND
- `test_routing_hil_at_0_4` — confidence=0.4; assert route=HIL_QUEUE (inclusive lower bound)
- `test_routing_blocked_below_0_4` — confidence=0.399; assert route=BLOCKED
- `test_routing_hil_at_0_699` — confidence=0.699; assert route=HIL_QUEUE
- `test_confidence_calc_calls_llm_and_sets_state` — mock LLM; assert `state.confidence` set
- `test_confidence_calc_writes_audit_log` — assert second audit log entry written

**Acceptance criteria covered**: AC-001

---

### TASK-009: Step 11 (RECORD) — persistence to event_scores, ai_audit_log, episodic_memory
**Complexity**: M | **TDD**: true
**Files**:
- `src/event_pipeline/steps/s11_record.py`
- `tests/unit/event_pipeline/test_s11_record.py`

`RecordStep` (Step 11): within a single DB transaction:
1. Writes `event_scores` row for each portfolio in `state.exposure_map`.
2. Sets `raw_event.pipeline_status = completed` (only if route != BLOCKED; if BLOCKED sets
   `pipeline_status = completed` but `route = blocked` is noted in the score record).
3. Writes `episodic_memory` append-only record with `event_type = "pipeline_completed"`,
   `tenant_id`, `source_ref = raw_event_id`, `payload = {category, intensity, route, confidence}`.
4. All three writes are atomic; if the transaction fails, the step raises `PipelineHalt`
   and the executor marks the event `failed`.

All `episodic_memory` writes are INSERT-only — no UPDATE or DELETE ever (P-08).

**Tests to write first (TDD)**:
- `test_record_step_writes_event_scores_for_all_portfolios` — 3 portfolios in exposure_map; assert 3 rows
- `test_record_step_writes_episodic_memory_append_only` — assert INSERT called, not UPDATE
- `test_record_step_sets_pipeline_status_completed` — assert `raw_event.pipeline_status = completed`
- `test_record_step_rolls_back_on_db_error` — mock DB error on episodic write; assert all three inserts rolled back

**Acceptance criteria covered**: AC-001, AC-005

---

### TASK-010: Step 12 (DISPATCH) — alert send, HIL enqueue, BLOCKED suppression
**Complexity**: M | **TDD**: true
**Files**:
- `src/event_pipeline/steps/s12_dispatch.py`
- `src/event_pipeline/dispatch/alert_formatter.py`
- `src/event_pipeline/dispatch/websocket_dispatcher.py`
- `src/event_pipeline/dispatch/hil_enqueuer.py`
- `tests/unit/event_pipeline/test_s12_dispatch.py`

`DispatchStep` (Step 12): strategy-selects dispatcher by `state.route`:
- `AUTO_SEND`: calls `WebSocketDispatcher.push(alert)` and `WebPushDispatcher.push(alert)`.
  Alert text comes from `state.alert_text` (set in generate-alert-text step, see TASK-011).
  Writes alert record to `alerts` table (outside scope of this plan's migrations but noted).
- `HIL_QUEUE`: calls `HilEnqueuer.enqueue(item)` which writes to `hil_queue` table.
- `BLOCKED`: no outbound action; logs at `INFO` level with `route=blocked`.

`AlertFormatter` (Single Responsibility): produces `AlertPayload` Pydantic model from
`PipelineState`; attaches confidence, sample size (len(analogues)), and disclaimer text.

Each dispatcher is a dependency-injected collaborator. `DispatchStep` depends on abstractions,
not concretions (P-DI). No conditional `if route ==` inside dispatcher implementations.

Note: `generate_alert_text` (architecture Step 8 / req step 9) is folded into TASK-011 below
as it is directly consumed by dispatch.

**Tests to write first (TDD)**:
- `test_dispatch_auto_send_calls_websocket_and_web_push` — route=AUTO_SEND; assert both dispatchers called
- `test_dispatch_hil_enqueues_item` — route=HIL_QUEUE; assert `HilEnqueuer.enqueue` called
- `test_dispatch_blocked_suppresses_all_sends` — route=BLOCKED; assert no dispatcher called
- `test_alert_formatter_includes_confidence_and_disclaimer` — assert disclaimer text present in payload
- `test_dispatch_does_not_run_on_pipeline_halt` — executor halts before step 12; assert no dispatch

**Acceptance criteria covered**: AC-001, AC-005

---

### TASK-011: Generate alert text (req step 9), enqueue deep-dive (req step 12), and timestamp/trace closure (Step 13)
**Complexity**: M | **TDD**: true
**Files**:
- `src/event_pipeline/steps/s13_trace.py`
- `src/event_pipeline/steps/alert_text_generator.py`
- `src/event_pipeline/steps/deep_dive_enqueuer.py`
- `tests/unit/event_pipeline/test_s13_trace.py`
- `tests/unit/event_pipeline/test_alert_text_generator.py`

`AlertTextGenerator`: called inside `DispatchStep` (TASK-010) or as its own pre-dispatch
sub-step; composes concise alert copy from `state.category`, `state.intensity`,
`state.tickers`, `state.confidence`, `len(state.analogues)` as sample size, and appends
a mandatory disclaimer string from config; sets `state.alert_text`. No LLM call in this
step — text is template-rendered to stay within the ~$0.05/event budget.

`DeepDiveEnqueuer`: publishes a Celery task message `run_deep_dive.apply_async(args=[raw_event_id,
tenant_id])` to the `event_deep_dive` queue. Fires only when `route in (AUTO_SEND, HIL_QUEUE)`;
suppressed for BLOCKED events.

`TraceStep` (Step 13): closes the Langfuse trace opened at pipeline start; sets
`state.generated_at = datetime.utcnow()`; writes `generated_at` back to `raw_events` table;
emits a structured log line: `{event_id, tenant_id, latency_ms, route, confidence, step_count=13}`.

**Tests to write first (TDD)**:
- `test_alert_text_generator_includes_required_fields` — assert confidence, sample_size, disclaimer in output
- `test_deep_dive_enqueuer_publishes_for_auto_send` — route=AUTO_SEND; assert Celery task enqueued
- `test_deep_dive_enqueuer_suppressed_for_blocked` — route=BLOCKED; assert no Celery call
- `test_trace_step_sets_generated_at` — assert `state.generated_at` is set after step runs
- `test_trace_step_closes_langfuse_trace` — assert Langfuse client `trace.finish()` called

**Acceptance criteria covered**: AC-001, AC-002, AC-003

---

### TASK-012: Pipeline error handling — per-step failure trap and halt-without-dispatch guarantee
**Complexity**: M | **TDD**: true
**Files**:
- `src/event_pipeline/pipeline_executor.py` (update from TASK-001)
- `tests/unit/event_pipeline/test_pipeline_executor.py` (extend from TASK-001)

Extend `PipelineExecutor.run()` with:
- Per-step `try/except` wrapping every `await step.execute(state)` call.
- On any non-`PipelineHalt` exception: wrap in `PipelineHalt(step_name=step.step_name, detail=str(e))`
  then fall through to the halt handler.
- Halt handler: sets `state.failed_step`, `state.error_detail`; calls the `RawEventRepository`
  to update `pipeline_status = failed` with `failed_step` and `error_detail`; raises the
  `PipelineHalt` to propagate out of the Celery task (Celery marks task as FAILURE).
- Dispatch step (Step 12) is guarded: if `state.failed_step is not None` or
  `state.route == AlertRoute.BLOCKED`, no alert is dispatched.
- Structured error log emitted on halt: `{event_id, failed_step, error_detail, tenant_id}`.

**Tests to write first (TDD)**:
- `test_non_pipeline_halt_exception_is_wrapped` — step raises `ValueError`; assert `PipelineHalt` re-raised with step name
- `test_failed_step_name_matches_raising_step` — step 7 raises; assert `state.failed_step = "s07_exposure_score"`
- `test_db_status_written_to_failed_on_halt` — assert repository `update_status(failed)` called
- `test_dispatch_not_called_when_failed_step_set` — halt before dispatch; assert dispatch step skipped
- `test_error_detail_stored_in_state` — assert `state.error_detail` contains original exception message

**Acceptance criteria covered**: AC-005

---

### TASK-013: Integration tests — full pipeline end-to-end with mocked LLM and mocked providers
**Complexity**: M | **TDD**: true
**Files**:
- `tests/integration/event_pipeline/test_pipeline_end_to_end.py`
- `tests/integration/event_pipeline/conftest.py`

Integration tests run against a real PostgreSQL test DB (pgvector extension enabled) and a
real Redis instance (both spun up via `docker-compose.test.yml`). LLM calls are replaced
with deterministic mock responses via `pytest-mock`. Provider adapters use `FakeGdeltAdapter`
and `FakeEdgarAdapter` returning fixed `RawEventPayload` fixtures.

Test scenarios:
1. **Happy path GDELT event** — full 13 steps; assert `raw_events.pipeline_status = completed`,
   `geopolitical_events` row exists with embedding, `event_scores` row exists,
   `episodic_memory` row appended, Celery deep-dive task enqueued.
2. **Duplicate event** — submit same payload twice; assert second run has
   `pipeline_status = duplicate`, no second `event_scores` row, no second alert.
3. **Classification failure** — mock LLM returns invalid category; assert
   `pipeline_status = failed`, `failed_step = "s04_classify"`, no alert dispatched.
4. **BLOCKED route** — mock confidence = 0.1; assert `route = BLOCKED`, no WebSocket push,
   no HIL enqueue, `pipeline_status = completed`.
5. **HIL route** — mock confidence = 0.55; assert `hil_queue` row created, no WebSocket push.
6. **Step failure mid-pipeline** — mock Step 7 to raise; assert `pipeline_status = failed`,
   `failed_step = "s07_exposure_score"`, no partial alert dispatched.

**Tests to write first (TDD)**:
All six scenarios listed above are the tests.

**Acceptance criteria covered**: AC-001, AC-002, AC-003, AC-004, AC-005, AC-006

---

### TASK-014: Admin source toggle wiring for Twitter/X stub and source config
**Complexity**: S | **TDD**: false
**Files**:
- `src/event_pipeline/ingest/adapter_registry.py` (update from TASK-003)
- `src/config/settings.py` (update)

Wire `TWITTER_ENABLED` environment variable (default `false`) into `AdapterRegistry`. When
`TWITTER_ENABLED=false`, `AdapterRegistry.is_enabled(RawEventSource.X_FILTERED_STREAM)` returns
`False` and `TwitterStubAdapter.poll()` is never called. This matches admin toggle behaviour
described in C-002 and the architecture §11 source toggle. Add `TWITTER_ENABLED` to `.env.example`
with a comment explaining the stub status.

Also add: `DEDUP_TTL_SECONDS` (default 3600), `CLASSIFY_MODEL_YAML` (default
`agents/classify_event.yaml`), `PIPELINE_QUEUE` (default `event_pipeline`),
`DEEP_DIVE_QUEUE` (default `event_deep_dive`) to settings and `.env.example`.

**Acceptance criteria covered**: AC-001 (source ON/OFF toggleability)

---

## Acceptance Criteria Coverage
| AC | Description | Covered by |
|----|-------------|-----------|
| AC-001 | All 13 pipeline steps execute sequentially and produce persisted event record, dispatched alert (if rules match), and enqueued deep-dive job | TASK-001, TASK-002, TASK-003, TASK-006, TASK-007, TASK-008, TASK-009, TASK-010, TASK-011, TASK-013, TASK-014 |
| AC-002 | Tweet-class event: elapsed time from detected_at to alert dispatch < 30 seconds (measured by timestamp fields) | TASK-003, TASK-011, TASK-013 |
| AC-003 | Breaking geo/EDGAR event: elapsed time < 90 s for geo; < 20 min for SEC filing (measured by timestamp fields) | TASK-003, TASK-011, TASK-013 |
| AC-004 | classify step outputs valid category (6-value enum) and intensity (1–5); any out-of-range value raises structured error and halts pipeline | TASK-005, TASK-012, TASK-013 |
| AC-005 | Pipeline step failure marks event as failed with failing step name and error details; no partial alert dispatched | TASK-001, TASK-009, TASK-010, TASK-012, TASK-013 |
| AC-006 | Same raw event payload submitted twice within deduplication window: second run short-circuited after persist_raw_event, logged as duplicate, no duplicate alert | TASK-002, TASK-004, TASK-013 |

AC coverage: 6/6 = **100%**

## Definition of Done
- [ ] All 14 tasks complete
- [ ] Unit tests passing (TDD red-green-refactor cycle followed for all M/L tasks)
- [ ] Integration tests passing — all 6 scenarios in TASK-013
- [ ] AC-001 through AC-006 verified by integration test assertions
- [ ] `pipeline_status` transitions verified: `pending → running → completed | failed | duplicate`
- [ ] Langfuse trace closed on every pipeline run (success and failure)
- [ ] `ai_audit_log` row written for every LLM call (classify + confidence)
- [ ] `episodic_memory` append-only constraint verified: no UPDATE or DELETE on that table
- [ ] Twitter/X toggle defaults OFF; system operates without it
- [ ] `inputs_hash` invalidation verified: re-submitted event with unchanged holdings reuses score
- [ ] No TODO/FIXME in produced code
- [ ] `src/event_pipeline/` service layer >= 80% line coverage
- [ ] No stack traces returned to clients; all pipeline errors logged internally
- [ ] PLAN-F-002 interfaces (ProviderRegistry, CacheFirstMixin, Protocol implementations) confirmed present before TASK-003 begins
- [ ] dev-code-review run and all Critical/High findings resolved

## Open Questions Inherited
| # | Question | Resolution |
|---|----------|-----------|
| 1 | C-002: Twitter/X cost tier (Free vs $100/month Basic) | Resolved: stub adapter only; admin toggle defaults OFF; no live API connection in MVP (OQ-1). |
| 2 | C-005: Classification LLM (Azure OpenAI vs Anthropic) | Resolved: Anthropic Haiku 4.5 via multi-provider YAML abstraction; Azure OpenAI excluded from MVP (OQ-2). |
| 3 | C-001: $0.05/event cost reconciliation | Resolved: Haiku 4.5 for classify + confidence synthesis; cache-first for all provider calls; no Sonnet in Mode A path (OQ-3). |

## Risks and Notes
- **PLAN-F-002 hard dependency**: TASK-003 (source adapters) and TASK-006 (portfolio scan) consume
  `NewsProvider`, `PriceProvider`, and `CacheFirstMixin` from `src/providers/`. Do not start
  TASK-003 or TASK-006 until PLAN-F-002 is executed and its interfaces are importable.
- **pgvector ANN performance**: `geopolitical_events.embedding` column must have an IVFFlat or
  HNSW index for Step 8 performance. The Alembic migration in TASK-002 should include
  `CREATE INDEX CONCURRENTLY ON geopolitical_events USING ivfflat (embedding vector_cosine_ops)`.
- **Celery task idempotency**: Celery's at-least-once delivery means the same `raw_event_id`
  may be delivered twice. TASK-001 must check `pipeline_status` at task entry and return
  immediately if `completed` or `duplicate`.
- **Latency AC-002 is not directly testable in unit/integration tests**: the < 30 s SLA depends
  on infrastructure (Redis, Postgres, Celery worker scheduling). Integration tests assert that
  `detected_at` and `generated_at` are both set and that their difference is logged; load
  testing is required separately.
- **SEC EDGAR < 20-minute SLA (AC-003)**: `EdgarAdapter` must poll at an interval no greater
  than 5 minutes (`EDGAR_POLL_INTERVAL_SECONDS` env var, default 300). Webhook mode is
  preferred when SEC provides it.
- **Confidence thresholds are config, not magic numbers**: `AUTO_SEND_THRESHOLD` (default 0.7)
  and `HIL_THRESHOLD` (default 0.4) should be environment variables read by `RoutingStep`
  so operators can tune without code deployment.
- **`generate_alert_text` uses template rendering, not LLM**: to stay within $0.05/event
  budget, the alert copy is template-based. The LLM budget is spent only on classify
  (Step 4) and confidence synthesis (Step 9).
- **`alerts` table**: TASK-010 references writing an alert record. That table's full schema
  is owned by the alert-system requirement. TASK-010 should write a minimal alert stub
  record or use the `hil_queue` table; full alert schema integration can be deferred to the
  alert-system plan.
