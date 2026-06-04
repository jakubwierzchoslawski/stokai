---
plan_id: PLAN-F-001
slug: reactive-pipeline-ingestion
title: Reactive Pipeline Ingestion (Mode A)
linked_requirement: REQ-F-001
type: functional
status: done
blocked_reason:
complexity: XL
tdd_required: true
linked_nfrs:
  - { id: REQ-N-001, reason: "p99 end-to-end ≤ 90 s; LLM budget ≤ 18 s; processing ≤ 60 s" }
  - { id: REQ-N-003, reason: "Per-event LLM + API cost ceiling of $0.05" }
  - { id: REQ-N-008, reason: "One Langfuse trace per pipeline run; every LLM call is a logged span" }
dependencies: []
executed_at: 2026-06-03T00:00:00Z
reviewed_at:
review_id:
created_at: 2026-06-02T00:00:00Z
updated_at: 2026-06-02T00:00:00Z
---

# PLAN-F-001 — Reactive Pipeline Ingestion (Mode A)

## Linked Requirement
**REQ-F-001** — Reactive Pipeline Ingestion (Mode A)
Status: approved | Jira: —

## Objective
Build the complete 12-step Mode A Reactive Pipeline inside the `events` backend module. The pipeline receives a raw external event from any active source adapter (GDELT, SEC EDGAR, price anomaly, or Twitter/X when enabled), persists and classifies it using Claude Haiku 4.5, extracts affected tickers, computes a geo/sector exposure map against the company table, embeds the event text with OpenAI text-embedding-3-small, retrieves historical analogies via pgvector HNSW cosine search, generates an ~80-word alert text with Claude Sonnet 4.6, evaluates per-user alert rules with anti-fatigue controls, dispatches an alert via SendGrid or writes a silent-log entry, conditionally enqueues a Mode B Event Deep-Dive job, and returns a structured pipeline result — all within 90 seconds and a $0.05 per-event cost ceiling. Every LLM call is traced in Langfuse as a child span of a single pipeline-level trace.

## Architecture Context
This plan touches four layers of the six-layer model (Architecture §4):

- **Layer 2 — Ingestion:** Source adapter interfaces (`NewsProvider`, `FilingsProvider`, `SocialProvider`) feed events into the pipeline queue. The `ingestion` module provides the queue consumer hook; the `events` module owns the pipeline executor.
- **Layer 3 — Storage:** All reads and writes go through the `storage` module's repository pattern. New repository interfaces are defined for `geo_event`, `event_exposure`, `event_embedding`, `alert`, and `workflow_run` (for the Mode B enqueue reference). pgvector HNSW index on `event_embedding` supports step 7. TimescaleDB is not touched by this plan.
- **Layer 4 — Processing:** The `events` module hosts the `PipelineExecutor` service and its twelve step functions. The `ai` module provides the Langfuse tracer and the LLM client interfaces. The `alerts` module provides the `AlertRuleEvaluator` and `AlertDispatcher` interfaces consumed by steps 9 and 10.
- **Layer 5 — Serving:** A Celery task wraps the executor so it can be triggered asynchronously. A thin FastAPI endpoint (for internal/test triggering) is provided in the `api` module.

