---
plan_id: PLAN-F-005
slug: alert-dispatch-anti-fatigue
title: Alert Dispatch with Anti-Fatigue Controls
linked_requirement: REQ-F-005
type: functional
status: done
executed_at: 2026-06-03T00:00:00Z
blocked_reason:
complexity: L
tdd_required: true
linked_nfrs:
  - { id: REQ-N-001, reason: "evaluate_alert_rules ≤1s, dispatch_or_log_silent ≤2s (Mode A steps 9-10 SLAs)" }
  - { id: REQ-N-006, reason: "tenant_id isolation on all alert_rule and alert queries" }
dependencies:
  - { id: PLAN-F-001, reason: "Alert dispatch implements steps 9-10 of the Mode A pipeline; IAlertRuleEvaluator and IAlertDispatcher interface stubs are defined in PLAN-F-001" }
executed_at:
reviewed_at:
review_id:
created_at: 2026-06-02T00:00:00Z
updated_at: 2026-06-02T00:00:00Z
---

# PLAN-F-005 — Alert Dispatch with Anti-Fatigue Controls

## Linked Requirement
**REQ-F-005** — Alert Dispatch with Anti-Fatigue Controls
Status: approved | Jira: —

## Objective

Build the `alerts` backend module with full implementations of the `IAlertRuleEvaluator` and `IAlertDispatcher` interfaces stubbed in PLAN-F-001. The module evaluates per-user `alert_rule` rows against incoming events, applies a four-gate anti-fatigue control chain (daily limit, quiet hours, per-ticker re-alert interval, deduplication window) and a budget enforcement gate (daily_budget_usd, hard_stop_pct), generates an ~80-word alert text via Sonnet 4.6 (step 8 delegate), dispatches passing alerts via SendGrid email, writes suppressed alerts as silent-log rows with an explicit status enum, and conditionally enqueues the Mode B Event Deep-Dive Celery job when intensity ≥ 4 or a portfolio company match is present (step 11 delegate). All anti-fatigue counters are stored and queried via the repository layer, never directly from service code. Both steps meet their Mode A SLAs: rule evaluation ≤1s, dispatch/log ≤2s.

## Architecture Context

This plan lives entirely in the `alerts` backend module (Architecture §5). It replaces the interface stubs created in PLAN-F-001 with concrete implementations and adds the repository layer, alert-text generation, and email dispatch.

Layer contacts (Architecture §4):

- **Layer 3 — Storage:** New `IAlertRuleRepository` and `IAlertRepository` interfaces and their SQLAlchemy 2.0 async implementations. All queries carry `tenant_id` in the WHERE clause (Architecture §12.3, Principle 3). Counter state (daily alert counts, last-alert timestamps per ticker) is read from the `alert` table directly — no separate counter table.
- **Layer 4 — Processing:** `AlertRuleEvaluator` service owns the five-gate evaluation chain. `AlertTextGenerator` service owns the Sonnet 4.6 call (step 8 of Mode A). `BudgetEnforcer` service reads budget settings from `user.settings JSONB`. `DeepDiveEnqueuer` service wraps Celery task enqueue for the Mode B handoff.
- **Layer 5 — Serving:** `AlertDispatcher` service calls the SendGrid API via an `IEmailSender` interface (swappable). All outbound email calls go through this interface per Architecture Principle 1.
- **Layer 4 → Layer 5 consumer:** The `PipelineExecutor` in `src/events/` calls `IAlertRuleEvaluator.evaluate` (step 9) and `IAlertDispatcher.dispatch` / `IAlertDispatcher.log_silent` (step 10) through the interfaces defined in PLAN-F-001. This plan fulfils those contracts.

New module layout:

```
src/alerts/
  interfaces/
    i_alert_rule_evaluator.py    — already defined in PLAN-F-001 (do not redefine)
    i_alert_dispatcher.py        — already defined in PLAN-F-001 (do not redefine)
    i_alert_rule_repository.py   — new
    i_alert_fatigue_repository.py — new
    i_email_sender.py            — new
  services/
    alert_rule_evaluator.py      — implements IAlertRuleEvaluator
    alert_text_generator.py      — Sonnet 4.6 alert text (step 8 delegate)
    budget_enforcer.py           — daily budget + hard-stop check
    anti_fatigue_checker.py      — four-gate anti-fatigue logic
    alert_dispatcher.py          — implements IAlertDispatcher
    deep_dive_enqueuer.py        — conditional Mode B Celery enqueue
  repositories/
    alert_rule_repository.py     — implements IAlertRuleRepository
    alert_repository.py          — implements IAlertFatigueRepository + write path
  integrations/
    sendgrid_email_sender.py     — implements IEmailSender via SendGrid
  models.py                      — AlertRuleRow, AlertRow, AntiFatigueState, BudgetState,
                                   AlertTextResult, DispatchDecision
  exceptions.py                  — AlertDispatchError, BudgetHardStopError, SendGridError
```

