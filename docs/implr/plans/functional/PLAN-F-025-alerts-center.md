---
plan_id: PLAN-F-025
slug: alerts-center
title: Alerts Center
linked_requirement: REQ-F-025
type: functional
status: done
blocked_reason:
complexity: M
tdd_required: true
linked_nfrs:
  - { id: REQ-N-006, reason: "tenant_id isolation on all alert and alert_rule queries; ownership check on every rule mutation" }
dependencies:
  - { id: PLAN-F-005, reason: "alert and alert_rule rows are persisted by PLAN-F-005; this plan adds the UI/API management layer on top" }
executed_at: 2026-06-04T00:00:00Z
reviewed_at:
review_id:
created_at: 2026-06-02T00:00:00Z
updated_at: 2026-06-02T00:00:00Z
---

# PLAN-F-025 — Alerts Center

## Linked Requirement
**REQ-F-025** — Alerts Center
Status: approved | Jira: —

## Objective

Build the Alerts Center: a FastAPI REST layer and React 18 + TypeScript frontend that
exposes a paginated, filterable chronological list of fired alerts with deep-links back to
originating map events or reports, and a full CRUD management surface for `alert_rule` rows
covering intensity thresholds, event-category filters, ticker lists, quiet hours, per-ticker
frequency limits, and notification channels. Anti-fatigue global settings (daily push limit,
overall quiet hours, deduplication window) stored in `user.settings JSONB` are surfaced and
editable in the same screen. All mutations enforce authenticated user ownership; all queries
include `tenant_id` in their WHERE clauses.

## Architecture Context

This plan spans Layer 5 (Serving) and Layer 6 (Presentation), reading data written by
PLAN-F-005 in Layer 3 (Storage).

- **Architecture §5 — Backend Module Map (`alerts` module):** New router and read-path
  service added to `src/alerts/`. PLAN-F-005 owns the write path (rule evaluation,
  dispatching, inserting `alert` rows). This plan adds `GET /api/v1/alerts`,
  `GET /api/v1/alert-rules`, `POST/PATCH/DELETE /api/v1/alert-rules/{rule_id}`, and
  `PATCH /api/v1/settings/anti-fatigue` using the repository layer already established.
- **Architecture §10 — Data Model:** Reads `alert` and `alert_rule` tables. The `alert`
  table carries `event_id` (join to `geo_event` for `lat`, `lon`, title, and deep-link
  coordinates) and an optional `report_id` (join to future report table; nullable now).
- **Architecture §11 — Frontend:** React 18 + TypeScript, TanStack Query for server state,
  MapLibre GL JS deep-link via a URL parameter (`/map?event={event_id}&lat=…&lon=…`).
- **Architecture §12.1 — Auth:** JWT `Bearer` token required on all endpoints. Rule
  mutations verify `alert_rule.user_id == authenticated user_id` before any write.
- **Architecture §12.3 — Multi-Tenancy:** Every repository query carries `tenant_id` in
  the WHERE clause. No cross-tenant data is reachable.

## Applied NFR Constraints

| NFR | Constraint | Impact on this plan |
|-----|-----------|---------------------|
| REQ-N-006 | tenant_id on all queries; resource ownership verified per lookup | All repository methods require `tenant_id`; rule mutations check `user_id` ownership before applying changes |

## Component Design

### New Components

