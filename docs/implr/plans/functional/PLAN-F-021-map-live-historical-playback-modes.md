---
plan_id: PLAN-F-021
slug: map-live-historical-playback-modes
title: Map Live, Historical, and Playback Modes
linked_requirement: REQ-F-021
type: functional
status: done
blocked_reason:
complexity: L
tdd_required: true
linked_nfrs: []
dependencies:
  - { id: PLAN-F-019, reason: "intelligence-map: useMapMode hook, WebSocket manager, and IntelligenceMap composition root must exist before time modes can be added" }
  - { id: PLAN-F-017, reason: "scoring-engine-and-indicator-builder: company_score TimescaleDB hypertable and ICompanyScoreRepository.get_history must exist; GET /api/v1/scores/company/{id}/history endpoint required by Historical mode" }
executed_at: 2026-06-05T00:00:00Z
reviewed_at:
review_id:
created_at: 2026-06-03T00:00:00Z
updated_at: 2026-06-05T00:00:00Z
---

# PLAN-F-021 — Map Live, Historical, and Playback Modes

## Linked Requirement
**REQ-F-021** — Map Live, Historical, and Playback Modes
Status: approved | Jira:

## Objective

Extend the Intelligence Map (PLAN-F-019) with three time-dimension modes. Live mode is the
default: the existing WebSocket connection delivers real-time event pulses within 5 seconds
of pipeline processing. Historical mode adds a date-range slider that queries
`GET /api/v1/events?from=&to=` for static event pulses and a score-at-time lookup
(`GET /api/v1/scores/history?company_ids=&at=`) that colors company markers by their
`company_score` value at the closest snapshot timestamp — a time-machine view with no future
data leakage. Playback mode loads the same historical event window and drives an animation
timer that reveals events chronologically at 1×, 4×, or 16× speed (a 1-hour event window at
16× plays in approximately 3.75 minutes), with Play/Pause/Reset controls. All three modes
display a contextual human-readable empty state instead of a blank canvas when no events
match. Switching back from Historical or Playback to Live reconnects the WebSocket without a
page reload. This plan adds the time-mode layer on top of the existing hook and component
tree from PLAN-F-019 — it does not rebuild map rendering, clustering, or score-overlay
infrastructure.

## Architecture Context

This plan operates entirely in **Layer 6 — Presentation** (ARCHITECTURE.md §11) and consumes
two **Layer 5 — Serving** endpoints (ARCHITECTURE.md §5, §10):

- `GET /api/v1/events?from=&to=` — already defined in the architecture for historical event
  load; this plan adds its backend FastAPI handler in `src/api/v1/events.py`.
- `GET /api/v1/scores/history?company_ids=&at=` — score-at-time query; backend uses the
  `WHERE computed_at <= :at_time ORDER BY computed_at DESC LIMIT 1 PER COMPANY` pattern
  against the `company_score` TimescaleDB hypertable (ARCHITECTURE.md §10). This plan adds
  the handler in `src/api/v1/scoring/scores.py`, extending PLAN-F-017's scores router.

**Frontend integration points (ARCHITECTURE.md §11, §13):**
- `useMapMode` hook (from PLAN-F-019 TASK-009) currently manages `"global" | "portfolio" |
  "sector"` context. This plan extends it with a second orthogonal dimension: the time mode
  (`"live" | "historical" | "playback"`) and the associated date-range / speed state.
- The WebSocket subscription manager (PLAN-F-019 TASK-002) already exposes `subscribe`,
  `unsubscribe`, and a `connected: bool`. This plan extends it with an explicit
  `reconnect()` method used on Live-mode re-entry.
- `useEventFeed` (PLAN-F-019 TASK-002) is extended: when `timeMode === "historical"` or
  `"playback"`, the hook suspends the WebSocket subscription and switches to a
  TanStack Query `useQuery` over the historical REST endpoint.
- `IntelligenceMap.tsx` (PLAN-F-019 TASK-011) is modified to wire the new time-mode
  toolbar and pass the active event window to the existing `<PulseLayer>` and
  `<ClusterLayer>` without touching their internal rendering logic.

**Data layer:**
- `company_score` is a TimescaleDB hypertable partitioned on `computed_at`
  (ARCHITECTURE.md §10, D4). Score-at-time is a standard `ORDER BY computed_at DESC LIMIT 1`
  range query — no schema change required beyond what PLAN-F-017 already provides.

**SOLID application:**
- `useTimeModeState` (new) owns all time-mode state. `useEventFeed` is extended via a
  strategy pattern: it accepts a `TimeModeContext` object and delegates fetch/subscribe
  behavior without a switch-chain inside the hook body.
- `PlaybackEngine` is a standalone class (Single Responsibility) injected into
  `usePlayback`; it is not wired into the WebSocket or fetch layers.

## Component Design

### New Components