Module ownership per Architecture §5:
- `src/events/` — pipeline executor and step implementations (this plan's primary output)
- `src/storage/` — new repository interfaces and SQLAlchemy implementations for the event entities
- `src/ai/` — Langfuse tracer helper and LLM client wrapper (consumed, not owned, by this plan)
- `src/alerts/` — alert rule evaluator and dispatcher (consumed at steps 9–10)
- `src/config/` — Celery task registration

Decision D5 (12 steps, authoritative) and D6 (Anthropic-only MVP; OpenAI embeddings for event embedding only) are binding throughout.

## Applied NFR Constraints
| NFR | Constraint | Impact on this plan |
|-----|-----------|---------------------|
| REQ-N-001 | p99 end-to-end ≤ 90 s; LLM time ≤ 18 s total; deterministic processing ≤ 60 s | Per-step timeout guards added to each LLM call; pipeline executor records step latencies; Langfuse span records timing |
| REQ-N-003 | Per-event total LLM + embedding cost ≤ $0.05 | `CostAccumulator` tracks running cost after each LLM step; pipeline raises `CostCeilingExceededError` and halts if ceiling is hit before completion |
| REQ-N-008 | One Langfuse trace per pipeline run; every LLM call is a logged span with prompt version, model, token counts, latency, cost | `LangfuseTracer` is started at step 1 and flushed at step 12; each of the four LLM calls (classify, extract, embed, generate) creates a child span |

## Component Design

### New Components
```
Module: events (src/events/)
  ├── PipelineExecutor          — orchestrates all 12 steps; owns the Langfuse trace lifecycle
  ├── steps/
  │     ├── persist_raw_event   — step 1: write raw payload to geo_event staging row
  │     ├── classify_event      — step 2: Haiku 4.5 LLM call; returns ClassificationResult
  │     ├── extract_tickers     — step 3: Haiku 4.5 LLM call; returns list[str]
  │     ├── compute_exposure_map — step 4: DB query; returns list[ExposureCandidate]
  │     ├── persist_event_record — step 5: commits geo_event + event_exposure rows
  │     ├── embed_event         — step 6: OpenAI embedding; stores VECTOR(1536)
  │     ├── find_historical_analogies — step 7: pgvector HNSW top-K search
  │     ├── generate_alert_text — step 8: Sonnet 4.6 LLM call; ~80-word summary
  │     ├── evaluate_alert_rules — step 9: delegates to AlertRuleEvaluator interface
  │     ├── dispatch_or_log_silent — step 10: delegates to AlertDispatcher interface
  │     ├── enqueue_deep_dive   — step 11: conditional Mode B job enqueue via WorkflowQueue
  │     └── return_pipeline_result — step 12: writes episodic memory; returns PipelineResult
  ├── models.py                 — Pydantic models: RawEvent, ClassificationResult,
  │                               ExposureCandidate, PipelineResult, PipelineContext
  ├── cost_accumulator.py       — CostAccumulator: running per-event cost tracking
  ├── exceptions.py             — PipelineError, CostCeilingExceededError, StepTimeoutError
  └── celery_tasks.py           — Celery task wrapper: run_pipeline_task

Module: storage (src/storage/)  — new repository interfaces and implementations
  ├── interfaces/
  │     ├── IGeoEventRepository      — upsert_raw, persist_classified, get_by_id
  │     ├── IEventExposureRepository — bulk_insert
  │     ├── IEventEmbeddingRepository — insert, find_similar_hnsw(vector, k) → list[SimilarEvent]
  │     └── IAlertRepository         — insert_alert, insert_silent_log
  └── implementations/
        ├── geo_event_repository.py
        ├── event_exposure_repository.py
        ├── event_embedding_repository.py
        └── alert_repository.py

Module: ai (src/ai/)  — thin additions consumed by events module
  ├── interfaces/ILLMClient           — classify(prompt) → str, complete(prompt) → str
  ├── interfaces/IEmbeddingClient     — embed(text) → list[float]
  ├── interfaces/ILangfuseTracer      — start_trace, start_span, end_span, end_trace
  ├── anthropic_client.py             — AnthropicLLMClient implements ILLMClient
  ├── openai_embedding_client.py      — OpenAIEmbeddingClient implements IEmbeddingClient
  └── langfuse_tracer.py              — LangfuseTracer implements ILangfuseTracer

Module: alerts (src/alerts/)  — new interfaces + stubs consumed by steps 9–10
  ├── interfaces/IAlertRuleEvaluator  — evaluate(event, exposures, tenant_id) → RuleMatch | None
  └── interfaces/IAlertDispatcher    — dispatch(alert_data) → None; log_silent(event_id) → None
```

### Modified Components
| File | Change | Reason |
|------|--------|--------|
| `src/config/celery_app.py` | Register `run_pipeline_task` from `src/events/celery_tasks.py` | Make pipeline Celery-runnable |
| `src/api/routers/events.py` | Add `POST /api/v1/events/ingest` endpoint (internal; admin-only) | Provide HTTP trigger for testing and manual ingestion |

### Interfaces and Contracts

```python
# src/events/models.py

class RawEvent(BaseModel):
    source_provider: str          # "gdelt" | "edgar" | "price_anomaly" | "twitter"
    occurred_at: datetime
    raw_payload: dict[str, Any]
    tenant_id: UUID | None = None

class ClassificationResult(BaseModel):
    category: list[str]
    intensity: int                # 1–5
    sentiment: str                # "positive" | "negative" | "neutral"
    geo_regions: list[str]
    affected_sectors: list[str]
    cameo_code: str

class ExposureCandidate(BaseModel):
    company_id: UUID
    exposure_type: str            # "direct" | "supply_chain" | "sector" | "currency"
    direction: str                # "positive" | "negative"
    magnitude: float              # 0.0–1.0

class PipelineResult(BaseModel):
    event_id: UUID
    alert_dispatched: bool
    silent_logged: bool
    deep_dive_enqueued: bool
    total_cost_usd: float
    step_latencies_ms: dict[str, int]
    langfuse_trace_id: str

class PipelineContext(BaseModel):
    """Mutable state passed between steps."""
    raw_event: RawEvent
    event_id: UUID | None = None
    classification: ClassificationResult | None = None
    tickers: list[str] = []
    exposures: list[ExposureCandidate] = []
    embedding: list[float] | None = None
    analogies: list[dict] = []
    alert_text: str | None = None
    rule_match: Any | None = None
    cost_accumulator: Any = None       # CostAccumulator instance
    langfuse_trace_id: str | None = None


# src/storage/interfaces/i_event_embedding_repository.py

class SimilarEvent(BaseModel):
    event_id: UUID
    cosine_distance: float
    title: str
    occurred_at: datetime

class IEventEmbeddingRepository(Protocol):
    async def insert(self, event_id: UUID, embedding: list[float]) -> None: ...
    async def find_similar_hnsw(
        self, vector: list[float], k: int = 5
    ) -> list[SimilarEvent]: ...


# src/ai/interfaces/i_llm_client.py

class ILLMClient(Protocol):
    async def complete(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int,
        timeout_seconds: float,
    ) -> tuple[str, int, int]: ...  # (content, input_tokens, output_tokens)


# src/ai/interfaces/i_langfuse_tracer.py

class ILangfuseTracer(Protocol):
    def start_trace(self, name: str, metadata: dict) -> str: ...  # returns trace_id
    def start_span(self, trace_id: str, name: str, input: dict) -> str: ...  # returns span_id
    def end_span(self, span_id: str, output: dict, cost_usd: float, latency_ms: int) -> None: ...
    def end_trace(self, trace_id: str, output: dict) -> None: ...


# src/alerts/interfaces/i_alert_rule_evaluator.py

class RuleMatch(BaseModel):
    rule_id: UUID
    user_id: UUID
    tenant_id: UUID
    channels: list[str]

class IAlertRuleEvaluator(Protocol):
    async def evaluate(
        self,
        event_id: UUID,
        classification: ClassificationResult,
        exposures: list[ExposureCandidate],
        tenant_id: UUID | None,
    ) -> list[RuleMatch]: ...


# src/alerts/interfaces/i_alert_dispatcher.py

class IAlertDispatcher(Protocol):
    async def dispatch(self, rule_match: RuleMatch, alert_text: str, event_id: UUID) -> None: ...
    async def log_silent(self, event_id: UUID, tenant_id: UUID | None) -> None: ...
```

## Implementation Tasks

### TASK-001: Domain Models and Exceptions · S/no-TDD · src/events/models.py, src/events/exceptions.py, src/events/cost_accumulator.py

Define all Pydantic models used throughout the pipeline: `RawEvent`, `ClassificationResult`, `ExposureCandidate`, `PipelineResult`, `PipelineContext`. Define `PipelineError`, `CostCeilingExceededError`, `StepTimeoutError` exceptions. Implement `CostAccumulator` with `add(cost_usd: float) -> None` and `check_ceiling(ceiling: float) -> None` that raises `CostCeilingExceededError` when the running total exceeds the ceiling.

**AC covered**: enables AC-006

---

### TASK-002: Storage Repository Interfaces · S/no-TDD · src/storage/interfaces/i_geo_event_repository.py, src/storage/interfaces/i_event_exposure_repository.py, src/storage/interfaces/i_event_embedding_repository.py, src/storage/interfaces/i_alert_repository.py

Define the four `Protocol` interfaces exactly as specified in the Interfaces and Contracts section. Use `typing.Protocol` with `runtime_checkable` decorator. Each interface lives in its own file. No implementations in this task.

**AC covered**: enables AC-001, AC-004

---

### TASK-003: AI Client Interfaces · S/no-TDD · src/ai/interfaces/i_llm_client.py, src/ai/interfaces/i_embedding_client.py, src/ai/interfaces/i_langfuse_tracer.py, src/alerts/interfaces/i_alert_rule_evaluator.py, src/alerts/interfaces/i_alert_dispatcher.py

Define `ILLMClient`, `IEmbeddingClient`, `ILangfuseTracer`, `IAlertRuleEvaluator`, and `IAlertDispatcher` Protocol interfaces exactly as specified in the Interfaces and Contracts section. No implementations in this task.

**AC covered**: enables AC-003, AC-006

---

### TASK-004: Geo Event and Exposure Repositories · M/TDD · src/storage/implementations/geo_event_repository.py, src/storage/implementations/event_exposure_repository.py, tests/unit/storage/test_geo_event_repository.py, tests/unit/storage/test_event_exposure_repository.py

Implement `GeoEventRepository` satisfying `IGeoEventRepository`: `upsert_raw(raw_event: RawEvent) -> UUID` (creates a staging row with raw_payload JSON), `persist_classified(event_id, classification, title, summary, lat, lon, source_provider, tenant_id) -> None` (updates the row with all classified fields), `get_by_id(event_id) -> GeoEventRow | None`. Implement `EventExposureRepository` satisfying `IEventExposureRepository`: `bulk_insert(event_id, candidates: list[ExposureCandidate]) -> None`. Use SQLAlchemy 2.0 async session. Include `tenant_id` in all WHERE clauses where applicable. Tests use a test database transaction that rolls back after each test.

**Tests to write first (TDD)**:
- `upsert_raw` inserts a new row and returns the generated `event_id`
- `persist_classified` updates all classification fields on an existing staging row
- `get_by_id` returns `None` for a non-existent event_id
- `bulk_insert` inserts multiple exposure rows with correct `event_id` FK
- `bulk_insert` is idempotent when called twice with the same data (upsert on PK)

**AC covered**: AC-001

---

### TASK-005: Event Embedding Repository · M/TDD · src/storage/implementations/event_embedding_repository.py, tests/unit/storage/test_event_embedding_repository.py

Implement `EventEmbeddingRepository` satisfying `IEventEmbeddingRepository`: `insert(event_id, embedding: list[float]) -> None` stores the VECTOR(1536) value using pgvector's SQLAlchemy type; `find_similar_hnsw(vector, k=5) -> list[SimilarEvent]` executes `ORDER BY embedding <=> $1 LIMIT $2` using the HNSW index. Return results as `SimilarEvent` Pydantic models. Tests mock the pgvector column but verify the SQL is parameterised and the LIMIT is bounded.

**Tests to write first (TDD)**:
- `insert` stores a 1536-dimension vector and can be retrieved by `event_id`
- `find_similar_hnsw` returns at most `k` results ordered by cosine distance ascending
- `find_similar_hnsw` returns an empty list when the table has no rows
- Vector dimension mismatch (not 1536) raises a validation error before the DB call

**AC covered**: AC-004

---

### TASK-006: Alert Repository · S/no-TDD · src/storage/implementations/alert_repository.py

Implement `AlertRepository` satisfying `IAlertRepository`: `insert_alert(alert_data: dict) -> UUID` inserts an `alert` row and returns the `alert_id`; `insert_silent_log(event_id, tenant_id) -> None` inserts a minimal silent-log record. SQLAlchemy 2.0 async session. Both methods include `tenant_id` in the insert payload.

**AC covered**: enables AC-001

---

### TASK-007: Anthropic LLM Client · M/TDD · src/ai/anthropic_client.py, tests/unit/ai/test_anthropic_client.py

Implement `AnthropicLLMClient` satisfying `ILLMClient`. Constructor accepts `api_key: str`, `default_model: str`. `complete(system_prompt, user_message, max_tokens, timeout_seconds)` calls the Anthropic Messages API using `anthropic.AsyncAnthropic`, enforces the `timeout_seconds` via `asyncio.wait_for`, and returns `(content_str, input_tokens, output_tokens)`. On timeout, raise `StepTimeoutError`. Never log the API key. Tests mock `anthropic.AsyncAnthropic` and verify: timeout propagation, token count extraction, `StepTimeoutError` on timeout.

**Tests to write first (TDD)**:
- Successful completion returns content string and correct token counts
- Request exceeding `timeout_seconds` raises `StepTimeoutError`
- `anthropic.APIError` is wrapped in `PipelineError` with a sanitised message (no API key in message)
- `max_tokens` is forwarded verbatim to the Anthropic API call

**AC covered**: AC-003, enables AC-006

---

### TASK-008: OpenAI Embedding Client · M/TDD · src/ai/openai_embedding_client.py, tests/unit/ai/test_openai_embedding_client.py

Implement `OpenAIEmbeddingClient` satisfying `IEmbeddingClient`. Constructor accepts `api_key: str`. `embed(text: str) -> list[float]` calls `openai.AsyncOpenAI` with model `text-embedding-3-small`, enforces a 2-second timeout, and returns the embedding vector. Validates that the returned vector has exactly 1536 dimensions; raises `PipelineError` if not. Tests mock `openai.AsyncOpenAI`.

**Tests to write first (TDD)**:
- Successful embed returns a list of 1536 floats
- Response with wrong dimension count raises `PipelineError`
- Timeout after 2 s raises `StepTimeoutError`
- API key is never included in log output or exception messages

**AC covered**: AC-004

---

### TASK-009: Langfuse Tracer · M/TDD · src/ai/langfuse_tracer.py, tests/unit/ai/test_langfuse_tracer.py

Implement `LangfuseTracer` satisfying `ILangfuseTracer`. Uses the `langfuse` Python SDK (self-hosted). `start_trace(name, metadata) -> str` creates a Langfuse trace and returns `trace_id`. `start_span(trace_id, name, input) -> str` creates a child generation span, returns `span_id`. `end_span(span_id, output, cost_usd, latency_ms)` closes the span with output, cost, and latency. `end_trace(trace_id, output)` flushes the trace. If the Langfuse host is unreachable, log a warning and continue — observability failures must never block the pipeline. Tests mock the Langfuse SDK client.

**Tests to write first (TDD)**:
- `start_trace` calls the SDK `trace()` method and returns a non-empty string ID
- `end_span` records `cost_usd` and `latency_ms` on the span
- When the SDK raises a connection error, `LangfuseTracer` logs a warning and returns a no-op gracefully
- `end_trace` calls SDK flush; no exception is propagated if flush fails

**AC covered**: enables AC-001 (observability per REQ-N-008)

---

### TASK-010: Step 1 — persist_raw_event · S/no-TDD · src/events/steps/persist_raw_event.py

Implement `persist_raw_event(ctx: PipelineContext, repo: IGeoEventRepository) -> PipelineContext`. Calls `repo.upsert_raw(ctx.raw_event)`, stores the returned `event_id` in `ctx.event_id`, records step start latency. Returns updated context. This step must complete in < 1 second; no LLM call.

**AC covered**: AC-001

---

### TASK-011: Step 2 — classify_event · M/TDD · src/events/steps/classify_event.py, prompts/classifiers/event_classifier.md, tests/unit/events/steps/test_classify_event.py

Implement `classify_event(ctx: PipelineContext, llm: ILLMClient, tracer: ILangfuseTracer) -> PipelineContext`. Loads the system prompt from `prompts/classifiers/event_classifier.md`. Calls `llm.complete` with Haiku 4.5, `max_tokens=200`, `timeout_seconds=5.0`. Parses the JSON response into `ClassificationResult`. Opens a Langfuse span, records input_tokens, output_tokens, cost estimate, and latency. Adds cost to `ctx.cost_accumulator`; calls `check_ceiling(0.05)`. Write the prompt template in `prompts/classifiers/event_classifier.md` — it must request category[], intensity (integer 1–5), sentiment, geo_regions[], affected_sectors[], cameo_code as a JSON object.

**Tests to write first (TDD)**:
- Valid LLM JSON response is parsed into a `ClassificationResult` with all six fields populated
- Malformed JSON response raises `PipelineError` without propagating raw LLM output
- A 5-second timeout from the LLM raises `StepTimeoutError`
- Cost from the LLM call is added to `ctx.cost_accumulator`
- Langfuse span is started and ended with correct metadata

**AC covered**: AC-003

---

### TASK-012: Step 3 — extract_tickers · S/no-TDD · src/events/steps/extract_tickers.py, prompts/classifiers/ticker_extractor.md

Implement `extract_tickers(ctx: PipelineContext, llm: ILLMClient, tracer: ILangfuseTracer) -> PipelineContext`. Loads the ticker extraction prompt. Calls `llm.complete` with Haiku 4.5, `max_tokens=100`, `timeout_seconds=3.0`. Parses the JSON array of ticker strings. Stores result in `ctx.tickers`. Adds cost to accumulator; calls `check_ceiling`. Writes the ticker extractor prompt in `prompts/classifiers/ticker_extractor.md`.

**AC covered**: enables AC-001

---

### TASK-013: Step 4 — compute_exposure_map · M/TDD · src/events/steps/compute_exposure_map.py, tests/unit/events/steps/test_compute_exposure_map.py

Implement `compute_exposure_map(ctx: PipelineContext, db_session: AsyncSession) -> PipelineContext`. Queries the `company` table for rows where:
- `hq_country` or any key in `geo_revenue JSONB` matches any entry in `ctx.classification.geo_regions`, OR
- `sector_internal` or `sector_gics` matches any entry in `ctx.classification.affected_sectors`

Also includes any company whose ticker matches an entry in `ctx.tickers`. For each matched company, constructs an `ExposureCandidate` with `exposure_type` (direct for ticker match, sector for sector match, currency for geo_revenue match), `direction` ("negative" for sectors typically hurt by geopolitical events, "positive" otherwise — a simple heuristic lookup table), and `magnitude` (0.5 default; 1.0 for direct ticker match). Stores result in `ctx.exposures`. Must complete in < 3 s.

**Tests to write first (TDD)**:
- Company matching by `geo_regions` appears in output with `exposure_type="currency"`
- Company matching by `affected_sectors` appears with `exposure_type="sector"`
- Company matching by exact ticker appears with `exposure_type="direct"` and `magnitude=1.0`
- Company not matching any criterion is excluded from output
- Empty geo_regions + empty sectors + empty tickers returns an empty exposures list
- Query uses parameterised SQL (no string interpolation)

**AC covered**: AC-001

---

### TASK-014: Step 5 — persist_event_record · S/no-TDD · src/events/steps/persist_event_record.py

Implement `persist_event_record(ctx: PipelineContext, geo_repo: IGeoEventRepository, exposure_repo: IEventExposureRepository) -> PipelineContext`. Calls `geo_repo.persist_classified(...)` with all classification fields and the `title`, `summary` from the raw payload. Then calls `exposure_repo.bulk_insert(ctx.event_id, ctx.exposures)`. Returns updated context. Must complete in < 1 s.

**AC covered**: AC-001

---

### TASK-015: Step 6 — embed_event · M/TDD · src/events/steps/embed_event.py, tests/unit/events/steps/test_embed_event.py

Implement `embed_event(ctx: PipelineContext, embedding_client: IEmbeddingClient, embedding_repo: IEventEmbeddingRepository, tracer: ILangfuseTracer) -> PipelineContext`. Concatenates `title + " " + summary` from the raw payload as the text to embed. Calls `embedding_client.embed(text)` with 2-second timeout enforced by the client. Stores the vector via `embedding_repo.insert(ctx.event_id, vector)`. Stores the vector in `ctx.embedding`. Opens and closes a Langfuse span recording the embedding dimension, latency, and cost (uses OpenAI pricing for text-embedding-3-small). Adds cost to accumulator.

**Tests to write first (TDD)**:
- Embedding result is stored in `ctx.embedding` and written to the repository
- Timeout from the embedding client propagates as `StepTimeoutError`
- Text passed to the embedding client is the concatenation of title and summary
- Langfuse span records the correct embedding model name

**AC covered**: AC-004

---

### TASK-016: Step 7 — find_historical_analogies · M/TDD · src/events/steps/find_historical_analogies.py, tests/unit/events/steps/test_find_historical_analogies.py

Implement `find_historical_analogies(ctx: PipelineContext, embedding_repo: IEventEmbeddingRepository) -> PipelineContext`. Calls `embedding_repo.find_similar_hnsw(ctx.embedding, k=5)`. Excludes the current `ctx.event_id` from results if it appears. Converts results to a list of dicts (event_id, title, occurred_at, cosine_distance) stored in `ctx.analogies`. Must complete in < 3 s (no timeout guard needed — this is a DB call, not an LLM call).

**Tests to write first (TDD)**:
- Returns up to 5 analogies sorted by cosine distance ascending
- Current event_id is excluded from the returned analogies
- Empty result from the repository results in `ctx.analogies = []` (no exception)
- Each analogy dict contains `event_id`, `title`, `occurred_at`, `cosine_distance`

**AC covered**: AC-004

---

### TASK-017: Step 8 — generate_alert_text · M/TDD · src/events/steps/generate_alert_text.py, prompts/classifiers/alert_text_generator.md, tests/unit/events/steps/test_generate_alert_text.py

Implement `generate_alert_text(ctx: PipelineContext, llm: ILLMClient, tracer: ILangfuseTracer) -> PipelineContext`. Loads prompt from `prompts/classifiers/alert_text_generator.md`. Constructs the user message from the classification result, top analogies (up to 3), and exposed company names. Calls `llm.complete` with Sonnet 4.6, `max_tokens=200`, `timeout_seconds=8.0`. Stores the response in `ctx.alert_text`. Opens and closes a Langfuse span. Adds cost to accumulator; calls `check_ceiling`. The prompt in `prompts/classifiers/alert_text_generator.md` must instruct Sonnet to produce a maximum of 80-word alert text. Write the prompt file.

**Tests to write first (TDD)**:
- LLM response is stored verbatim in `ctx.alert_text`
- Timeout after 8 s raises `StepTimeoutError`
- Cost is added to the accumulator after a successful call
- Prompt construction includes analogy context when `ctx.analogies` is non-empty
- Prompt construction omits analogy section when `ctx.analogies` is empty

**AC covered**: AC-001

---

### TASK-018: Step 9 — evaluate_alert_rules · M/TDD · src/events/steps/evaluate_alert_rules.py, src/alerts/alert_rule_evaluator.py, src/alerts/interfaces/i_alert_rule_evaluator.py, tests/unit/events/steps/test_evaluate_alert_rules.py, tests/unit/alerts/test_alert_rule_evaluator.py

Implement `evaluate_alert_rules(ctx: PipelineContext, evaluator: IAlertRuleEvaluator) -> PipelineContext`. Calls `evaluator.evaluate(ctx.event_id, ctx.classification, ctx.exposures, ctx.raw_event.tenant_id)`. Stores the list of `RuleMatch` objects in `ctx.rule_match`. Implement `AlertRuleEvaluator` satisfying `IAlertRuleEvaluator`: queries the `alert_rule` table for the tenant, applies intensity filters (`rule.min_intensity <= classification.intensity`), scope filters (checks if any exposure company_id is in the rule's scope JSONB), deduplication (no alert sent for same event_id + rule_id within deduplication window from `user.settings`), anti-fatigue (user's `daily_push_limit` not exceeded).

**Tests to write first (TDD)**:
- Rule with `min_intensity=3` matches a classification with `intensity=4`
- Rule with `min_intensity=5` does not match a classification with `intensity=3`
- Rule that already fired for the same `event_id` within dedup window returns no match
- User who has hit `daily_push_limit` receives no match regardless of intensity
- `evaluate_alert_rules` step stores the list of matches in `ctx.rule_match`

**AC covered**: AC-001

---

### TASK-019: Step 10 — dispatch_or_log_silent · M/TDD · src/events/steps/dispatch_or_log_silent.py, src/alerts/alert_dispatcher.py, src/alerts/interfaces/i_alert_dispatcher.py, tests/unit/events/steps/test_dispatch_or_log_silent.py, tests/unit/alerts/test_alert_dispatcher.py

Implement `dispatch_or_log_silent(ctx: PipelineContext, dispatcher: IAlertDispatcher, alert_repo: IAlertRepository) -> PipelineContext`. If `ctx.rule_match` is non-empty, calls `dispatcher.dispatch(rule_match, ctx.alert_text, ctx.event_id)` for each match and calls `alert_repo.insert_alert(...)`. If empty, calls `dispatcher.log_silent(ctx.event_id, ctx.raw_event.tenant_id)` and `alert_repo.insert_silent_log(...)`. Implement `AlertDispatcher` satisfying `IAlertDispatcher`: for `dispatch`, constructs a SendGrid email API call using `sendgrid.SendGridAPIClient`; for `log_silent`, writes to a structured log at INFO level. SendGrid API key read from environment variable `SENDGRID_API_KEY`.

**Tests to write first (TDD)**:
- When `ctx.rule_match` is non-empty, `dispatcher.dispatch` is called once per match
- When `ctx.rule_match` is empty, `dispatcher.log_silent` is called and `dispatch` is not called
- `AlertDispatcher.dispatch` constructs a SendGrid request with correct `to`, `subject`, `body`
- SendGrid API failure is wrapped in `PipelineError` (no raw SendGrid error propagated)
- `insert_silent_log` is called when no rules matched

**AC covered**: AC-001

---

### TASK-020: Step 11 — enqueue_deep_dive · S/no-TDD · src/events/steps/enqueue_deep_dive.py

Implement `enqueue_deep_dive(ctx: PipelineContext, workflow_queue: IWorkflowQueue) -> PipelineContext`. Enqueues a Mode B Event Deep-Dive job if `ctx.classification.intensity >= 4` OR if any `ExposureCandidate` in `ctx.exposures` has `exposure_type="direct"` (portfolio match). The enqueue call sets `workflow_type="event_deep_dive"`, `inputs={"event_id": str(ctx.event_id)}`, `priority="high"`, and `scheduled_for=now() + timedelta(minutes=2)`. Define the `IWorkflowQueue` Protocol in `src/events/interfaces/i_workflow_queue.py`. Returns updated context with `deep_dive_enqueued` flag.

**AC covered**: AC-002

---

### TASK-021: Step 12 — return_pipeline_result · S/no-TDD · src/events/steps/return_pipeline_result.py

Implement `return_pipeline_result(ctx: PipelineContext, tracer: ILangfuseTracer) -> PipelineResult`. Closes the Langfuse trace via `tracer.end_trace(ctx.langfuse_trace_id, output={...})`. Constructs and returns `PipelineResult` with `event_id`, `alert_dispatched`, `silent_logged`, `deep_dive_enqueued`, `total_cost_usd`, `step_latencies_ms`, and `langfuse_trace_id`. This step also writes an episodic memory entry: inserts a minimal row into `workflow_run` with `workflow_type="mode_a_pipeline"`, `status="complete"`, `cost_usd`, and `langfuse_trace_id`.

**AC covered**: AC-001

---

### TASK-022: PipelineExecutor Orchestrator · L/TDD · src/events/pipeline_executor.py, tests/unit/events/test_pipeline_executor.py, tests/integration/events/test_pipeline_executor_integration.py

Implement `PipelineExecutor` class. Constructor receives all interface dependencies via injection: `geo_event_repo`, `event_exposure_repo`, `event_embedding_repo`, `alert_repo`, `llm_client`, `embedding_client`, `tracer`, `alert_rule_evaluator`, `alert_dispatcher`, `workflow_queue`, `db_session`. `run(raw_event: RawEvent) -> PipelineResult` method: initialises `PipelineContext`, starts the Langfuse trace, calls all 12 step functions in order, catches `StepTimeoutError` and `CostCeilingExceededError` (logs and re-raises as `PipelineError`), records per-step latencies in context, and calls `return_pipeline_result` at the end even on error (to flush the trace). Total wall-clock time is asserted to be within 90 s in the integration test.

**Tests to write first (TDD)**:
- Unit: successful run with all mocked steps returns a `PipelineResult` with `event_id` set
- Unit: `StepTimeoutError` from any step raises `PipelineError` and still flushes the Langfuse trace
- Unit: `CostCeilingExceededError` halts the pipeline and raises `PipelineError`
- Unit: step latencies are recorded for all 12 steps in `PipelineResult.step_latencies_ms`
- Integration: full 12-step run against mocked LLM clients and test DB completes without exception
- Integration: `PipelineResult.total_cost_usd` is less than or equal to 0.05 on a typical run

**AC covered**: AC-001, AC-002, AC-006

---

### TASK-023: Celery Task Wrapper and FastAPI Ingest Endpoint · S/no-TDD · src/events/celery_tasks.py, src/api/routers/events.py, src/config/celery_app.py

Implement `run_pipeline_task` as a Celery task in `src/events/celery_tasks.py`. It receives a serialised `RawEvent` dict, deserialises it, instantiates `PipelineExecutor` with production dependencies resolved from the application DI context, and calls `executor.run(raw_event)`. Implement `POST /api/v1/events/ingest` in `src/api/routers/events.py` — admin-only (requires `role="admin"` JWT claim), accepts a `RawEvent` JSON body, enqueues `run_pipeline_task` to Celery, and returns `202 Accepted` with a task ID. Register the task in `src/config/celery_app.py`.

**AC covered**: AC-001, AC-005

---

### TASK-024: Twitter/X Graceful Degradation · S/no-TDD · src/events/steps/persist_raw_event.py, src/config/settings.py

Add a `TWITTER_ENABLED` environment variable (default `false`) to `src/config/settings.py`. In `persist_raw_event`, if a `RawEvent` with `source_provider="twitter"` arrives and `settings.TWITTER_ENABLED` is `false`, raise a `SourceDisabledError` (subclass of `PipelineError`) which is caught by the executor and causes a graceful skip — not a pipeline failure. Update the `PipelineExecutor` to catch `SourceDisabledError` specifically: log at INFO level and return an empty `PipelineResult` without triggering an error trace. Document that all other source providers (gdelt, edgar, price_anomaly) are always enabled regardless of this flag.

**AC covered**: AC-005

---

### TASK-025: End-to-End Integration Test · L/TDD · tests/integration/events/test_pipeline_e2e.py

Write a full integration test that exercises all 12 steps with: a real PostgreSQL test database (via `pytest-asyncio` + `asyncpg`), mocked Anthropic and OpenAI API clients (using `pytest-mock`), a mocked SendGrid client, and a mocked Langfuse SDK. The test asserts: a `geo_event` row exists after the run; at least one `event_exposure` row exists; an `event_embedding` row with a 1536-dim vector exists; either an `alert` row or a silent-log entry exists; `PipelineResult.total_cost_usd <= 0.05`; the total wall-clock time of `executor.run()` does not exceed 90 seconds. A second test case uses an intensity-4 event and asserts that `PipelineResult.deep_dive_enqueued` is `True`. A third test asserts that when `source_provider="twitter"` and `TWITTER_ENABLED=false`, the pipeline returns gracefully without writing any DB rows.

**Tests to write first (TDD)**:
- Happy path: all 12 steps complete; all DB rows exist; `total_cost_usd <= 0.05`
- High-intensity event (intensity >= 4): `deep_dive_enqueued` is `True`
- Twitter disabled: `SourceDisabledError` is caught; no DB rows written; no exception propagated
- Rule evaluation with no matching rules: `silent_logged` is `True`, `alert_dispatched` is `False`

**AC covered**: AC-001, AC-002, AC-003, AC-004, AC-005, AC-006

---

## Acceptance Criteria Coverage

- AC-001: Given an external event arrives from GDELT, SEC EDGAR, or a price anomaly source, the system completes all 12 pipeline steps and produces a persisted geo_event row, event_exposure rows, event_embedding row, and an alert or silent-log record within 90 seconds → TASK-004, TASK-005, TASK-006, TASK-010, TASK-011, TASK-012, TASK-013, TASK-014, TASK-015, TASK-017, TASK-018, TASK-019, TASK-021, TASK-022, TASK-023, TASK-025
- AC-002: Given a high-intensity event (intensity 4 or 5) matching at least one portfolio company, a Mode B deep-dive job is enqueued at step 12 within the 90-second window → TASK-020, TASK-022, TASK-025
- AC-003: Given classification by Haiku 4.5, the geo_event record carries populated category[], intensity, sentiment, geo_regions[], affected_sectors[], and cameo_code fields within 5 seconds → TASK-007, TASK-011, TASK-025
- AC-004: Given event text is embedded (step 7), the embedding is stored as a VECTOR(1536) in the event_embedding table and the pgvector HNSW top-K search returns analogy results within the 60-second total LLM budget → TASK-005, TASK-008, TASK-015, TASK-016, TASK-025
- AC-005: Given Twitter/X is toggled off by admin, the pipeline completes successfully using remaining sources without errors or degraded output quality → TASK-023, TASK-024, TASK-025
- AC-006: Given any single pipeline run, the total LLM and API cost is recorded and does not exceed $0.05 per event → TASK-001, TASK-007, TASK-011, TASK-017, TASK-022, TASK-025

## Risks and Notes

- **pgvector HNSW index bootstrap:** The `event_embedding` HNSW index must be created via a migration (`CREATE INDEX ... USING hnsw (embedding vector_cosine_ops)`). Without the HNSW index the `find_similar_hnsw` step will fall back to a sequential scan which may breach the 90-second SLA for large tables. Include the index migration in the earliest DB migration touching `event_embedding`.
- **OpenAI for embeddings (not Anthropic):** Decision D6 specifies Anthropic-only for LLM tasks, but `text-embedding-3-small` is an OpenAI model. The OpenAI API key (`OPENAI_API_KEY`) must be present in the environment even in an Anthropic-only deployment. The `IEmbeddingClient` interface insulates the rest of the system from this.
- **Cost ceiling enforcement ordering:** The `CostAccumulator.check_ceiling` call occurs after each LLM step. This means the last step that pushes total cost above $0.05 is caught before the next step runs, but the over-budget step itself has already executed. This is acceptable: the pipeline halts immediately, the event is persisted, and the operator is notified via the Langfuse trace.
- **Langfuse flush on error:** The `PipelineExecutor.run` must call `tracer.end_trace` in a `finally` block so that traces are flushed even when a step raises. This prevents orphaned traces in Langfuse.
- **Twitter/X source_provider race:** If Twitter/X is toggled off mid-pipeline (rare but possible at admin level), the `SourceDisabledError` path in `persist_raw_event` handles the case cleanly. No partial pipeline writes occur because `persist_raw_event` is step 1.
- **Prompt files are part of the deliverable:** `prompts/classifiers/event_classifier.md`, `prompts/classifiers/ticker_extractor.md`, and `prompts/classifiers/alert_text_generator.md` must be committed alongside the code. The Langfuse tracer records the prompt SHA; without the file the SHA cannot be computed.
- **Anti-fatigue state:** The deduplication window and daily push limit are read from `user.settings` (JSONB). The `AlertRuleEvaluator` must handle absent keys gracefully (default: 60-minute dedup window, daily limit of 5).