Decision D6 (Anthropic-only MVP, Sonnet 4.6 for alert text) and D11 (modular monolith, interface boundaries) are binding. Architecture Principle 1 mandates the `IEmailSender` abstraction for SendGrid.

## Applied NFR Constraints

| NFR | Constraint | Impact on this plan |
|-----|-----------|---------------------|
| REQ-N-001 | `evaluate_alert_rules` ≤1s end-to-end; `dispatch_or_log_silent` ≤2s | `AlertRuleEvaluator.evaluate` is a pure DB + in-memory chain; single query per gate using indexed columns. `AlertDispatcher` runs SendGrid HTTP call with a 1.5s timeout; silent-log path is a single DB insert. |
| REQ-N-006 | tenant_id isolation on all alert_rule and alert queries | Every repository method accepts `tenant_id` as a required parameter and includes it in all WHERE clauses. No cross-tenant data leakage possible at the query level. |

## Component Design

### New Components

```
Module: alerts (src/alerts/)

  interfaces/
    IAlertRuleRepository
      get_active_rules(tenant_id) -> list[AlertRuleRow]

    IAlertFatigueRepository
      count_dispatched_today(user_id, tenant_id) -> int
      get_last_dispatch_for_ticker(user_id, ticker, tenant_id) -> datetime | None
      get_recent_dispatches_for_event(event_id, user_id, tenant_id, window_minutes) -> list[UUID]

    IEmailSender
      send(to_email, subject, html_body) -> None

  services/
    AlertRuleEvaluator       — implements IAlertRuleEvaluator
    AlertTextGenerator       — Sonnet 4.6 structured output call
    AntiFatigueChecker       — stateless; receives AntiFatigueState; returns suppression reason or None
    BudgetEnforcer           — reads user.settings JSONB; stateless check
    AlertDispatcher          — implements IAlertDispatcher
    DeepDiveEnqueuer         — wraps workflow_queue.enqueue for Mode B

  repositories/
    AlertRuleRepository      — implements IAlertRuleRepository
    AlertRepository          — implements IAlertFatigueRepository + insert_alert + insert_silent_log

  integrations/
    SendGridEmailSender      — implements IEmailSender
```

### Modified Components

| File | Change | Reason |
|------|--------|--------|
| `src/alerts/interfaces/i_alert_rule_evaluator.py` | Add `user_id` to `RuleMatch`; expand return to `list[RuleMatch]` | PLAN-F-001 stub used a minimal signature; full implementation needs per-user matches |
| `src/alerts/interfaces/i_alert_dispatcher.py` | Add `AlertDispatchResult` return type to `dispatch`; add `suppression_status` arg to `log_silent` | Caller needs confirmation of channel and alert_id for pipeline result |
| `src/config/settings.py` | Add `SENDGRID_API_KEY`, `SENDGRID_FROM_EMAIL` env vars | Email dispatch config |
| `src/config/celery_app.py` | Register `enqueue_deep_dive_task` from `src/alerts/` | Mode B handoff |

### Interfaces and Contracts