```
src/
  features/
    intelligence-map/
      components/
        TimeModeToolbar.tsx          — mode toggle (Live / Historical / Playback) + date
                                       range slider + speed picker; overlay at top-right
        TimeModeToolbar.test.tsx
        DateRangeSlider.tsx          — controlled date-range input (from_date, to_date);
                                       uses shadcn/ui Slider + date picker
        DateRangeSlider.test.tsx
        PlaybackControls.tsx         — Play / Pause / Reset buttons + speed selector
                                       (1×, 4×, 16×); visible only in Playback mode
        PlaybackControls.test.tsx
      hooks/
        useTimeModeState.ts          — owns TimeMode enum + date range + speed;
                                       pure reducer, no side effects
        useTimeModeState.test.ts
        useHistoricalEvents.ts       — TanStack Query useQuery over GET /api/v1/events
                                       ?from=&to=; disabled unless timeMode="historical"
                                       or "playback"
        useHistoricalEvents.test.ts
        useScoreAtTime.ts            — TanStack Query useQuery over GET /api/v1/scores/
                                       history?company_ids=&at=; returns company_id →
                                       ScoreAtTime map; drives score overlay coloring in
                                       Historical mode
        useScoreAtTime.test.ts
        usePlayback.ts               — animation engine wrapper; drives a tick timer that
                                       advances a virtual "now" cursor through the event
                                       window; exposes { isPlaying, currentTick,
                                       play, pause, reset }
        usePlayback.test.ts
      lib/
        playback-engine.ts           — pure PlaybackEngine class: constructor(events,
                                       speedMultiplier); tick(wallClockMs): EventPulse[];
                                       no React dependency
        playback-engine.test.ts
        time-mode-empty-state.ts     — mode-aware empty state message generator extending
                                       PLAN-F-019's empty-state-message.ts
        time-mode-empty-state.test.ts
      types/
        time-mode.types.ts           — TimeMode enum, DateRange, PlaybackSpeed, ScoreAtTime
                                       interfaces

  api/
    v1/
      scores_history.py              — GET /api/v1/scores/history FastAPI handler;
                                       calls ICompanyScoreRepository.get_score_at_time
      events_range.py                — GET /api/v1/events?from=&to= FastAPI handler;
                                       calls IEventRepository.get_events_in_range

tests/
  unit/
    intelligence-map/
      (collocated .test.ts files above)
  integration/
    intelligence-map/
      map-historical-mode.test.tsx   — RTL + MSW; date range → static pulses + scores
      map-playback-mode.test.tsx     — RTL + fake timer; Play → events appear in order
      map-live-reconnect.test.tsx    — RTL + fake WS; Historical → Live → WS reconnected
    api/
      test_scores_history_api.py     — pytest; GET /api/v1/scores/history correctness
      test_events_range_api.py       — pytest; GET /api/v1/events?from=&to= correctness
```

### Modified Components

| File | Change | Reason |
|------|--------|--------|
| `src/features/intelligence-map/hooks/useMapMode.ts` | Extend state to include `timeMode: TimeMode`, `dateRange: DateRange \| null`, `playbackSpeed: PlaybackSpeed`; add `SET_TIME_MODE`, `SET_DATE_RANGE`, `SET_PLAYBACK_SPEED` actions | Time mode is part of the map's overall mode state; keeping it co-located avoids prop drilling |
| `src/features/intelligence-map/hooks/useEventFeed.ts` | Accept `TimeModeContext`; when `timeMode !== "live"`, suspend WebSocket subscription and return events from `useHistoricalEvents`; when `timeMode === "playback"`, return the tick-windowed event slice from `usePlayback` | Strategy extension without breaking Live mode path (OCP) |
| `src/features/intelligence-map/IntelligenceMap.tsx` | Mount `<TimeModeToolbar>` and `<PlaybackControls>`; pass `timeMode` and `currentTick` down to `useEventFeed`; render `<ScoreAtTimeOverlay>` when `timeMode === "historical"` | Composition root wires all new hooks into the existing render tree |
| `src/api/v1/scoring/scores.py` | Add `GET /api/v1/scores/history` handler (score-at-time batch endpoint) | PLAN-F-017 defined the scores router; this plan adds the time-machine query endpoint |
| `src/api/v1/events.py` | Add `from` and `to` query parameters to `GET /api/v1/events`; delegate to `IEventRepository.get_events_in_range` | Historical and Playback modes need date-scoped event fetch |
| `src/api/websocket-manager.ts` | Add `reconnect(): void` method; emit `connected` state transitions via existing callback mechanism | AC-005 — switching from Historical/Playback back to Live must re-establish the WS without a page reload |

### Interfaces and Contracts