```
Backend — src/alerts/
  api/
    alerts_router.py          — GET /api/v1/alerts (paginated, filterable)
    alert_rules_router.py     — GET/POST /api/v1/alert-rules,
                                PATCH/DELETE /api/v1/alert-rules/{rule_id}
    anti_fatigue_router.py    — GET/PATCH /api/v1/settings/anti-fatigue
  services/
    alerts_reader.py          — read-path service: list alerts with event deep-link URLs
    alert_rule_manager.py     — CRUD service: create/edit/delete alert_rule rows
    anti_fatigue_settings.py  — read/write user.settings anti-fatigue fields
  repositories/
    alerts_read_repository.py — paginated alert queries with geo_event join
    alert_rule_crud_repository.py — alert_rule CRUD queries
  schemas/
    alert_response.py         — AlertListItem, AlertListResponse (paginated envelope)
    alert_rule_schemas.py     — AlertRuleResponse, CreateAlertRuleRequest,
                                UpdateAlertRuleRequest
    anti_fatigue_schemas.py   — AntiFatigueSettingsResponse, UpdateAntiFatigueRequest

Frontend — src/frontend/
  pages/
    AlertsCenterPage.tsx      — route /alerts; tab host for List and Rules tabs
  components/alerts/
    AlertsListPanel.tsx       — chronological alert list with filter bar
    AlertFilterBar.tsx        — date range, status, action signal type filters
    AlertListRow.tsx          — single alert row; renders event deep-link
    AlertRulesPanel.tsx       — rule list with enable/disable toggle
    AlertRuleCard.tsx         — collapsed rule row with edit/delete controls
    AlertRuleFormModal.tsx    — create/edit modal: all rule fields
    AntiFatigueSettingsPanel.tsx — daily push limit, quiet hours, dedup window
  hooks/
    useAlerts.ts              — TanStack Query hook: GET /api/v1/alerts
    useAlertRules.ts          — TanStack Query hook: GET /api/v1/alert-rules
    useMutateAlertRule.ts     — create / update / delete mutations
    useAntiFatigueSettings.ts — read + update anti-fatigue settings
  lib/
    alertDeepLink.ts          — builds /map?event={id}&lat={lat}&lon={lon} URL
```

### Modified Components

| File | Change | Reason |
|------|--------|--------|
| `src/alerts/repositories/alert_rule_repository.py` | Add `get_by_user`, `insert`, `update`, `delete` methods to support CRUD | PLAN-F-005 only added `get_active_rules(tenant_id)`; this plan requires per-user CRUD access |
| `src/alerts/repositories/alert_repository.py` | Add `list_alerts` paginated query with status/date/signal filters and `geo_event` join | Existing write-path repository gains a read-path method |
| `src/api/v1/router.py` | Register `alerts_router`, `alert_rules_router`, `anti_fatigue_router` | Wire new endpoints into the FastAPI app |
| `src/frontend/App.tsx` | Add `/alerts` route pointing to `AlertsCenterPage` | Make Alerts Center reachable via navigation |

### Interfaces and Contracts

