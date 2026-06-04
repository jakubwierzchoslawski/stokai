---
plan_id: PLAN-F-002
slug: event-classification-and-extraction
title: Event Classification and Ticker Extraction
linked_requirement: REQ-F-002
type: functional
status: done
blocked_reason:
complexity: M
tdd_required: true
linked_nfrs:
  - { id: REQ-N-001, reason: "classify_event ≤5s, extract_tickers ≤3s, both within the 18s total LLM budget" }
  - { id: REQ-N-003, reason: "Both calls use Haiku 4.5; token budgets strictly bounded (2k in/200 out and 1k in/100 out)" }
  - { id: REQ-N-008, reason: "Each LLM call is a Langfuse child span with prompt_version, model, tokens, latency, cost" }
dependencies:
  - { id: PLAN-F-001, reason: "Steps 2–3 run inside the Mode A pipeline; ILLMClient, ILangfuseTracer, ClassificationResult, PipelineContext, and CostAccumulator are defined there" }
executed_at: 2026-06-03T00:00:00Z
reviewed_at:
review_id:
created_at: 2026-06-02T00:00:00Z
updated_at: 2026-06-02T00:00:00Z
---

# PLAN-F-002 — Event Classification and Ticker Extraction

## Linked Requirement
**REQ-F-002** — Event Classification and Ticker Extraction
Status: approved | Jira: —

## Objective
Implement the two LLM-powered steps of the Mode A Reactive Pipeline that transform raw event
text into structured intelligence: `classify_event` (step 2, Haiku 4.5, ≤5 s) and
`extract_tickers` (step 3, Haiku 4.5, ≤3 s). Each step loads its prompt from a versioned
Markdown file, calls the Anthropic Messages API with strictly bounded token budgets, validates
the response against a Pydantic output model, records a Langfuse child span with prompt SHA,
model name, token counts, latency, and estimated cost, and propagates structured errors when
token limits or cost ceilings are exceeded. The output of `classify_event` is a fully populated
`ClassificationResult` (category[], intensity 1–5, sentiment –1.0 to +1.0, geo_regions[],
affected_sectors[], cameo_code). The output of `extract_tickers` is a `TickerExtractionResult`
(tickers[], may be empty). Both are stored on `PipelineContext` for downstream steps.

## Architecture Context
This plan is scoped entirely to **Layer 4 — Processing** (Architecture §4) and the `events`
backend module (Architecture §5). It extends the step implementations inside `src/events/steps/`
that were scaffolded in PLAN-F-001.

**Consumed from PLAN-F-001 (no re-implementation):**
- `src/events/models.py` — `ClassificationResult`, `PipelineContext`, `RawEvent`
- `src/events/exceptions.py` — `PipelineError`, `StepTimeoutError`, `CostCeilingExceededError`
- `src/events/cost_accumulator.py` — `CostAccumulator`
- `src/ai/interfaces/i_llm_client.py` — `ILLMClient` Protocol
- `src/ai/interfaces/i_langfuse_tracer.py` — `ILangfuseTracer` Protocol
- `src/ai/anthropic_client.py` — `AnthropicLLMClient` (concrete; injected)

**New artifacts owned by this plan:**
- `src/events/steps/classify_event.py` — step 2 implementation
- `src/events/steps/extract_tickers.py` — step 3 implementation
- `src/events/models.py` — `TickerExtractionResult` model (additive change)
- `prompts/classifiers/event_classifier.md` — prompt template for classification
- `prompts/classifiers/ticker_extractor.md` — prompt template for extraction
- Unit tests for both steps

**Prompt management (Architecture §8):** Prompts are stored in `prompts/classifiers/` under
Git version control. The Git SHA of each prompt file is recorded as the `prompt_version` on
every Langfuse span, enabling exact reproduction of any historical inference. The prompts are
loaded from the filesystem at call time (not at module import), so edits without restart are
possible in development. In production, prompt files are baked into the container image.

**Agent YAML constraints (Architecture §7.1):** Both steps enforce `max_input_tokens` and
`cost_ceiling_usd` as specified by their agent YAML configuration. When either limit is
exceeded, the step raises a structured error (not a truncated or partial result), as required
by AC-004.

## Applied NFR Constraints