```typescript
// src/features/intelligence-map/types/time-mode.types.ts

export type TimeMode = "live" | "historical" | "playback";
export type PlaybackSpeed = "1x" | "4x" | "16x";

export interface DateRange {
  from_date: string;  // ISO 8601 date "YYYY-MM-DD"
  to_date: string;    // ISO 8601 date "YYYY-MM-DD"
}

export interface ScoreAtTime {
  company_id: string;
  indicator_id: string;
  score: number;        // 0–100 normalized
  geo_adjusted: number; // 0–100
  computed_at: string;  // ISO 8601 timestamp of the closest snapshot
}

export interface TimeModeContext {
  timeMode: TimeMode;
  dateRange: DateRange | null;
  playbackSpeed: PlaybackSpeed;
  currentTick: Date | null;  // set by PlaybackEngine in Playback mode; null otherwise
}


// src/features/intelligence-map/lib/playback-engine.ts

export const PLAYBACK_MULTIPLIERS: Record<PlaybackSpeed, number> = {
  "1x": 1,
  "4x": 4,
  "16x": 16,
};

export class PlaybackEngine {
  constructor(events: EventPulse[], speed: PlaybackSpeed);
  // Returns events whose timestamp <= virtualNow; call on each animation frame tick.
  tick(wallClockElapsedMs: number): { visibleEvents: EventPulse[]; virtualNow: Date };
  reset(): void;
}


// src/features/intelligence-map/hooks/useTimeModeState.ts

export interface TimeModeState {
  timeMode: TimeMode;
  dateRange: DateRange | null;
  playbackSpeed: PlaybackSpeed;
}

type TimeModeAction =
  | { type: "SET_TIME_MODE"; payload: TimeMode }
  | { type: "SET_DATE_RANGE"; payload: DateRange | null }
  | { type: "SET_PLAYBACK_SPEED"; payload: PlaybackSpeed };

export function useTimeModeState(): {
  state: TimeModeState;
  setTimeMode: (mode: TimeMode) => void;
  setDateRange: (range: DateRange | null) => void;
  setPlaybackSpeed: (speed: PlaybackSpeed) => void;
};


// src/features/intelligence-map/hooks/useHistoricalEvents.ts

export interface HistoricalEventsParams {
  dateRange: DateRange;
  enabled: boolean;  // false in Live mode
}

export function useHistoricalEvents(params: HistoricalEventsParams): {
  events: EventPulse[];
  isLoading: boolean;
  isError: boolean;
};


// src/features/intelligence-map/hooks/useScoreAtTime.ts

export interface ScoreAtTimeParams {
  companyIds: string[];
  at: string;    // ISO 8601 datetime; closest snapshot at or before this time is returned
  enabled: boolean;
}

export function useScoreAtTime(params: ScoreAtTimeParams): {
  scores: Record<string, ScoreAtTime>;  // keyed by company_id
  isLoading: boolean;
};


// Backend: src/api/v1/scoring/scores.py (extension)

# New endpoint added to existing scores router:
# GET /api/v1/scores/history
# Query params: company_ids (comma-separated UUIDs), at (ISO datetime)
# Response: { data: ScoreAtTime[], error: null }
# Score-at-time SQL pattern:
#   SELECT DISTINCT ON (company_id, indicator_id)
#     company_id, indicator_id, score, geo_adjusted, computed_at
#   FROM company_score
#   WHERE company_id = ANY(:company_ids)
#     AND computed_at <= :at_time
#   ORDER BY company_id, indicator_id, computed_at DESC


# Backend: src/api/v1/events.py (extension)

# Extended existing GET /api/v1/events endpoint:
# New query params: from (ISO date, optional), to (ISO date, optional)
# When from/to provided, filters: occurred_at >= from AND occurred_at <= to
# WebSocket subscription is NOT established for date-filtered calls
# Response envelope unchanged: { data: EventPulse[], error: null }
```

## Implementation Tasks

### TASK-001: Time-mode type definitions · S/no-TDD · src/features/intelligence-map/types/time-mode.types.ts

Define all TypeScript types for the time-mode system: `TimeMode`, `PlaybackSpeed`,
`DateRange`, `ScoreAtTime`, `TimeModeContext`. Export from the feature barrel. These are pure
data contracts with no logic and no React dependency.

The `PlaybackSpeed` type is a string literal union (`"1x" | "4x" | "16x"`) rather than a
numeric enum so that it is directly serializable as a display label and as a URL query
parameter without transformation.

**AC covered**: enables AC-002, AC-003, AC-004, AC-005

---

### TASK-002: `useTimeModeState` hook · M/TDD · src/features/intelligence-map/hooks/useTimeModeState.ts,src/features/intelligence-map/hooks/useTimeModeState.test.ts

Implement `useTimeModeState()` as a `useReducer`-based hook with three actions:
`SET_TIME_MODE`, `SET_DATE_RANGE`, `SET_PLAYBACK_SPEED`. Initial state: `timeMode="live"`,
`dateRange=null`, `playbackSpeed="1x"`.

Guard: when `SET_TIME_MODE` transitions to `"live"`, reset `dateRange` to `null` and
`playbackSpeed` to `"1x"` atomically in a single dispatch so downstream subscribers never
observe an inconsistent state (e.g., `timeMode="live"` with a stale `dateRange` set).

Guard: when `SET_TIME_MODE` transitions to `"historical"` or `"playback"`, do not clear
`dateRange` if one is already set — preserve the last-used range across mode switches.