```python
# src/alerts/schemas/alert_response.py

from uuid import UUID
from datetime import datetime
from pydantic import BaseModel
from alerts.models import AlertStatus, ActionSignal

class AlertListItem(BaseModel):
    alert_id: UUID
    occurred_at: datetime
    event_title: str
    action_signal: ActionSignal
    confidence: float
    channel: str           # "email" | "silent"
    status: AlertStatus
    event_link: str        # /map?event={event_id}&lat={lat}&lon={lon}
    report_link: str | None

class AlertListResponse(BaseModel):
    items: list[AlertListItem]
    total: int
    page: int
    page_size: int
    has_next: bool

# src/alerts/schemas/alert_rule_schemas.py

class AlertRuleResponse(BaseModel):
    rule_id: UUID
    user_id: UUID
    name: str
    enabled: bool
    event_category_filter: list[str]
    intensity_min: int
    ticker_list: list[str]
    quiet_hours_start: str | None   # "HH:MM" UTC
    quiet_hours_end: str | None     # "HH:MM" UTC
    per_ticker_interval_hours: int
    channels: list[str]

class CreateAlertRuleRequest(BaseModel):
    name: str
    event_category_filter: list[str] = []
    intensity_min: int              # 1–5
    ticker_list: list[str] = []
    quiet_hours_start: str | None = None
    quiet_hours_end: str | None = None
    per_ticker_interval_hours: int = 24
    channels: list[str]

class UpdateAlertRuleRequest(BaseModel):
    name: str | None = None
    enabled: bool | None = None
    event_category_filter: list[str] | None = None
    intensity_min: int | None = None
    ticker_list: list[str] | None = None
    quiet_hours_start: str | None = None
    quiet_hours_end: str | None = None
    per_ticker_interval_hours: int | None = None
    channels: list[str] | None = None

# src/alerts/schemas/anti_fatigue_schemas.py

class AntiFatigueSettingsResponse(BaseModel):
    daily_push_limit: int
    quiet_hours_start: str | None   # "HH:MM" UTC
    quiet_hours_end: str | None     # "HH:MM" UTC
    dedup_window_minutes: int

class UpdateAntiFatigueRequest(BaseModel):
    daily_push_limit: int | None = None
    quiet_hours_start: str | None = None
    quiet_hours_end: str | None = None
    dedup_window_minutes: int | None = None


# Read-repository interfaces

class IAlertReadRepository(Protocol):
    async def list_alerts(
        self,
        user_id: UUID,
        tenant_id: UUID,
        page: int,
        page_size: int,
        status_filter: AlertStatus | None,
        action_signal_filter: ActionSignal | None,
        date_from: datetime | None,
        date_to: datetime | None,
    ) -> tuple[list[AlertListItem], int]: ...


class IAlertRuleCrudRepository(Protocol):
    async def get_by_user(
        self, user_id: UUID, tenant_id: UUID
    ) -> list[AlertRuleResponse]: ...

    async def get_by_id(
        self, rule_id: UUID, user_id: UUID, tenant_id: UUID
    ) -> AlertRuleResponse | None: ...

    async def insert(
        self, user_id: UUID, tenant_id: UUID, data: CreateAlertRuleRequest
    ) -> AlertRuleResponse: ...

    async def update(
        self, rule_id: UUID, user_id: UUID, tenant_id: UUID, data: UpdateAlertRuleRequest
    ) -> AlertRuleResponse: ...

    async def delete(
        self, rule_id: UUID, user_id: UUID, tenant_id: UUID
    ) -> None: ...
```

## Implementation Tasks

### TASK-001: Alerts Read Repository · M/TDD · src/alerts/repositories/alerts_read_repository.py, tests/unit/alerts/test_alerts_read_repository.py

Implement `AlertsReadRepository` satisfying `IAlertReadRepository`. The `list_alerts` method issues a single paginated SQL query joining `alert` to `geo_event` (for `title`, `lat`, `lon`, `occurred_at`) using SQLAlchemy 2.0 async session. Apply optional WHERE filters for `status`, `action_signal`, `dispatched_at` date range. Compute `event_link` as `/map?event={event_id}&lat={lat}&lon={lon}` inline in the query result mapping. Set `report_link = None` (report linking is deferred; field is nullable in the schema). Return a tuple of `(list[AlertListItem], total_count)` where `total_count` uses a count sub-query on the same filters. All queries include `WHERE alert.user_id = :user_id AND alert.tenant_id = :tenant_id`. Order by `alert.dispatched_at DESC NULLS LAST`.

**Tests to write first (TDD)**:
- `list_alerts` returns items ordered by `dispatched_at` descending
- `list_alerts` with `status_filter=SUPPRESSED_QUIET_HOURS` returns only matching rows
- `list_alerts` with `action_signal_filter=WATCH` returns only matching rows
- `list_alerts` with `date_from`/`date_to` filters excludes alerts outside the range
- `list_alerts` with no filters returns all alerts for the user
- Pagination: page 2 with page_size=10 skips first 10 rows
- `total` count reflects full result set, not just the current page
- `event_link` is correctly formed as `/map?event={event_id}&lat={lat}&lon={lon}`
- Alerts for a different `user_id` or `tenant_id` are never returned
- Alert with a silent-log `channel` appears in the list (status is the differentiator)

**AC covered**: AC-001, AC-005

---

### TASK-002: Alert Rule CRUD Repository · M/TDD · src/alerts/repositories/alert_rule_crud_repository.py, tests/unit/alerts/test_alert_rule_crud_repository.py