```python
# src/alerts/models.py

from enum import Enum
from uuid import UUID
from datetime import datetime, time
from pydantic import BaseModel

class ActionSignal(str, Enum):
    HOLD = "HOLD"
    WATCH = "WATCH"
    BUY_OPP = "BUY_OPP"
    REDUCE_RISK = "REDUCE_RISK"
    HEDGE = "HEDGE"
    CONTRARIAN = "CONTRARIAN"

class AlertStatus(str, Enum):
    DISPATCHED = "dispatched"
    SUPPRESSED_DAILY_LIMIT = "suppressed_daily_limit"
    SUPPRESSED_QUIET_HOURS = "suppressed_quiet_hours"
    SUPPRESSED_DEDUP = "suppressed_dedup"
    SUPPRESSED_BUDGET = "suppressed_budget"
    SUPPRESSED_TICKER_INTERVAL = "suppressed_ticker_interval"

class AlertRuleRow(BaseModel):
    rule_id: UUID
    tenant_id: UUID
    user_id: UUID
    user_email: str
    event_categories: list[str]     # empty = all categories
    intensity_min: int              # 1–5
    ticker_list: list[str]          # empty = all portfolio tickers
    quiet_hours_start: time | None
    quiet_hours_end: time | None
    daily_limit: int                # default 5
    dedup_window_minutes: int       # default 60
    per_ticker_interval_hours: int  # default 24
    enabled: bool

class AlertTextResult(BaseModel):
    alert_text: str                 # ~80 words
    action_signal: ActionSignal
    confidence: float               # 0–1
    sample_size: int
    low_sample_disclaimer: bool     # true when sample_size < 5

class AntiFatigueState(BaseModel):
    dispatched_today: int
    last_ticker_dispatch: datetime | None
    recent_event_alert_ids: list[UUID]  # within dedup_window_minutes

class BudgetState(BaseModel):
    daily_budget_usd: float
    spent_today_usd: float
    alert_threshold_pct: float      # 80% default
    hard_stop_pct: float            # 100% default

class DispatchDecision(BaseModel):
    should_dispatch: bool
    suppression_status: AlertStatus | None
    alert_row: "AlertRow | None"    # set after DB write

class AlertRow(BaseModel):
    alert_id: UUID
    event_id: UUID
    user_id: UUID
    tenant_id: UUID
    rule_id: UUID
    alert_text: str
    action_signal: ActionSignal
    confidence: float
    sample_size: int
    dispatched_at: datetime | None
    channel: str                    # "email" | "silent"
    cost_usd: float
    status: AlertStatus


# src/alerts/interfaces/i_alert_rule_repository.py

class IAlertRuleRepository(Protocol):
    async def get_active_rules(self, tenant_id: UUID) -> list[AlertRuleRow]: ...


# src/alerts/interfaces/i_alert_fatigue_repository.py

class IAlertFatigueRepository(Protocol):
    async def count_dispatched_today(
        self, user_id: UUID, tenant_id: UUID
    ) -> int: ...

    async def get_last_dispatch_for_ticker(
        self, user_id: UUID, ticker: str, tenant_id: UUID
    ) -> datetime | None: ...

    async def get_recent_event_alert_ids(
        self, event_id: UUID, user_id: UUID, tenant_id: UUID, window_minutes: int
    ) -> list[UUID]: ...


# src/alerts/interfaces/i_email_sender.py

class IEmailSender(Protocol):
    async def send(
        self, to_email: str, subject: str, html_body: str
    ) -> None: ...


# src/alerts/interfaces/i_alert_rule_evaluator.py  (extended from PLAN-F-001)

class RuleMatch(BaseModel):
    rule_id: UUID
    user_id: UUID
    user_email: str
    tenant_id: UUID
    channels: list[str]
    matched_tickers: list[str]

class IAlertRuleEvaluator(Protocol):
    async def evaluate(
        self,
        event_id: UUID,
        intensity: int,
        categories: list[str],
        matched_tickers: list[str],
        tenant_id: UUID | None,
    ) -> list[RuleMatch]: ...


# src/alerts/interfaces/i_alert_dispatcher.py  (extended from PLAN-F-001)

class AlertDispatchResult(BaseModel):
    alert_id: UUID
    status: AlertStatus
    channel: str

class IAlertDispatcher(Protocol):
    async def dispatch(
        self,
        rule_match: RuleMatch,
        alert_text_result: AlertTextResult,
        event_id: UUID,
    ) -> AlertDispatchResult: ...

    async def log_silent(
        self,
        event_id: UUID,
        tenant_id: UUID | None,
        suppression_status: AlertStatus,
    ) -> None: ...
```

## Implementation Tasks

### TASK-001: Domain Models and Exceptions · S/no-TDD · src/alerts/models.py, src/alerts/exceptions.py

Define all Pydantic models for the `alerts` module as specified in the Interfaces and Contracts section: `AlertRuleRow`, `AlertTextResult`, `AntiFatigueState`, `BudgetState`, `DispatchDecision`, `AlertRow`, `ActionSignal` enum, `AlertStatus` enum. Define `AlertDispatchError`, `BudgetHardStopError`, `SendGridError` exceptions. Each exception carries a `user_id: UUID | None` and `event_id: UUID | None` field for log correlation.