**Tests to write first (TDD):**
- Initial state has `timeMode="live"`, `dateRange=null`, `playbackSpeed="1x"`
- `SET_TIME_MODE("historical")` transitions `timeMode` to `"historical"` without clearing an existing `dateRange`
- `SET_TIME_MODE("live")` from `"historical"` resets `dateRange` to `null` and `playbackSpeed` to `"1x"`
- `SET_DATE_RANGE({ from_date: "2025-01-01", to_date: "2025-01-31" })` sets `dateRange` correctly
- `SET_PLAYBACK_SPEED("16x")` updates `playbackSpeed` to `"16x"`
- `SET_TIME_MODE("playback")` from `"live"` with no prior `dateRange` leaves `dateRange` as `null`

**AC covered**: AC-002, AC-003, AC-005

---

### TASK-003: `PlaybackEngine` class · M/TDD · src/features/intelligence-map/lib/playback-engine.ts,src/features/intelligence-map/lib/playback-engine.test.ts

Implement the `PlaybackEngine` class: a pure, framework-free animation engine that maps
wall-clock elapsed milliseconds to a virtual event window cursor.

Constructor: `PlaybackEngine(events: EventPulse[], speed: PlaybackSpeed)`. Internally,
sort events ascending by `timestamp`. Compute the `virtualWindowStart` from the earliest
event timestamp and `virtualWindowEnd` from the latest.

`tick(wallClockElapsedMs: number)`: compute `virtualElapsedMs = wallClockElapsedMs * PLAYBACK_MULTIPLIERS[speed]`; derive `virtualNow = virtualWindowStart + virtualElapsedMs`. Return
`{ visibleEvents: EventPulse[], virtualNow: Date }` where `visibleEvents` contains all events
with `timestamp <= virtualNow`. When `virtualNow >= virtualWindowEnd`, clamp and stop advancing
(all events are visible; playback is complete).

`reset()`: reset the internal elapsed counter to zero so subsequent `tick` calls restart from the beginning.

Speed verification: at 16×, one real hour (3 600 000 ms) of wall-clock time advances the
virtual cursor by 57 600 000 ms (16 hours). A 1-hour event window (`virtualWindowEnd -
virtualWindowStart = 3 600 000 ms`) completes in `3 600 000 / 16 = 225 000 ms` (3.75
minutes) of wall-clock time, satisfying AC-003.

**Tests to write first (TDD):**
- Given 3 events at T+0min, T+30min, T+60min; speed `"1x"`; after `tick(0)` → 1 event visible (T+0)
- After `tick(1_800_000)` (30 real minutes at 1×) → 2 events visible (T+0 and T+30)
- After `tick(3_600_000)` (60 real minutes at 1×) → 3 events visible; `virtualNow` equals `virtualWindowEnd`
- Speed `"16x"`; after `tick(225_000)` (3.75 real minutes) → all 3 events visible (1-hour window completes) — AC-003 numerical verification
- Speed `"4x"`; after `tick(900_000)` (15 real minutes) → 3 events visible (1-hour window completes)
- `reset()` after `tick(3_600_000)` → next `tick(0)` returns 1 event visible again (T+0 only)
- Empty events array → `tick(any)` returns `{ visibleEvents: [], virtualNow: <epoch> }`
- Events with identical timestamps all appear together in the same tick

**AC covered**: AC-003

---

### TASK-004: `usePlayback` hook · M/TDD · src/features/intelligence-map/hooks/usePlayback.ts,src/features/intelligence-map/hooks/usePlayback.test.ts

Implement `usePlayback(events: EventPulse[], speed: PlaybackSpeed)`. The hook wraps
`PlaybackEngine` in a React `useRef` (so the engine instance survives re-renders) and uses
`requestAnimationFrame` for the tick loop.

State exposed: `{ isPlaying: boolean, visibleEvents: EventPulse[], virtualNow: Date | null, isComplete: boolean }`.
Methods exposed: `play()`, `pause()`, `reset()`.

`play()`: starts the `requestAnimationFrame` loop; computes `wallClockElapsed` as
`performance.now() - startTime`; calls `engine.tick(wallClockElapsed)` each frame; updates
`visibleEvents` and `virtualNow` state; when `isComplete` becomes true, cancels the loop.

`pause()`: cancels the current animation frame; preserves `visibleEvents` and `wallClockElapsed` so `play()` resumes from the same position.

`reset()`: cancels loop, calls `engine.reset()`, resets state to initial (empty
`visibleEvents`, `isPlaying=false`, `isComplete=false`).

When `events` prop changes (new date window loaded), reset the engine with the new event
set (do not carry over stale `wallClockElapsed`).

**Tests to write first (TDD):**
- `play()` → after `vi.advanceTimersByTime(some_ms)` → `visibleEvents` grows (mock `requestAnimationFrame` via vitest fake timers)
- `pause()` during playback → `isPlaying` becomes `false`; subsequent timer advance does not change `visibleEvents`
- `reset()` → `visibleEvents` cleared, `isPlaying=false`, `virtualNow=null`
- Playback reaching `isComplete=true` → animation loop cancelled; no further `requestAnimationFrame` calls after completion
- `play()` called twice without `pause()` in between → does not start a second animation loop (idempotent)
- `events` prop changing while playing → engine resets to new event set; `visibleEvents` reflects new set from tick 0