Implement `AlertRuleCrudRepository` satisfying `IAlertRuleCrudRepository`. All five methods (`get_by_user`, `get_by_id`, `insert`, `update`, `delete`) use SQLAlchemy 2.0 async session against the `alert_rule` table. `get_by_id` returns `None` (not raise) when the row does not exist or belongs to a different `user_id`/`tenant_id`. `insert` populates `rule_id` as a server-generated UUID. `update` applies only the non-None fields from `UpdateAlertRuleRequest` (partial update). `delete` is a hard delete (no soft-delete). All queries include `tenant_id` and `user_id` in their WHERE clauses.

**Tests to write first (TDD)**:
- `get_by_user` returns all rules owned by the user for that tenant
- `get_by_user` does not return rules owned by a different user or tenant
- `get_by_id` returns the rule when `rule_id`, `user_id`, and `tenant_id` all match
- `get_by_id` returns `None` when `rule_id` belongs to a different `user_id`
- `get_by_id` returns `None` when `rule_id` does not exist
- `insert` persists all fields and returns the new `AlertRuleResponse` with a valid UUID
- `update` with only `enabled=False` changes only `enabled`; all other fields remain unchanged
- `update` with `quiet_hours_start` and `quiet_hours_end` updates both fields atomically
- `delete` removes the row; subsequent `get_by_id` returns `None`
- `delete` on a non-existent or foreign-user rule raises `NotFoundError`

**AC covered**: AC-003, AC-004

---

### TASK-003: Alert Rule Manager Service · M/TDD · src/alerts/services/alert_rule_manager.py, tests/unit/alerts/test_alert_rule_manager.py