| NFR | Constraint | Impact on this plan |
|-----|-----------|---------------------|
| REQ-N-001 | classify_event ≤5 s; extract_tickers ≤3 s; both within 18 s total LLM budget | `timeout_seconds` passed to `llm.complete`; `StepTimeoutError` raised on breach; per-step latency recorded in Langfuse span |
| REQ-N-003 | Haiku 4.5 only; classification max 2k in / 200 out; extraction max 1k in / 100 out | `max_tokens` enforced in the `llm.complete` call; input is pre-truncated to stay within limit; cost estimated and added to `CostAccumulator` after each call |
| REQ-N-008 | Each LLM call is a Langfuse child span with prompt_version (git SHA), model, input_tokens, output_tokens, latency_ms, cost_usd | `tracer.start_span` / `tracer.end_span` called in each step; prompt SHA computed via `hashlib.sha256` on prompt file content at call time |

## Component Design

### New Components

```
Module: events (src/events/)
  └── steps/
        ├── classify_event.py       — step 2: load prompt, call LLM, validate, record span
        └── extract_tickers.py      — step 3: load prompt, call LLM, validate, record span

Module: events (src/events/) — additive change
  └── models.py                    — add TickerExtractionResult(tickers: list[str])

Prompts:
  prompts/classifiers/
        ├── event_classifier.md    — system + user prompt template for classification
        └── ticker_extractor.md    — system + user prompt template for ticker extraction

Tests:
  tests/unit/events/steps/
        ├── test_classify_event.py
        └── test_extract_tickers.py
```

### Modified Components

| File | Change | Reason |
|------|--------|--------|
| `src/events/models.py` | Add `TickerExtractionResult(tickers: list[str])` model | Required output type for extract_tickers step |

### Interfaces and Contracts

These are the exact function signatures the executor must implement. Both functions follow the
step convention established in PLAN-F-001: they receive an immutable context and dependencies,
mutate a copy, and return the updated context.

```python
# src/events/steps/classify_event.py

async def classify_event(
    ctx: PipelineContext,
    llm: ILLMClient,
    tracer: ILangfuseTracer,
    prompt_path: Path = Path("prompts/classifiers/event_classifier.md"),
) -> PipelineContext:
    """
    Step 2 of the Mode A pipeline.

    - Loads the prompt from `prompt_path`.
    - Computes the prompt SHA via hashlib.sha256 for Langfuse version label.
    - Calls llm.complete(system_prompt, user_message, max_tokens=200, timeout_seconds=5.0)
      where user_message is the raw event text from ctx.raw_event.raw_payload["text"].
    - Parses the JSON response into ClassificationResult; raises PipelineError on parse failure.
    - Validates: intensity in [1, 5]; sentiment in [-1.0, 1.0]; raises PipelineError otherwise.
    - Opens a Langfuse child span on ctx.langfuse_trace_id; records prompt_version, model,
      input_tokens, output_tokens, latency_ms, cost_usd.
    - Adds cost to ctx.cost_accumulator; calls check_ceiling(0.05).
    - Stores result in ctx.classification.
    - Returns updated ctx.
    """
    ...


# src/events/steps/extract_tickers.py

async def extract_tickers(
    ctx: PipelineContext,
    llm: ILLMClient,
    tracer: ILangfuseTracer,
    prompt_path: Path = Path("prompts/classifiers/ticker_extractor.md"),
) -> PipelineContext:
    """
    Step 3 of the Mode A pipeline.

    - Loads the prompt from `prompt_path`.
    - Computes the prompt SHA for Langfuse version label.
    - Calls llm.complete(system_prompt, user_message, max_tokens=100, timeout_seconds=3.0)
      where user_message is the raw event text from ctx.raw_event.raw_payload["text"].
    - Parses the JSON response into TickerExtractionResult; empty list is valid.
    - Raises PipelineError on parse failure; does NOT raise on empty list.
    - Opens a Langfuse child span; records the same fields as classify_event.
    - Adds cost to ctx.cost_accumulator; calls check_ceiling(0.05).
    - Stores result in ctx.tickers.
    - Returns updated ctx.
    """
    ...


# src/events/models.py (additive)

class TickerExtractionResult(BaseModel):
    tickers: list[str]   # may be empty; each entry is an uppercase NYSE/NASDAQ ticker symbol
```

### Prompt Templates

`prompts/classifiers/event_classifier.md` must contain a system prompt instructing Haiku 4.5
to return a single JSON object with exactly these keys:

```json
{
  "category": ["string"],
  "intensity": 1,
  "sentiment": 0.0,
  "geo_regions": ["string"],
  "affected_sectors": ["string"],
  "cameo_code": "string"
}
```

It must specify: intensity is an integer from 1 to 5; sentiment is a float from -1.0 to +1.0;
category uses a fixed taxonomy (e.g. conflict, sanctions, election, natural_disaster,
economic_policy, trade, humanitarian); cameo_code follows the CAMEO ontology. The system
prompt must include two worked examples (one high-intensity conflict, one low-intensity
economic event) to ground the model's output format.

`prompts/classifiers/ticker_extractor.md` must contain a system prompt instructing Haiku 4.5
to return a single JSON object with exactly this key:

```json
{ "tickers": ["AAPL", "XOM"] }
```

It must specify: only NYSE and NASDAQ listed companies; implied exposures are acceptable
(e.g. oil majors for a Middle East conflict); empty array when no companies are mentioned or
implied; no explanations, only the JSON object.

## Implementation Tasks

### TASK-001: TickerExtractionResult Model · S/no-TDD · src/events/models.py

Add `TickerExtractionResult` to `src/events/models.py` as a Pydantic `BaseModel` with a
single field `tickers: list[str]`. Each ticker is validated to be a non-empty uppercase string
(use `@field_validator`). The model must accept an empty list without raising. This is a purely
additive change; no existing model is modified.

**AC covered**: AC-002, AC-003

---

### TASK-002: Event Classifier Prompt · S/no-TDD · prompts/classifiers/event_classifier.md

Write the `event_classifier.md` prompt file. The prompt must:
- Open with a system role definition for Haiku 4.5 as a geopolitical event classifier.
- Specify the exact JSON output schema with all six fields (category[], intensity, sentiment,
  geo_regions[], affected_sectors[], cameo_code).
- Define valid category taxonomy values.
- State that intensity is an integer in [1, 5] and sentiment is a float in [-1.0, +1.0].
- Reference the CAMEO ontology for cameo_code.
- Include two distinct worked examples: one for a high-intensity conflict event and one for
  a low-intensity economic policy event, each with a complete expected JSON output.
- End with the user turn placeholder: `EVENT TEXT:\n{{event_text}}`.

**AC covered**: AC-001

---

### TASK-003: Ticker Extractor Prompt · S/no-TDD · prompts/classifiers/ticker_extractor.md

Write the `ticker_extractor.md` prompt file. The prompt must:
- Define the system role for Haiku 4.5 as a US equity ticker extractor.
- Specify the exact JSON output format: `{ "tickers": [...] }`.
- State that only NYSE and NASDAQ tickers are valid; implied exposures are acceptable.
- State that the response must be a valid JSON object with no surrounding prose or markdown.
- State that an empty array is the correct response when no companies are mentioned or implied.
- Include two examples: one event with explicit ticker mentions and one with implied sector exposure.
- End with the user turn placeholder: `EVENT TEXT:\n{{event_text}}`.

**AC covered**: AC-002, AC-003

---

### TASK-004: classify_event Step Implementation · M/TDD · src/events/steps/classify_event.py, tests/unit/events/steps/test_classify_event.py

Implement `classify_event` as an `async` function matching the signature in the Interfaces and
Contracts section. Implementation details:

1. Load prompt file from `prompt_path`; compute SHA-256 of file bytes for `prompt_version`.
2. Extract `event_text = ctx.raw_event.raw_payload.get("text", "")`. If empty string, raise
   `PipelineError("classify_event received empty event text")`.
3. Call `llm.complete(system_prompt, event_text, max_tokens=200, timeout_seconds=5.0)`.
   `system_prompt` is the full content of the prompt file with `{{event_text}}` interpolated.
4. Parse the returned content string as JSON; on `json.JSONDecodeError`, raise
   `PipelineError("classify_event: LLM returned non-JSON response")` — never propagate raw
   LLM output in exception messages.
5. Construct `ClassificationResult(**parsed_json)` using Pydantic; on `ValidationError`, raise
   `PipelineError("classify_event: response failed schema validation")`.
6. Start Langfuse span before the LLM call; end it after, recording `prompt_version`,
   `model="claude-haiku-4-5"`, `input_tokens`, `output_tokens`, `latency_ms`, `cost_usd`.
   Use `ILangfuseTracer` interface. Cost estimate: `(input_tokens * 0.00025 + output_tokens * 0.00125) / 1000`.