**AC covered**: AC-003

---

### TASK-005: Historical events API hook · M/TDD · src/features/intelligence-map/hooks/useHistoricalEvents.ts,src/features/intelligence-map/hooks/useHistoricalEvents.test.ts

Implement `useHistoricalEvents({ dateRange, enabled })`. When `enabled=false`, the hook
returns `{ events: [], isLoading: false, isError: false }` immediately without any network
call. When `enabled=true` and `dateRange` is set, use TanStack Query `useQuery` to call
`GET /api/v1/events?from={dateRange.from_date}&to={dateRange.to_date}`. The query key
includes `[dateRange.from_date, dateRange.to_date]` so changing the date range triggers a
fresh fetch.

Validate the response with the same `EventPulse` Zod schema used by PLAN-F-019's
`fetchEvents`, throwing `EventFetchError` on schema violations. Return events sorted
ascending by `timestamp` to ensure `PlaybackEngine` receives pre-sorted input.

The hook must not re-subscribe to the WebSocket. It is the pure REST half of the
`useEventFeed` strategy extension.

**Tests to write first (TDD):**
- `enabled=false` → no `GET /api/v1/events` request made; returns empty events array
- `enabled=true`, MSW returns 5 events in date range → `events` has length 5 after loading resolves
- Date range changes while `enabled=true` → new fetch is triggered with updated `from` and `to` params; previous result is not used
- MSW returns malformed event (missing `lat`) → `isError=true`; `events` remains empty
- Events returned out of chronological order from the API → hook returns them sorted ascending by `timestamp`

**AC covered**: AC-002, AC-003

---

### TASK-006: Score-at-time API hook · M/TDD · src/features/intelligence-map/hooks/useScoreAtTime.ts,src/features/intelligence-map/hooks/useScoreAtTime.test.ts

Implement `useScoreAtTime({ companyIds, at, enabled })`. When `enabled=false` (i.e., not in
Historical mode), returns `{ scores: {}, isLoading: false }` immediately.

When enabled, calls `GET /api/v1/scores/history?company_ids={csv}&at={iso_datetime}` via
TanStack Query. The `company_ids` list is derived from the currently visible historical event
set (the union of `affected_companies[].company_id` across all visible events). Deduplicate
before sending.

Response is a `ScoreAtTime[]`. The hook transforms this into
`Record<string, ScoreAtTime>` keyed by `company_id` for O(1) lookup by the score overlay.

Query key: `["scores-at-time", companyIds.sort().join(","), at]` — sorted company ID list
and `at` timestamp together determine cacheability.

**Tests to write first (TDD):**
- `enabled=false` → no fetch; returns `{}`
- `enabled=true`, MSW returns 2 score records → `scores` has 2 keys matching company IDs
- Same `at` and `companyIds` → TanStack Query cache hit; no second network call
- `at` changes → new fetch triggered
- `companyIds` changes (new events loaded) → new fetch triggered
- Company absent from history (no row before `at`) → that company's ID is absent from `scores` (no phantom defaults)

**AC covered**: AC-002

---

### TASK-007: `TimeModeToolbar` component · M/TDD · src/features/intelligence-map/components/TimeModeToolbar.tsx,src/features/intelligence-map/components/TimeModeToolbar.test.tsx,src/features/intelligence-map/components/DateRangeSlider.tsx,src/features/intelligence-map/components/DateRangeSlider.test.tsx

Implement `<TimeModeToolbar timeMode onSetTimeMode dateRange onSetDateRange />` as an
absolutely-positioned overlay at the top-right of the map canvas (consistent with
`<MapContextSwitcher>` at top-left from PLAN-F-019).

Mode toggle: a three-button shadcn/ui `ToggleGroup` labeled "Live / Historical / Playback".
The active mode is visually distinguished (filled pill).

Conditional rendering:
- `timeMode === "live"`: only the toggle is shown.
- `timeMode === "historical"` or `"playback"`: the `<DateRangeSlider>` is shown below the
  toggle. A "Load" button triggers the historical fetch only on explicit user confirmation
  (not on every slider drag) to avoid thrashing the API.

`<DateRangeSlider from_date to_date onSetRange />`: a pair of shadcn/ui date pickers
(calendar popup, not a range input slider, for accessibility). The from_date must be before
to_date; the component blocks the "Load" button and shows an inline error if the range is
invalid. Maximum range enforced: 365 days. Date values are ISO 8601 strings.