**AC covered**: enables AC-002, AC-003, AC-005, AC-006

---

### TASK-002: Alert Rule and Fatigue Repository Interfaces · S/no-TDD · src/alerts/interfaces/i_alert_rule_repository.py, src/alerts/interfaces/i_alert_fatigue_repository.py, src/alerts/interfaces/i_email_sender.py

Define `IAlertRuleRepository`, `IAlertFatigueRepository`, and `IEmailSender` as `typing.Protocol` classes exactly as specified in the Interfaces and Contracts section. Use `runtime_checkable` decorator. Each interface lives in its own file. Extend the existing `IAlertRuleEvaluator` (add `user_email`, `matched_tickers` to `RuleMatch`) and `IAlertDispatcher` (add `AlertDispatchResult`, `suppression_status` to `log_silent`) in their existing files from PLAN-F-001; do not create new files for those.

**AC covered**: enables AC-001, AC-002, AC-003, AC-004, AC-006

---

### TASK-003: Alert Rule Repository Implementation · M/TDD · src/alerts/repositories/alert_rule_repository.py, tests/unit/alerts/test_alert_rule_repository.py

Implement `AlertRuleRepository` satisfying `IAlertRuleRepository`. `get_active_rules(tenant_id)` queries the `alert_rule` table with `WHERE tenant_id = :tenant_id AND enabled = true`, joins to `user` for `user_email`, and returns a list of `AlertRuleRow`. Use SQLAlchemy 2.0 async session. All columns must be read in a single query (no N+1). Index assumed on `(tenant_id, enabled)`.

**Tests to write first (TDD)**:
- `get_active_rules` returns only rules where `enabled=true` for the given tenant
- `get_active_rules` returns an empty list when no rules exist for the tenant
- `get_active_rules` does not return rules belonging to a different `tenant_id`
- `user_email` is correctly populated from the joined `user` row
- Resulting `AlertRuleRow` objects match all schema fields

**AC covered**: AC-001, AC-002, AC-003

---

### TASK-004: Alert Fatigue and Write Repository Implementation · M/TDD · src/alerts/repositories/alert_repository.py, tests/unit/alerts/test_alert_repository.py

Implement `AlertRepository` satisfying both `IAlertFatigueRepository` and the write methods (`insert_alert`, `insert_silent_log`) required by `IAlertRepository` (from PLAN-F-001). Methods:

- `count_dispatched_today(user_id, tenant_id) -> int` — counts `alert` rows where `status = 'dispatched'`, `user_id = :user_id`, `tenant_id = :tenant_id`, and `dispatched_at >= current UTC date midnight`.
- `get_last_dispatch_for_ticker(user_id, ticker, tenant_id) -> datetime | None` — returns `MAX(dispatched_at)` for alerts where `alert_text ILIKE '%{ticker}%'` OR `matched_tickers` contains ticker in metadata; use a `company_id` join via the `event_exposure` table for correctness (join on `event_id`).
- `get_recent_event_alert_ids(event_id, user_id, tenant_id, window_minutes) -> list[UUID]` — returns `alert_id` values for alerts where `event_id = :event_id`, `user_id = :user_id`, `tenant_id = :tenant_id`, and `dispatched_at >= NOW() - interval ':window_minutes minutes'`.
- `insert_alert(alert_row: AlertRow) -> UUID` — inserts into the `alert` table, returns `alert_id`.
- `insert_silent_log(event_id, user_id, tenant_id, rule_id, status: AlertStatus) -> None` — inserts a minimal `alert` row with `channel='silent'` and the given `status`.

All queries include `tenant_id` in WHERE clauses.

**Tests to write first (TDD)**:
- `count_dispatched_today` returns 0 for a user with no alerts today
- `count_dispatched_today` counts only today's dispatched alerts, not yesterday's
- `count_dispatched_today` does not count silent-logged alerts
- `get_last_dispatch_for_ticker` returns `None` when no prior alert exists for that ticker
- `get_last_dispatch_for_ticker` returns the most recent `dispatched_at` when alerts exist
- `get_recent_event_alert_ids` respects the `window_minutes` cutoff
- `get_recent_event_alert_ids` returns an empty list when no alerts exist within the window
- `insert_alert` persists all fields correctly and returns a valid UUID
- `insert_silent_log` creates a row with `channel='silent'` and correct `status`
- No method returns data for a different `tenant_id`