7. Add computed `cost_usd` to `ctx.cost_accumulator`; call `ctx.cost_accumulator.check_ceiling(0.05)`.
8. Set `ctx.classification = result`. Return updated `ctx`.

**Tests to write first (TDD)**:
- Valid LLM JSON response with all six fields produces a `ClassificationResult` stored on `ctx.classification`
- `intensity` outside [1, 5] in the LLM response raises `PipelineError` via Pydantic validation
- `sentiment` outside [-1.0, 1.0] in the LLM response raises `PipelineError` via Pydantic validation
- Malformed JSON from the LLM raises `PipelineError` without leaking raw LLM content
- A 5-second timeout from the LLM raises `StepTimeoutError` (propagated from `llm.complete`)
- Cost from the call is added to `ctx.cost_accumulator` and `check_ceiling` is called
- Langfuse `start_span` and `end_span` are each called exactly once with `prompt_version` set
- Empty `event_text` raises `PipelineError` before any LLM call is made

**AC covered**: AC-001, AC-004

---

### TASK-005: extract_tickers Step Implementation · M/TDD · src/events/steps/extract_tickers.py, tests/unit/events/steps/test_extract_tickers.py

Implement `extract_tickers` as an `async` function matching the signature in the Interfaces
and Contracts section. Implementation details:

1. Load prompt file from `prompt_path`; compute SHA-256 for `prompt_version`.
2. Extract `event_text = ctx.raw_event.raw_payload.get("text", "")`.
3. Call `llm.complete(system_prompt, event_text, max_tokens=100, timeout_seconds=3.0)`.
4. Parse returned content as JSON; on `json.JSONDecodeError`, raise
   `PipelineError("extract_tickers: LLM returned non-JSON response")`.
5. Construct `TickerExtractionResult(**parsed_json)` using Pydantic; on `ValidationError`,
   raise `PipelineError("extract_tickers: response failed schema validation")`.
6. An empty `tickers` list is valid; the step succeeds and stores `ctx.tickers = []`.
7. Start Langfuse span before the LLM call; end it after with the same fields as
   `classify_event`. Cost estimate: `(input_tokens * 0.00025 + output_tokens * 0.00125) / 1000`.
8. Add `cost_usd` to `ctx.cost_accumulator`; call `check_ceiling(0.05)`.
9. Set `ctx.tickers = result.tickers`. Return updated `ctx`.

**Tests to write first (TDD)**:
- Valid LLM JSON response with a populated tickers list stores the tickers on `ctx.tickers`
- Valid LLM JSON response with an empty `tickers` array stores `[]` on `ctx.tickers` — no error raised
- Malformed JSON from the LLM raises `PipelineError` without leaking raw LLM content
- A 3-second timeout from the LLM raises `StepTimeoutError` (propagated from `llm.complete`)
- Cost from the call is added to `ctx.cost_accumulator` and `check_ceiling` is called
- Langfuse `start_span` and `end_span` are each called exactly once with `prompt_version` set
- `TickerExtractionResult` validator rejects a ticker that is not a non-empty uppercase string

**AC covered**: AC-002, AC-003, AC-004

---

### TASK-006: Agent YAML — classify_event · S/no-TDD · agents/classify_event.yaml

Define the agent YAML for the `classify_event` step. This file governs the per-agent limits
that are enforced at runtime by the step implementation and referenced in AC-004. Content:

```yaml
agent_id: classify_event
model: claude-haiku-4-5
purpose: "Classify a raw geopolitical event into structured categories, intensity, sentiment, regions, sectors, and CAMEO code."
prompt_file: prompts/classifiers/event_classifier.md
limits:
  max_input_tokens: 2000
  max_output_tokens: 200
  timeout_seconds: 5
  cost_ceiling_usd: 0.002
output_schema: ClassificationResult
```

The step implementation reads `max_input_tokens` from this file to pre-truncate input if
necessary (implementation detail: compute approximate token count via `len(text.split()) * 1.3`;
if pre-truncation would result in loss, log a WARNING before truncating).

**AC covered**: AC-004

---

### TASK-007: Agent YAML — extract_tickers · S/no-TDD · agents/extract_tickers.yaml

Define the agent YAML for the `extract_tickers` step. Content:

```yaml
agent_id: extract_tickers
model: claude-haiku-4-5
purpose: "Extract NYSE/NASDAQ ticker symbols directly mentioned or implied by an event."
prompt_file: prompts/classifiers/ticker_extractor.md
limits:
  max_input_tokens: 1000
  max_output_tokens: 100
  timeout_seconds: 3
  cost_ceiling_usd: 0.001
output_schema: TickerExtractionResult
```

**AC covered**: AC-004

---

### TASK-008: Integration Test — classify_event and extract_tickers · M/TDD · tests/integration/events/steps/test_classification_extraction_integration.py

Write an integration test suite that exercises both steps together inside a minimal
`PipelineContext`, using mocked `ILLMClient` and `ILangfuseTracer` (via `pytest-mock`).
The tests must not make real API calls. No database dependency.

**Tests to write first (TDD)**:
- Both steps run sequentially on the same `PipelineContext`; classification is populated before extraction runs
- After both steps, `ctx.classification` is a fully valid `ClassificationResult` and `ctx.tickers` is a `list[str]`
- `ctx.cost_accumulator` reflects the combined cost of both LLM calls
- When classification times out, `PipelineError` is raised before `extract_tickers` is invoked (executor contract; test that `classify_event` propagates the error)
- When extraction returns an empty tickers list, the context carries `tickers=[]` and no exception is raised; downstream steps can proceed
- Langfuse spans are created and closed with `prompt_version` set to a non-empty SHA string for both steps

**AC covered**: AC-001, AC-002, AC-003, AC-004

---

## Acceptance Criteria Coverage

- AC-001: Given raw event text input, Haiku 4.5 returns a valid classification JSON with non-null category[], intensity in range 1–5, sentiment in range –1.0 to +1.0, geo_regions[], affected_sectors[], and cameo_code within 5 seconds → TASK-002, TASK-004, TASK-008
- AC-002: Given raw event text input, Haiku 4.5 returns a ticker extraction result (empty list permitted when no tickers are mentioned) within 3 seconds → TASK-001, TASK-003, TASK-005, TASK-008
- AC-003: Given an event with no mentions of specific companies, the extract_tickers call returns an empty list without error, and the pipeline continues → TASK-001, TASK-003, TASK-005, TASK-008
- AC-004: Given the agent YAML defines max_input_tokens and cost_ceiling_usd for the classification agent, the system enforces these limits and returns a structured error if exceeded rather than producing a truncated or overrun result → TASK-004, TASK-005, TASK-006, TASK-007, TASK-008

## Risks and Notes

- **Prompt file encoding and SHA stability:** The SHA-256 prompt version is computed on raw file bytes. Any whitespace or line-ending difference between operating systems (CRLF vs LF) will produce a different SHA. Enforce LF line endings in `.gitattributes` for all `prompts/` files to guarantee stable SHAs across developer machines and the CI container.
- **Input pre-truncation heuristic:** Token counting via `len(text.split()) * 1.3` is an approximation. If the system processes very long event texts (e.g. full SEC filings), a dedicated tokenizer (`tiktoken` or Anthropic's tokenizer) should replace the heuristic before going to production. For MVP with GDELT and Twitter inputs this approximation is acceptable.
- **Sentiment type mismatch:** The architecture (§10 data model) stores `sentiment` as a float on the `geo_event` table. The requirement data model specifies `float –1.0 to +1.0`. The `ClassificationResult.sentiment` field is typed as `float`, not `str`. If Haiku returns sentiment as a string (e.g. `"positive"`), the Pydantic validator will raise. The prompt must explicitly instruct the model to return a numeric float — this is covered in TASK-002.
- **Cost ceiling interaction:** Both steps share the same `CostAccumulator` on `PipelineContext` and both call `check_ceiling(0.05)` (the per-event ceiling). If `classify_event` alone costs close to $0.05 (which it cannot in practice at Haiku 4.5 pricing, but the guard is structural), `extract_tickers` will be blocked. This is correct behaviour per AC-004.
- **No direct DB access:** Neither step reads from or writes to the database. All structured outputs are stored on `PipelineContext` and persisted by the downstream `persist_event_record` step (PLAN-F-001 TASK-014). This plan owns no repository calls.
- **Langfuse unavailability:** The `ILangfuseTracer` implementation from PLAN-F-001 (TASK-009) is designed to swallow connectivity failures and log a warning. Both steps in this plan therefore do not need their own Langfuse error handling — the tracer interface is already resilient.