**Tests to write first (TDD):**
- Renders three toggle buttons; clicking "Historical" calls `onSetTimeMode("historical")`
- `timeMode="live"` → `<DateRangeSlider>` not present in the DOM
- `timeMode="historical"` → `<DateRangeSlider>` is present in the DOM
- `<DateRangeSlider>` with `from_date > to_date` → "Load" button is disabled; error message visible
- `<DateRangeSlider>` with valid range → "Load" button enabled; clicking it calls `onSetDateRange`
- `<DateRangeSlider>` with range > 365 days → "Load" button disabled with "range exceeds 1 year" message

**AC covered**: AC-002, AC-003, AC-005

---

### TASK-008: `PlaybackControls` component · M/TDD · src/features/intelligence-map/components/PlaybackControls.tsx,src/features/intelligence-map/components/PlaybackControls.test.tsx

Implement `<PlaybackControls isPlaying isComplete speed onPlay onPause onReset onSetSpeed />`.
The component renders only when `timeMode === "playback"` (controlled by the parent
`<IntelligenceMap>`).

Controls:
- Play button: visible when `!isPlaying && !isComplete`; calls `onPlay()`.
- Pause button: visible when `isPlaying`; calls `onPause()`.
- Reset button: always visible; calls `onReset()`.
- Speed selector: shadcn/ui `Select` with options "1×", "4×", "16×"; calls `onSetSpeed(speed)`.
- Progress indicator: a thin linear progress bar showing `visibleEvents.length / totalEvents`
  as a fraction. When `isComplete`, bar fills entirely and shows "Complete" label.

The component is purely presentational — all state lives in `usePlayback`.

**Tests to write first (TDD):**
- `isPlaying=false, isComplete=false` → Play button present, Pause button absent
- `isPlaying=true` → Pause button present, Play button absent
- `isComplete=true` → Play button absent, Pause button absent, "Complete" label visible
- Clicking Play fires `onPlay`; clicking Pause fires `onPause`; clicking Reset fires `onReset`
- Selecting "16×" from speed selector fires `onSetSpeed("16x")`
- `visibleEvents=3, totalEvents=10` → progress bar has width ~30% (assert `aria-valuenow` attribute)

**AC covered**: AC-003

---

### TASK-009: Time-mode empty state extension · S/no-TDD · src/features/intelligence-map/lib/time-mode-empty-state.ts,src/features/intelligence-map/lib/time-mode-empty-state.test.ts

Extend the empty-state message system from PLAN-F-019 with time-mode awareness. Implement
`generateTimeModeEmptyStateMessage(timeMode, dateRange, eventCount, nearHoldingsCount): string`:

- `timeMode="live"`: delegate to the existing `generateEmptyStateMessage` from PLAN-F-019.
- `timeMode="historical"` and `eventCount=0` and `dateRange` set: `"No events found between {from_date} and {to_date}. Try widening the date range."`
- `timeMode="historical"` and `eventCount=0` and no `dateRange`: `"Select a date range to explore historical events."`
- `timeMode="playback"` and `isComplete=false` and `eventCount=0`: `"No events in the selected period. Try a different date range."`
- `timeMode="playback"` and `isComplete=true`: `"Playback complete. {totalEvents} event(s) replayed."`
- Fallback: `"No events to display."`

This function is not a React component — it is a pure string generator tested independently.
The existing `<EmptyState message={string} />` component from PLAN-F-019 renders the output.

**AC covered**: AC-004

---

### TASK-010: Backend — `GET /api/v1/scores/history` endpoint · M/TDD · src/api/v1/scoring/scores.py,tests/integration/api/scoring/test_scores_history_api.py

Add the score-at-time batch endpoint to the existing scoring scores router from PLAN-F-017.

Endpoint: `GET /api/v1/scores/history`
Query parameters:
- `company_ids`: comma-separated UUID strings (required; max 200 company IDs)
- `at`: ISO 8601 datetime string (required)

Response: `{ data: ScoreAtTime[], error: null }` where `ScoreAtTime` contains
`company_id`, `indicator_id`, `score`, `geo_adjusted`, `computed_at`.

SQL pattern (via `ICompanyScoreRepository`):
```sql
SELECT DISTINCT ON (company_id, indicator_id)
  company_id, indicator_id, score, geo_adjusted, computed_at
FROM company_score
WHERE company_id = ANY(:company_ids)
  AND computed_at <= :at_time
ORDER BY company_id, indicator_id, computed_at DESC
```

Add `get_score_at_time(company_ids: list[UUID], at_time: datetime) -> list[CompanyScoreRecord]`
to `ICompanyScoreRepository` interface and its `CompanyScoreRepository` implementation.
This is the only change to PLAN-F-017's repository interface.

Authorization: JWT required; `tenant_id` included in the WHERE clause automatically
via repository injection (ARCHITECTURE.md §12.3, Principle 3).

**Tests to write first (TDD):**
- `GET /api/v1/scores/history?company_ids={id1}&at=2025-06-01T12:00:00Z` with a score row at `2025-05-15` → returns that row (closest before `at`)
- Two companies, each with 3 score rows; `at` before all rows of company B → company B absent from response
- `company_ids` with 201 IDs → HTTP 422 with validation error
- Missing `at` parameter → HTTP 422
- Missing `company_ids` parameter → HTTP 422
- Unauthenticated request → HTTP 401
- `at` in the future (beyond all stored rows) → returns the most recent row for each company present