**AC covered**: AC-002, AC-003, AC-006

---

### TASK-005: Anti-Fatigue Checker Service · M/TDD · src/alerts/services/anti_fatigue_checker.py, tests/unit/alerts/test_anti_fatigue_checker.py

Implement `AntiFatigueChecker` as a stateless service. Constructor accepts no dependencies (pure logic). Single public method:

```python
def check(
    self,
    rule: AlertRuleRow,
    fatigue_state: AntiFatigueState,
    event_time_utc: datetime,
    matched_tickers: list[str],
) -> AlertStatus | None:
```

Returns `None` if all gates pass (alert should proceed), or the first failing `AlertStatus` in evaluation order:

1. **Daily limit gate:** `fatigue_state.dispatched_today >= rule.daily_limit` → `SUPPRESSED_DAILY_LIMIT`
2. **Quiet hours gate:** `event_time_utc` (converted to UTC) falls within `[rule.quiet_hours_start, rule.quiet_hours_end)` → `SUPPRESSED_QUIET_HOURS`. Handles overnight ranges (e.g. 22:00–06:00) by checking if start > end.
3. **Per-ticker interval gate:** For each ticker in `matched_tickers`, if `fatigue_state.last_ticker_dispatch` is not None and `event_time_utc - last_ticker_dispatch < timedelta(hours=rule.per_ticker_interval_hours)` → `SUPPRESSED_TICKER_INTERVAL`
4. **Deduplication gate:** `len(fatigue_state.recent_event_alert_ids) > 0` → `SUPPRESSED_DEDUP`

**Tests to write first (TDD)**:
- All gates pass → returns `None`
- `dispatched_today` equals `daily_limit` → `SUPPRESSED_DAILY_LIMIT`
- `dispatched_today` is below `daily_limit` → gate passes
- Event time within quiet hours (same day range) → `SUPPRESSED_QUIET_HOURS`
- Event time within quiet hours (overnight range, e.g. 22:00–06:00) → `SUPPRESSED_QUIET_HOURS`
- Event time outside quiet hours → gate passes
- Ticker last dispatched 2 hours ago with 24-hour interval → `SUPPRESSED_TICKER_INTERVAL`
- Ticker last dispatched 25 hours ago with 24-hour interval → gate passes
- Recent event alert IDs non-empty → `SUPPRESSED_DEDUP`
- Recent event alert IDs empty → gate passes
- Gates evaluated in order: daily limit checked before quiet hours

**AC covered**: AC-002, AC-003

---

### TASK-006: Budget Enforcer Service · M/TDD · src/alerts/services/budget_enforcer.py, tests/unit/alerts/test_budget_enforcer.py

Implement `BudgetEnforcer` as a stateless service:

```python
def check(self, budget_state: BudgetState) -> AlertStatus | None:
```

Returns `None` if budget allows dispatch. Returns `SUPPRESSED_BUDGET` if `(spent_today_usd / daily_budget_usd) * 100 >= hard_stop_pct`. Raises `BudgetHardStopError` (does not swallow) so the pipeline can log the event. `BudgetHardStopError` carries `user_id`, `spent_today_usd`, `daily_budget_usd`.

`BudgetState` is populated by the caller from `user.settings JSONB` fields: `daily_budget_usd`, `daily_alert_threshold_pct` (80 default), `daily_hard_stop_pct` (100 default). The `BudgetEnforcer` reads `settings` via a dedicated repository method `get_budget_state(user_id, tenant_id) -> BudgetState`.

Add to `IAlertFatigueRepository`:
```python
async def get_budget_state(self, user_id: UUID, tenant_id: UUID) -> BudgetState: ...
async def get_spent_today_usd(self, user_id: UUID, tenant_id: UUID) -> float: ...
```

Add corresponding implementations to `AlertRepository` (TASK-004 extended).

**Tests to write first (TDD)**:
- `spent / budget * 100 < hard_stop_pct` → returns `None`
- `spent / budget * 100 >= hard_stop_pct` → returns `SUPPRESSED_BUDGET`
- Zero `daily_budget_usd` → raises `BudgetHardStopError` (divide-by-zero guard)
- `hard_stop_pct` of 100 means fully spending budget triggers suppression
- `hard_stop_pct` of 80 triggers at 80% spend

**AC covered**: AC-006

---

### TASK-007: Alert Text Generator · M/TDD · src/alerts/services/alert_text_generator.py, prompts/alerts/alert_text_generator.md, tests/unit/alerts/test_alert_text_generator.py