Implement `AlertRuleManager` service. Constructor accepts `IAlertRuleCrudRepository`. Public methods: `list_rules(user_id, tenant_id)`, `create_rule(user_id, tenant_id, data)`, `update_rule(rule_id, user_id, tenant_id, data)`, `delete_rule(rule_id, user_id, tenant_id)`. The service validates that `intensity_min` is in [1, 5] and `per_ticker_interval_hours` is positive before delegating to the repository. `update_rule` and `delete_rule` call `get_by_id` first; if `None` is returned, raise `NotFoundError` with the `rule_id`. This service owns the ownership-verification logic: a rule not belonging to the authenticated user is treated identically to a non-existent rule (both return `NotFoundError` — no information leak about other users' rules).

**Tests to write first (TDD)**:
- `create_rule` with valid payload delegates to `repo.insert` and returns the response
- `create_rule` with `intensity_min=0` raises `ValidationError`
- `create_rule` with `intensity_min=6` raises `ValidationError`
- `create_rule` with `per_ticker_interval_hours=-1` raises `ValidationError`
- `update_rule` where `get_by_id` returns `None` raises `NotFoundError`
- `update_rule` with valid payload delegates to `repo.update` and returns updated response
- `update_rule` with new `quiet_hours_start` / `quiet_hours_end` propagates values to repo
- `delete_rule` where `get_by_id` returns `None` raises `NotFoundError`
- `delete_rule` with valid ownership calls `repo.delete` once
- `list_rules` delegates to `repo.get_by_user` and returns the list unchanged

**AC covered**: AC-003, AC-004

---

### TASK-004: Anti-Fatigue Settings Service · M/TDD · src/alerts/services/anti_fatigue_settings.py, tests/unit/alerts/test_anti_fatigue_settings.py

Implement `AntiFatigueSettingsService`. Constructor accepts `IUserSettingsRepository` (reads/writes `user.settings JSONB`). Add a read method to `IUserSettingsRepository`: `get_anti_fatigue(user_id, tenant_id) -> AntiFatigueSettingsResponse` and a write method `update_anti_fatigue(user_id, tenant_id, data: UpdateAntiFatigueRequest) -> AntiFatigueSettingsResponse`. The service validates: `daily_push_limit >= 1`, `dedup_window_minutes >= 1`, and that `quiet_hours_start` < `quiet_hours_end` unless one or both are `None` (an overnight range is expressed as two values where start > end, which is allowed). On partial update, only provided non-None fields are written; existing values are preserved. The service does not read or write any `alert_rule` rows — it exclusively concerns `user.settings JSONB`.

**Tests to write first (TDD)**:
- `get_settings` returns current values from `user.settings`
- `update_settings` with only `daily_push_limit` changes only that field
- `update_settings` with `daily_push_limit=0` raises `ValidationError`
- `update_settings` with `dedup_window_minutes=0` raises `ValidationError`
- `update_settings` with `quiet_hours_start="22:00"` and `quiet_hours_end="06:00"` is accepted (overnight range)
- `update_settings` with `quiet_hours_start="08:00"` and `quiet_hours_end="08:00"` raises `ValidationError` (zero window)
- Partial update preserves fields not provided in the request
- Updates are isolated to the requesting `user_id` and `tenant_id`

**AC covered**: AC-003, AC-004

---

### TASK-005: Alerts Read API Endpoint · M/TDD · src/alerts/api/alerts_router.py, tests/integration/alerts/test_alerts_api.py

Implement `GET /api/v1/alerts` FastAPI router. Query parameters: `page` (default 1), `page_size` (default 20, max 100), `status` (optional, `AlertStatus` enum), `action_signal` (optional, `ActionSignal` enum), `date_from` (optional, ISO 8601), `date_to` (optional, ISO 8601). Extract `user_id` and `tenant_id` from the JWT dependency (`Depends(get_current_user)`). Delegate to `AlertsReader.list_alerts(...)` and return `AlertListResponse`. Always returns HTTP 200 (empty `items` list when no results). Validate `page >= 1` and `page_size` bounds; return HTTP 422 on invalid parameters.

**Tests to write first (TDD)**:
- Authenticated request returns HTTP 200 with paginated `AlertListResponse`
- Unauthenticated request returns HTTP 401
- `status=suppressed_daily_limit` filter returns only suppressed-daily-limit alerts
- `action_signal=WATCH` filter returns only WATCH alerts
- `date_from` / `date_to` filter excludes out-of-range alerts
- `page_size=0` returns HTTP 422
- `page_size=101` returns HTTP 422
- Response `event_link` field follows the `/map?event=…&lat=…&lon=…` pattern
- Empty result set returns HTTP 200 with `items=[]` and `total=0`
- Alerts for another user's `tenant_id` are not returned

**AC covered**: AC-001, AC-005

---

### TASK-006: Alert Rules CRUD API Endpoints · M/TDD · src/alerts/api/alert_rules_router.py, tests/integration/alerts/test_alert_rules_api.py

Implement four endpoints under `src/alerts/api/alert_rules_router.py`:

- `GET /api/v1/alert-rules` — list all rules for the authenticated user; returns `list[AlertRuleResponse]`
- `POST /api/v1/alert-rules` — create a new rule; body `CreateAlertRuleRequest`; returns `AlertRuleResponse` HTTP 201
- `PATCH /api/v1/alert-rules/{rule_id}` — partial update; body `UpdateAlertRuleRequest`; returns `AlertRuleResponse`
- `DELETE /api/v1/alert-rules/{rule_id}` — delete; returns HTTP 204

All endpoints extract `user_id` and `tenant_id` from JWT. `PATCH` and `DELETE` delegate to `AlertRuleManager`; `NotFoundError` maps to HTTP 404. `ValidationError` from the service layer maps to HTTP 422.

**Tests to write first (TDD)**:
- `GET /api/v1/alert-rules` returns HTTP 200 with the user's rules
- Unauthenticated `GET` returns HTTP 401
- `POST` with valid body returns HTTP 201 and persisted `AlertRuleResponse` with new `rule_id`
- `POST` with `intensity_min=6` returns HTTP 422
- `PATCH` with `enabled=false` returns HTTP 200 with `enabled=false` in response
- `PATCH` with `quiet_hours_start` and `quiet_hours_end` updates both fields
- `PATCH` on a non-existent or foreign-user `rule_id` returns HTTP 404
- `DELETE` on own rule returns HTTP 204 and subsequent `GET` does not include that rule
- `DELETE` on a non-existent or foreign-user `rule_id` returns HTTP 404
- `POST` and `PATCH` bodies validated against Pydantic schema; missing required fields return HTTP 422

**AC covered**: AC-003, AC-004

---

### TASK-007: Anti-Fatigue Settings API Endpoint · S/no-TDD · src/alerts/api/anti_fatigue_router.py

Implement two endpoints:

- `GET /api/v1/settings/anti-fatigue` — returns `AntiFatigueSettingsResponse` for the authenticated user
- `PATCH /api/v1/settings/anti-fatigue` — partial update; body `UpdateAntiFatigueRequest`; returns updated `AntiFatigueSettingsResponse`

Both require JWT auth. `ValidationError` from `AntiFatigueSettingsService` maps to HTTP 422. Register the router in `src/api/v1/router.py`.

**AC covered**: AC-003, AC-004

---

### TASK-008: Alerts Center Page Shell and Routing · S/no-TDD · src/frontend/pages/AlertsCenterPage.tsx, src/frontend/App.tsx

Create `AlertsCenterPage.tsx` with a two-tab layout: "Alerts" (default) and "Rules". Each tab renders a placeholder component. Add the `/alerts` route to `App.tsx`, pointing to `AlertsCenterPage`. The route requires authentication (redirect to `/login` if unauthenticated, using the same auth guard pattern as other protected routes in the app). Tabs switch without full page navigation (client-side tab state).

**AC covered**: enables AC-001, AC-003

---

### TASK-009: Alerts List Panel (Frontend) · M/TDD · src/frontend/components/alerts/AlertsListPanel.tsx, src/frontend/components/alerts/AlertFilterBar.tsx, src/frontend/components/alerts/AlertListRow.tsx, src/frontend/hooks/useAlerts.ts, src/frontend/lib/alertDeepLink.ts, tests/frontend/alerts/AlertsListPanel.test.tsx

Implement the Alerts tab of the Alerts Center.

`useAlerts.ts`: TanStack Query hook calling `GET /api/v1/alerts`. Accepts filter parameters (status, action_signal, date_from, date_to, page, page_size). Invalidates on stale time of 30 seconds.

`alertDeepLink.ts`: pure function `buildEventLink(eventId, lat, lon): string` returning `/map?event={eventId}&lat={lat}&lon={lon}`.

`AlertFilterBar.tsx`: renders a date-range picker, a status dropdown (All / Dispatched / Suppressed), and an action signal dropdown (All / HOLD / WATCH / BUY_OPP / REDUCE_RISK / HEDGE / CONTRARIAN). Calls an `onFilterChange` callback prop when any filter changes.

`AlertListRow.tsx`: renders one `AlertListItem`. Columns: timestamp (formatted local time), event title (truncated to 60 chars with title tooltip), action signal badge (color-coded), confidence percentage, channel badge, status badge. The event title is a clickable link using `buildEventLink`. If `report_link` is non-null, renders a secondary "Report" link.

`AlertsListPanel.tsx`: composes `AlertFilterBar` and a list of `AlertListRow`, plus pagination controls (prev/next, page indicator). Shows a loading skeleton during fetch. Shows an empty state message when `total=0`.

**Tests to write first (TDD)**:
- `buildEventLink` returns correct URL for given event_id, lat, lon
- `AlertListRow` renders event title as a link with the correct href
- `AlertListRow` shows `report_link` anchor when `report_link` is non-null
- `AlertListRow` does not render report link when `report_link` is null
- `AlertsListPanel` shows loading skeleton while `useAlerts` is loading
- `AlertsListPanel` shows empty-state message when `items` is empty
- `AlertsListPanel` renders one `AlertListRow` per item in the response
- `AlertFilterBar` calls `onFilterChange` when status dropdown changes
- `AlertFilterBar` calls `onFilterChange` when action signal dropdown changes
- Clicking "Next" page control increments the page parameter in the query hook

**AC covered**: AC-001, AC-002, AC-005

---

### TASK-010: Alert Rule Management Panel (Frontend) · M/TDD · src/frontend/components/alerts/AlertRulesPanel.tsx, src/frontend/components/alerts/AlertRuleCard.tsx, src/frontend/components/alerts/AlertRuleFormModal.tsx, src/frontend/hooks/useAlertRules.ts, src/frontend/hooks/useMutateAlertRule.ts, tests/frontend/alerts/AlertRulesPanel.test.tsx

Implement the Rules tab of the Alerts Center.

`useAlertRules.ts`: TanStack Query hook for `GET /api/v1/alert-rules`.

`useMutateAlertRule.ts`: exposes `createRule`, `updateRule`, `deleteRule` mutations using TanStack Query `useMutation`. On success, invalidates the `useAlertRules` cache.

`AlertRuleCard.tsx`: displays rule name, enabled status toggle (calls `updateRule({ enabled: !current })` on click), intensity_min, channel badges, and Edit / Delete buttons. Delete button shows a confirmation inline before calling `deleteRule`.

`AlertRuleFormModal.tsx`: modal form for create and edit. Fields: name (text), event_category_filter (multi-select), intensity_min (number 1–5), ticker_list (comma-separated text input parsed to array), quiet_hours_start / quiet_hours_end (time inputs, optional), per_ticker_interval_hours (number), channels (multi-checkbox: email, push). Validates intensity_min in [1, 5] before submitting. On submit, calls `createRule` or `updateRule` depending on whether `rule_id` is present.

`AlertRulesPanel.tsx`: renders a list of `AlertRuleCard`, a "New Rule" button that opens `AlertRuleFormModal` with no initial data. Shows an empty state when no rules exist.

**Tests to write first (TDD)**:
- `AlertRulesPanel` renders one `AlertRuleCard` per rule returned by `useAlertRules`
- `AlertRulesPanel` shows empty state when rule list is empty
- `AlertRuleCard` enabled toggle calls `updateRule` with `{ enabled: false }` when toggling off an enabled rule
- `AlertRuleCard` Delete button shows confirmation text before calling `deleteRule`
- `AlertRuleCard` Delete confirms and calls `deleteRule` with the correct `rule_id`
- `AlertRuleFormModal` submit with `intensity_min=6` shows validation error and does not call `createRule`
- `AlertRuleFormModal` submit with valid data calls `createRule` with correct payload
- `AlertRuleFormModal` in edit mode pre-populates all fields from the existing rule
- `AlertRuleFormModal` in edit mode calls `updateRule` (not `createRule`) on submit
- `useMutateAlertRule.createRule` invalidates the `useAlertRules` cache on success

**AC covered**: AC-003, AC-004

---

### TASK-011: Anti-Fatigue Settings Panel (Frontend) · S/no-TDD · src/frontend/components/alerts/AntiFatigueSettingsPanel.tsx, src/frontend/hooks/useAntiFatigueSettings.ts

`useAntiFatigueSettings.ts`: TanStack Query hook for `GET /api/v1/settings/anti-fatigue` + `useMutation` for `PATCH`.

`AntiFatigueSettingsPanel.tsx`: renders within the Rules tab below the rule list (or as a sub-section). Fields: Daily push limit (number input), Overall quiet hours start / end (time inputs, both optional, cleared together), Deduplication window in minutes (number input). Save button calls `PATCH /api/v1/settings/anti-fatigue` with changed fields only. Shows a success toast on save. Shows inline error on 422 validation failure.

**AC covered**: AC-003, AC-004

---

### TASK-012: Map Deep-Link Navigation · M/TDD · src/frontend/pages/MapPage.tsx (or equivalent), tests/frontend/alerts/alertDeepLink.test.ts

Ensure the Intelligence Map page handles the `?event={event_id}&lat={lat}&lon={lon}` query parameters: on mount, if these parameters are present, the map flies to `[lon, lat]` at zoom level 8 and opens the event popup for `event_id`. If the event popup data is not yet loaded, a loading spinner replaces the popup until the `geo_event` data resolves (fetched via `GET /api/v1/events/{event_id}` or the existing event endpoint from PLAN-F-001/F-019). This task only adds the parameter-handling mount effect; it does not change any existing map interaction behaviour.

**Tests to write first (TDD)**:
- `buildEventLink` produces a URL parseable by `URLSearchParams` with correct keys
- Map mount effect calls `flyTo` with correct `[lon, lat]` when query params are present
- Map mount effect opens the event popup for the given `event_id` after fly-to
- Map mount effect is a no-op when no query params are present
- Map mount effect handles malformed lat/lon gracefully (NaN guard; no flyTo called)
- Event popup shows a loading spinner when event data is not yet fetched

**AC covered**: AC-002

---

## Acceptance Criteria Coverage

- AC-001: Alerts Center lists alerts chronologically with event title, action signal, confidence, channel, and status; each row links to the originating map event or report → TASK-001, TASK-005, TASK-009
- AC-002: Clicking an alert's event link navigates map to event location and opens the popup → TASK-009, TASK-012
- AC-003: User creates new alert rule with intensity_min=4 and ticker list; rule saved; subsequent Mode A alerts evaluated against it → TASK-002, TASK-003, TASK-006, TASK-010
- AC-004: User edits quiet hours on an existing rule; updated quiet hours apply to all future alert evaluations immediately → TASK-002, TASK-003, TASK-004, TASK-006, TASK-007, TASK-010, TASK-011
- AC-005: Filter by status=suppressed shows only suppressed alerts → TASK-001, TASK-005, TASK-009

## Acceptance Notes

- AC-003 states that after saving a rule "subsequent Mode A alerts are evaluated against it". This is satisfied by the existing `AlertRuleEvaluator` in PLAN-F-005, which queries `alert_rule` rows at evaluation time. This plan only needs to ensure the new rule is persisted correctly — no pipeline changes are required.
- AC-004 quiet-hours immediacy: rule evaluation in PLAN-F-005 reads `alert_rule` rows fresh from the DB on every event. An updated rule row is effective for the next pipeline run with no cache invalidation step needed.
- `report_link` is nullable and returns `null` for all alerts in this MVP. The field is included in the response schema to avoid a breaking API change when report linking is implemented.
- The anti-fatigue settings panel edits `user.settings JSONB`. PLAN-F-005 reads these same settings for the global quiet hours and daily push limit. Changes take effect on the next Mode A pipeline run.

## Risks and Notes

- The `alert_rule` table schema in Architecture §10 differs from the requirement's data model (requirement adds `name`, `event_category_filter`, `ticker_list`, `quiet_hours_start`/`quiet_hours_end`, `per_ticker_interval_hours`; architecture uses `alert_type`, `scope JSONB`, `channels JSONB`, `quiet_hours JSONB`). PLAN-F-005 already noted this discrepancy and adopted the requirement schema as authoritative (per D10). This plan assumes PLAN-F-005's migration is already applied.
- The `alert` table as defined in Architecture §10 omits `user_id`, `action_signal`, and `status` columns. PLAN-F-005's migration adds these. This plan's read repository assumes those columns exist.
- The Map deep-link (AC-002) depends on PLAN-F-019 (Intelligence Map) being implemented; specifically, the map page must accept and handle `?event`, `?lat`, `?lon` query parameters. TASK-012 adds only the mount-effect handler; if PLAN-F-019 is not yet merged, this task produces a safe no-op (the parameters are silently ignored until the map component is available).
- Filtering by status=suppressed (AC-005) should match all suppressed statuses (`SUPPRESSED_DAILY_LIMIT`, `SUPPRESSED_QUIET_HOURS`, `SUPPRESSED_DEDUP`, `SUPPRESSED_BUDGET`, `SUPPRESSED_TICKER_INTERVAL`). The API filter parameter accepts a single `AlertStatus` value; the frontend filter dropdown should group all suppressed statuses under one "Suppressed" option, sending each as a separate request or as a server-side wildcard. Implement as a comma-separated `status` multi-value query parameter on the API; the frontend sends all five suppressed values when "Suppressed" is selected.
- Push notification channel (referenced in `channels` field) is out of scope for this plan per the requirement's Out of Scope section. The `channels` field accepts `["email"]` only in MVP. The form should not render a push checkbox; the field is included in the schema for forward compatibility.