**AC covered**: AC-002

---

### TASK-011: Backend — `GET /api/v1/events` date-range filter · M/TDD · src/api/v1/events.py,tests/integration/api/test_events_range_api.py

Extend the existing `GET /api/v1/events` endpoint to accept optional `from` and `to` ISO
date query parameters. When present, add `occurred_at >= :from_date AND occurred_at <=
:to_date + interval '1 day'` to the existing query. When absent, the endpoint behaves
identically to its current implementation (Live mode path).

Add `get_events_in_range(from_date: date, to_date: date, tenant_id: UUID) -> list[GeoEvent]`
to the `IEventRepository` interface and its SQLAlchemy implementation.

The endpoint must not attempt a WebSocket subscription — range queries are strictly REST.

**Tests to write first (TDD):**
- `GET /api/v1/events?from=2025-01-01&to=2025-01-31` with 5 events in range and 3 outside → returns exactly 5 events
- Events at `2025-01-01` and at `2025-01-31` are both included (inclusive bounds)
- `from` without `to` → HTTP 422 (both required when either is provided)
- `from > to` → HTTP 422 with "from_date must be before to_date" message
- No `from` or `to` → existing behavior unchanged; all recent events returned
- Unauthenticated request with range params → HTTP 401
- `tenant_id` scoping: events from another tenant not returned even with a matching date range

**AC covered**: AC-002, AC-003

---

### TASK-012: `IntelligenceMap` integration — time-mode wiring · L/TDD · src/features/intelligence-map/IntelligenceMap.tsx,src/features/intelligence-map/IntelligenceMap.test.tsx

Extend `<IntelligenceMap />` to integrate all time-mode hooks and components. This task
modifies the composition root established by PLAN-F-019 TASK-011.

Changes:
1. Call `useTimeModeState()` and destructure `{ state, setTimeMode, setDateRange, setPlaybackSpeed }`.
2. Call `useHistoricalEvents({ dateRange: state.dateRange, enabled: state.timeMode !== "live" })`.
3. Call `usePlayback(historicalEvents.events, state.playbackSpeed)` — returns `{ isPlaying, visibleEvents, virtualNow, isComplete, play, pause, reset }`.
4. Compute `activeEvents`:
   - `"live"` → `liveEvents` from existing `useEventFeed` (unchanged).
   - `"historical"` → `historicalEvents.events`.
   - `"playback"` → `playback.visibleEvents`.
5. Call `useScoreAtTime({ companyIds: derivedCompanyIds, at: virtualNow?.toISOString() ?? state.dateRange?.to_date, enabled: state.timeMode === "historical" })`.
6. Pass `activeEvents` to `<PulseLayer>` (replaces the live-mode `events` prop — no change to PulseLayer signature).
7. Mount `<TimeModeToolbar>` wired to `useTimeModeState`.
8. Mount `<PlaybackControls>` when `timeMode === "playback"`, wired to `usePlayback`.
9. When `timeMode` transitions to `"live"`, call `websocketManager.reconnect()` (AC-005).
10. Pass `scoreAtTimeData` to the existing `<ScoreOverlay>` when `timeMode === "historical"`;
    in Live mode the existing `useScoreOverlay` WebSocket path is used unchanged.
11. Derive the empty-state message via `generateTimeModeEmptyStateMessage(...)` and pass to `<EmptyState>`.

**Tests to write first (TDD):**
- `timeMode="historical"` with MSW returning 3 historical events → `<PulseLayer>` receives 3 static events; no WebSocket subscription attempted
- `timeMode="playback"`, `play()` called → `<PulseLayer>` receives increasing event slices over fake timer ticks
- `timeMode` switch `"historical"` → `"live"` → `websocketManager.reconnect()` called exactly once (spy assertion) — AC-005
- `timeMode="historical"` with 0 events returned → `<EmptyState>` displays Historical-mode message (contains date range)
- `timeMode="playback"` and `isComplete=true` → `<EmptyState>` displays "Playback complete" message
- `timeMode="live"` with 0 events → existing Live-mode empty state message shown (regression guard)
- `<PlaybackControls>` only present in DOM when `timeMode="playback"`

**AC covered**: AC-001, AC-002, AC-003, AC-004, AC-005

---

### TASK-013: Integration tests — Historical, Playback, and Live-reconnect · M/TDD · tests/integration/intelligence-map/map-historical-mode.test.tsx,tests/integration/intelligence-map/map-playback-mode.test.tsx,tests/integration/intelligence-map/map-live-reconnect.test.tsx

Write the three integration test suites using React Testing Library + MSW + vitest fake
timers. These tests exercise the full hook-to-component flow.

**`map-historical-mode.test.tsx`:**
- Set `timeMode="historical"`, `dateRange={ from: "2025-01-01", to: "2025-01-31" }` → assert
  `GET /api/v1/events?from=2025-01-01&to=2025-01-31` is called; assert PulseLayer receives
  the events from MSW.