Implement `AlertTextGenerator` service. Constructor accepts `ILLMClient` (Sonnet 4.6). Single public method:

```python
async def generate(
    self,
    event_title: str,
    intensity: int,
    analogies: list[dict],
    exposed_company_count: int,
    tenant_id: UUID,
    tracer: ILangfuseTracer,
) -> AlertTextResult:
```

Loads the prompt template from `prompts/alerts/alert_text_generator.md`. Calls `ILLMClient.complete` with Sonnet 4.6, `max_tokens=200`, `timeout_seconds=8.0`. Parses the structured JSON response into `AlertTextResult`. Sets `low_sample_disclaimer = True` when `sample_size < 5`. Records a Langfuse span with model, token counts, latency, and cost. Raises `AlertDispatchError` (wrapping raw LLM exception) on parse failure or timeout — never propagates raw API errors to callers.

Write `prompts/alerts/alert_text_generator.md`: system prompt must instruct Sonnet 4.6 to return a JSON object with fields `alert_text` (~80 words), `action_signal` (one of HOLD/WATCH/BUY_OPP/REDUCE_RISK/HEDGE/CONTRARIAN), `confidence` (0–1 float), `sample_size` (int). The alert text must include: event headline, intensity indicator, number of holdings exposed, AI one-word action signal, confidence level, and analogies citation.

**Tests to write first (TDD)**:
- Valid JSON response parsed into `AlertTextResult` with all required fields
- `sample_size < 5` sets `low_sample_disclaimer = True`
- `sample_size >= 5` sets `low_sample_disclaimer = False`
- LLM timeout raises `AlertDispatchError` (not `StepTimeoutError` leaking through)
- Malformed JSON from LLM raises `AlertDispatchError` (not raw parse error)
- Langfuse span is started and ended with correct model tag and token counts
- `action_signal` value not in enum raises `AlertDispatchError`

**AC covered**: AC-001, AC-005

---

### TASK-008: Alert Rule Evaluator Service · M/TDD · src/alerts/services/alert_rule_evaluator.py, tests/unit/alerts/test_alert_rule_evaluator.py

Implement `AlertRuleEvaluator` satisfying `IAlertRuleEvaluator`. Constructor accepts `IAlertRuleRepository`.

```python
async def evaluate(
    self,
    event_id: UUID,
    intensity: int,
    categories: list[str],
    matched_tickers: list[str],
    tenant_id: UUID | None,
) -> list[RuleMatch]:
```

Logic:
1. Call `repo.get_active_rules(tenant_id)`.
2. For each rule: check `intensity >= rule.intensity_min`; if `rule.event_categories` is non-empty, verify at least one category matches; if `rule.ticker_list` is non-empty, verify at least one ticker matches.
3. Collect all matching rules as `RuleMatch` instances with `matched_tickers` populated.
4. Return the list (may be empty if no rules match).

The entire method must complete in ≤1s per REQ-N-001 — enforced by the single DB query in the repository.

**Tests to write first (TDD)**:
- Rule with `intensity_min=3` matches event with `intensity=3`
- Rule with `intensity_min=3` does not match event with `intensity=2`
- Rule with `event_categories=[]` matches any event category
- Rule with `event_categories=["conflict"]` does not match event with `categories=["trade"]`
- Rule with `ticker_list=[]` matches regardless of `matched_tickers`
- Rule with `ticker_list=["AAPL"]` matches only when "AAPL" is in `matched_tickers`
- Returns empty list when `get_active_rules` returns no rows
- Returns multiple `RuleMatch` objects when multiple rules match
- `tenant_id=None` is passed through to `get_active_rules` without error

**AC covered**: AC-001, AC-002, AC-003

---

### TASK-009: SendGrid Email Sender · S/no-TDD · src/alerts/integrations/sendgrid_email_sender.py

Implement `SendGridEmailSender` satisfying `IEmailSender`. Constructor accepts `api_key: str`, `from_email: str`. `send(to_email, subject, html_body)` calls the SendGrid v3 Mail Send API (`POST /v3/mail/send`) using the `sendgrid` Python SDK. Enforces a 1.5-second HTTP timeout (injected via `httpx` client or SDK timeout parameter). On HTTP 4xx/5xx, raises `SendGridError` with status code but never the API key. Never logs the API key or recipient email address at ERROR level; log at DEBUG only with PII masked.

**AC covered**: AC-001

---

### TASK-010: Alert Dispatcher Service · M/TDD · src/alerts/services/alert_dispatcher.py, tests/unit/alerts/test_alert_dispatcher.py

Implement `AlertDispatcher` satisfying `IAlertDispatcher`. Constructor accepts `IAlertFatigueRepository`, `IAlertFatigueRepository` (budget state), `AntiFatigueChecker`, `BudgetEnforcer`, `AlertTextGenerator`, `IEmailSender`, `IAlertRuleRepository` (for `user_email` lookup already on `RuleMatch`), and a write-capable `AlertRepository`.

`dispatch(rule_match, alert_text_result, event_id) -> AlertDispatchResult`:

1. Load `AntiFatigueState` from repository.
2. Load `BudgetState` from repository.
3. Run `AntiFatigueChecker.check(...)` — if suppressed, call `insert_silent_log` and return `AlertDispatchResult(status=suppression_status, channel="silent")`.
4. Run `BudgetEnforcer.check(...)` — if suppressed, call `insert_silent_log(status=SUPPRESSED_BUDGET)` and return.
5. Build `AlertRow` with `channel="email"`, `status=AlertStatus.DISPATCHED`.
6. Call `IEmailSender.send(...)` with the alert text as HTML body.
7. Call `insert_alert(alert_row)` and return `AlertDispatchResult(status=DISPATCHED, channel="email", alert_id=...)`.

If `IEmailSender.send` raises `SendGridError`, insert `alert` row with `channel='email'`, `status=SUPPRESSED_BUDGET` is wrong here — raise `AlertDispatchError` so the pipeline step can decide whether to retry or log.

`log_silent(event_id, tenant_id, suppression_status)` — delegates directly to `AlertRepository.insert_silent_log`.

The whole `dispatch` path must complete in ≤2s per REQ-N-001.

**Tests to write first (TDD)**:
- Anti-fatigue suppression returns `SUPPRESSED_DAILY_LIMIT` and calls `insert_silent_log`; `IEmailSender.send` is never called
- Budget suppression returns `SUPPRESSED_BUDGET` and calls `insert_silent_log`; `IEmailSender.send` is never called
- All gates pass: `IEmailSender.send` is called with correct `to_email`, `subject`, `html_body`
- All gates pass: `insert_alert` is called with `status=DISPATCHED`, `channel='email'`
- `SendGridError` during send raises `AlertDispatchError`; no silent-log row inserted (caller decides)
- `low_sample_disclaimer=True` on `AlertTextResult` results in disclaimer text in `html_body`
- `log_silent` inserts correct suppression status

**AC covered**: AC-001, AC-002, AC-003, AC-005, AC-006

---

### TASK-011: Deep Dive Enqueuer · S/no-TDD · src/alerts/services/deep_dive_enqueuer.py

Implement `DeepDiveEnqueuer` service. Constructor accepts a `WorkflowQueue` interface (from `src/events/` or shared infrastructure). Single method:

```python
async def maybe_enqueue(
    self,
    event_id: UUID,
    intensity: int,
    has_portfolio_match: bool,
    tenant_id: UUID,
) -> bool:
```

Enqueues a Mode B `event_deep_dive` Celery task when `intensity >= 4` or `has_portfolio_match is True`, using `scheduled_for = now() + timedelta(minutes=2)`. Returns `True` if enqueued, `False` otherwise. Uses the same `workflow_queue.enqueue(...)` signature as the architecture's step-11 code sample (Architecture §6). This step must complete in <1s.

**AC covered**: AC-004

---

### TASK-012: Pipeline Integration Wiring · S/no-TDD · src/alerts/__init__.py, src/config/settings.py

Wire the `alerts` module's concrete implementations into the pipeline:

- Export `AlertRuleEvaluator` and `AlertDispatcher` from `src/alerts/__init__.py` so the `PipelineExecutor` in `src/events/` can import them via the interface only.
- Add `SENDGRID_API_KEY` and `SENDGRID_FROM_EMAIL` to `src/config/settings.py` (Pydantic Settings model); fail-fast on missing vars at startup.
- Add a factory function `create_alert_rule_evaluator(session) -> IAlertRuleEvaluator` and `create_alert_dispatcher(session, llm_client, tracer) -> IAlertDispatcher` that assemble the concrete dependency graph. The `PipelineExecutor` calls these factories — it never instantiates `alerts` internals directly.