- Assert `GET /api/v1/scores/history` is called with company IDs from those events and the
  correct `at` timestamp.
- Assert that `ws/events` WebSocket is NOT subscribed in Historical mode.

**`map-playback-mode.test.tsx`:**
- Set `timeMode="playback"`, load 3 events spanning 1 hour; click Play.
- Advance fake timer by `225_000 ms` (3.75 minutes real → 1 hour virtual at 16×).
- Assert all 3 events are visible after that duration (AC-003 numerical).
- Assert `<PlaybackControls>` shows "Complete" state.
- Click Reset → PulseLayer receives 0 visible events.

**`map-live-reconnect.test.tsx`:**
- Start in Historical mode; switch back to Live mode via `<TimeModeToolbar>`.
- Assert `websocketManager.reconnect()` spy called exactly once.
- Assert `ws/events` WebSocket subscription is re-established.
- Assert that a subsequent WebSocket push event appears in PulseLayer event list.

**Tests to write first (TDD):**
(All bullet points above are discrete test cases.)

**AC covered**: AC-001, AC-002, AC-003, AC-004, AC-005

---

## Acceptance Criteria Coverage

- AC-001: Live mode active → WebSocket connection established on load; new event pulses appear on map within 5 seconds → TASK-012, TASK-013
- AC-002: Historical mode and date range selected → events within range render as static pulses; company markers show `company_score` from closest snapshot at selected date → TASK-005, TASK-006, TASK-007, TASK-010, TASK-011, TASK-012, TASK-013
- AC-003: Playback mode started → events appear chronologically; at 16× a 1-hour window plays in ~3.75 minutes; Play/Pause/Reset controls function → TASK-003, TASK-004, TASK-007, TASK-008, TASK-011, TASK-012, TASK-013
- AC-004: Any mode with zero events → map displays contextual human-readable message, not a blank canvas → TASK-009, TASK-012, TASK-013
- AC-005: Historical mode → switching back to Live reconnects WebSocket; real-time delivery resumes without page reload → TASK-002, TASK-007, TASK-012, TASK-013

## Acceptance Notes

AC-003 specifies "approximately 3.75 minutes" for a 1-hour window at 16×. The `PlaybackEngine` satisfies this mathematically: `3 600 000 ms / 16 = 225 000 ms`. The integration test in TASK-013 uses vitest fake timers to advance by exactly `225 000 ms` and asserts all events are visible. In production, `requestAnimationFrame` frame timing will introduce sub-second variation, which is within the "approximately" tolerance.

The `useScoreAtTime` hook (TASK-006) only activates in `timeMode="historical"`. In `timeMode="playback"`, score coloring is not applied (playback focuses on event chronology, not time-machine score isolation). This matches the requirement scope — Historical mode is the time-machine view; Playback is a chronological animation.

## Risks and Notes

- **`useEventFeed` extension without breaking Live mode:** The strategy extension in TASK-012 adds a conditional that gates the historical/playback fetch paths. The Live mode code path through `useEventFeed` must not be altered; regression is guarded by TASK-013's live-reconnect test which checks that the WS subscription still fires after mode switch.

- **Score-at-time query performance:** The `DISTINCT ON (company_id, indicator_id)` query over the `company_score` TimescaleDB hypertable is an indexed time-series range scan. With the existing `computed_at` partition dimension and a `(company_id, indicator_id, computed_at DESC)` index (provided by PLAN-F-017's migration), this query is expected to be fast for the 200-company universe. If the tracked universe grows beyond 1000 companies, consider replacing the `ANY(:company_ids)` array parameter with a temporary table join.

- **`useMapMode` extension (TASK-002) and PLAN-F-019 coupling:** `useMapMode.ts` was defined in PLAN-F-019 TASK-009 with only `"global" | "portfolio" | "sector"` context state. This plan extends it with a new state dimension. The extension must be backwards-compatible: the existing `SET_MODE` and `SET_SECTOR` actions must behave identically. Add new actions `SET_TIME_MODE`, `SET_DATE_RANGE`, `SET_PLAYBACK_SPEED` without removing or changing existing ones. The `useTimeModeState` hook in this plan wraps the new slice as a separate hook so the time-mode state can be independently tested without pulling in the context-mode reducer.

- **DateRangeSlider and 2-year retention limit:** The `company_score` hypertable retains 2 years of history (D4). The `<DateRangeSlider>` does not enforce a 2-year ceiling; however, the backend `GET /api/v1/scores/history` endpoint will silently return empty results for dates beyond the retention window rather than an error. The frontend empty state message covers this case via the "No events found between {dates}" path.

- **Playback and WebSocket isolation:** While in Playback mode the WebSocket subscription must be suspended (same as Historical mode). Leaving it active would mix real-time events into the playback buffer, corrupting chronological ordering. TASK-012 explicitly suspends the WS subscription whenever `timeMode !== "live"`.