**AC covered**: enables AC-001 through AC-006

---

### TASK-013: End-to-End Integration Test for Steps 9-10 · L/TDD · tests/integration/alerts/test_alert_pipeline_integration.py

Write integration tests covering steps 9–10 of the Mode A pipeline against a real test database (transaction-isolated, rolled back after each test). Use a real `AlertRuleRepository` and `AlertRepository` against the test DB. Mock only `ILLMClient` (Sonnet 4.6 call) and `IEmailSender` (SendGrid).

**Tests to write first (TDD)**:
- Full happy path: rule matches, all anti-fatigue gates pass, budget allows — alert row inserted with `status=DISPATCHED`, `IEmailSender.send` called once
- Daily limit reached: alert row inserted with `status=SUPPRESSED_DAILY_LIMIT`, `send` not called
- Quiet hours active: alert row inserted with `status=SUPPRESSED_QUIET_HOURS`, `send` not called
- Per-ticker interval active: alert row inserted with `status=SUPPRESSED_TICKER_INTERVAL`, `send` not called
- Deduplication window active: alert row inserted with `status=SUPPRESSED_DEDUP`, `send` not called
- Hard stop budget reached: alert row inserted with `status=SUPPRESSED_BUDGET`, `send` not called
- `sample_size < 5`: dispatched alert HTML body contains low-sample disclaimer
- No rules match: zero alert rows inserted, `send` not called
- `tenant_id` isolation: rule from tenant A not evaluated for event from tenant B
- Step 9 (`evaluate_alert_rules`) completes in ≤1s measured wall-clock
- Step 10 (`dispatch_or_log_silent`) with mocked SendGrid completes in ≤2s measured wall-clock

**AC covered**: AC-001, AC-002, AC-003, AC-005, AC-006

---

## Acceptance Criteria Coverage

- AC-001: Alert text generated by Sonnet 4.6 (~80 words, ≤8s, with confidence/sample_size/action_signal) → TASK-007, TASK-010, TASK-013
- AC-002: User at daily_push_limit → silent log, no email → TASK-004, TASK-005, TASK-010, TASK-013
- AC-003: Alert within quiet_hours → suppressed (silent log), not dispatched → TASK-005, TASK-010, TASK-013
- AC-004: intensity ≥ 4 or portfolio match → Mode B deep-dive Celery job enqueued within pipeline window → TASK-011
- AC-005: sample_size < 5 → low-sample disclaimer in alert text before dispatch → TASK-007, TASK-010, TASK-013
- AC-006: daily_hard_stop_pct reached → no further alerts for that user for the day → TASK-006, TASK-010, TASK-013

## Risks and Notes

- The `alert` table schema in Architecture §10 omits `user_id`, `action_signal`, `sample_size`, and `status` columns that the requirement's data model requires. The implementation must use the requirement's extended schema (`alert` table as defined in REQ-F-005 §Data Models). A database migration is required.
- The `alert_rule` table in Architecture §10 uses a different column shape than the requirement (requirement adds `user_id`, `event_categories`, `ticker_list`, `quiet_hours_start/end`, `dedup_window_minutes`, `per_ticker_interval_hours`; architecture uses `alert_type`, `min_intensity`, `scope JSONB`, `channels JSONB`, `quiet_hours JSONB`). This plan uses the requirement schema as authoritative (per D10: system_description.md is authoritative for functional requirements). The migration must reconcile these columns.
- SendGrid free tier imposes a daily sending limit (100 emails/day on free plan). At MVP scale this is acceptable; the `IEmailSender` abstraction allows a swap to a paid tier or alternative provider with no business logic change.
- The Sonnet 4.6 call in `AlertTextGenerator` (step 8 of Mode A) adds up to 8 seconds to the pipeline. Combined with the ≤1s (step 9) and ≤2s (step 10) SLAs, this is within the 60-second processing budget and 90-second end-to-end SLA.
- `get_last_dispatch_for_ticker` joins through `event_exposure` to match tickers via `company_id`. This assumes `event_exposure` is populated before step 9 runs (it is — step 5 persists it). The join must be index-assisted; ensure `(user_id, company_id)` index exists on the `alert` table.
- Anti-fatigue state is loaded per user in the dispatcher, meaning N rules produces N sets of DB reads. At MVP scale (one tenant, few users) this is acceptable. Batch-load optimisation can be added without interface changes.
