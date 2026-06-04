---
plan_id: PLAN-F-019
slug: intelligence-map
title: Intelligence Map (Primary Interface)
linked_requirement: REQ-F-019
type: functional
status: done
blocked_reason:
complexity: XL
tdd_required: true
executed_at: 2026-06-04T00:00:00Z
linked_nfrs:
  - { id: REQ-N-001, reason: "Initial map render must complete within 3 seconds on a 10,000-event dataset; Supercluster index must be built off the main thread" }
dependencies:
  - { id: PLAN-F-018, reason: "GeoModifierPayload delivered via WebSocket score channel; score overlay subscribes to it" }
  - { id: PLAN-F-002, reason: "geo_events must carry category[], intensity, lat, lon after classification step 2" }
executed_at:
reviewed_at:
review_id:
created_at: 2026-06-03T00:00:00Z
updated_at: 2026-06-03T00:00:00Z
---

# PLAN-F-019 — Intelligence Map (Primary Interface)

## Linked Requirement
**REQ-F-019** — Intelligence Map (Primary Interface)
Status: approved | Jira:

## Objective

Build the Intelligence Map as the application root route (`/`): a MapLibre GL JS world map
with a custom WebGL pulse layer for animated event markers, Supercluster-powered zoom-level
clustering with custom `clusterProperties` that aggregate category counts and max intensity,
and a Web Worker that builds the Supercluster index off the main thread to sustain a
sub-3-second initial render on 10,000-event datasets. Events are fetched on mount via
`GET /api/v1/events` (TanStack Query), and real-time additions are delivered via a WebSocket
subscription on `ws://host/ws/events`. Intensity-5 events always bypass clustering. A
score-coloring overlay draws secondary company markers when a scoring profile is active.
Category/intensity checkbox filters hide pulses immediately without a network round-trip.
Empty and quiet states display a human-readable message. The application has no landing
dashboard — this component is the React application root.

## Architecture Context

This plan lives entirely in **Layer 6 — Presentation** (ARCHITECTURE.md §11, §4). It
consumes two Layer 5 — Serving endpoints defined in the architecture:

- `GET /api/v1/events?bbox=...&zoom=...&context=...` — initial event load with spatial and
  context filters (ARCHITECTURE.md §5).
- `ws://host/ws/events` — real-time event push after Mode A pipeline step 12
  (ARCHITECTURE.md §13). This channel is the same one already broadcast by PLAN-F-001.
- `ws://host/ws/scores` — `GeoModifierPayload` messages broadcast by PLAN-F-018's
  `broadcast_geo_modifier` after each geo-modifier run.

**Frontend stack (ARCHITECTURE.md §11, §13):**
- React 18 + TypeScript, Vite build.
- MapLibre GL JS — mandatory (D10); open-source WebGL renderer.
- Supercluster — mandatory for clustering with custom `clusterProperties`.
- D3 — scoped to WebGL pulse animation and decay calculations only.
- TanStack Query — data fetching and client-side caching.
- WebSocket subscription manager (existing in-app utility, extended here).
- shadcn/ui — standard UI components (filter panel, empty state cards).

**Performance (ARCHITECTURE.md §9):** Initial render within 3 seconds on 10,000 events.
Supercluster index construction is delegated to a Web Worker to avoid blocking the main
thread during React rendering.

**Routing:** The Intelligence Map is mounted at `/` as the application root via React
Router (or equivalent). No redirect from a dashboard route — the router's default path
directly renders `<IntelligenceMap />`.

**PLAN-F-018 integration:** The score overlay reads `GeoModifierPayload` messages from the
WebSocket score channel and updates company marker colors without re-fetching the full
event list. The `affected_companies` field of `GeoModifierPayload` maps
`company_id → new_geo_adjusted` which drives the green→red color ramp of secondary markers.

**PLAN-F-002 integration:** Every `geo_event` record arriving from the API or WebSocket
carries `category[]`, `intensity`, `lat`, `lon`, and `relevance_window_end` — all
populated by the Mode A classify_event step (PLAN-F-002). This plan treats those fields as
a stable contract and does not produce them.

## Applied NFR Constraints

| NFR | Constraint | Impact on this plan |
|-----|-----------|---------------------|
| REQ-N-001 | Initial map render ≤ 3 seconds on 10,000-event dataset | Supercluster index built in a dedicated Web Worker (TASK-004); MapLibre layer added only after the worker responds with clustered points; no synchronous index build on mount |

## Component Design

### New Components

```
src/
  features/
    intelligence-map/
      IntelligenceMap.tsx            — root map component; mounted at route "/"
      IntelligenceMap.test.tsx       — RTL + vitest unit tests
      components/
        PulseLayer.tsx               — custom MapLibre layer: WebGL pulse rendering
        PulseLayer.test.tsx
        ClusterLayer.tsx             — Supercluster cluster bubble + ring renderer
        ClusterLayer.test.tsx
        ClusterDonut.tsx             — category-breakdown donut on cluster hover
        ClusterDonut.test.tsx
        ScoreOverlay.tsx             — secondary company markers coloured by geo_adjusted
        ScoreOverlay.test.tsx
        FilterPanel.tsx              — category/intensity checkbox sidebar
        FilterPanel.test.tsx
        EmptyState.tsx               — quiet/no-results human-readable message
        EmptyState.test.tsx
        MapContextSwitcher.tsx       — Global / Portfolio / Sector mode toggle
        MapContextSwitcher.test.tsx
      hooks/
        useEventFeed.ts              — TanStack Query fetch + WebSocket merge for events
        useEventFeed.test.ts
        useScoreOverlay.ts           — subscribes to ws/scores; maintains company delta map
        useScoreOverlay.test.ts
        useMapFilters.ts             — filter state (category, intensity); pure reducer
        useMapFilters.test.ts
        useMapMode.ts                — Global/Portfolio/Sector context state
        useMapMode.test.ts
      workers/
        supercluster.worker.ts       — Web Worker: receives GeoJSON, returns clusters
        supercluster.worker.test.ts
      lib/
        pulse-animation.ts           — D3 decay calculations for pulse rate/size
        pulse-animation.test.ts
        cluster-properties.ts        — Supercluster clusterProperties reducers
        cluster-properties.test.ts
        color-palette.ts             — 6-color colorblind-safe category palette (constants)
        empty-state-message.ts       — message generator given filter + context state
        empty-state-message.test.ts
      types/
        map.types.ts                 — EventPulse, ClusterProps, ScoreMarker interfaces
      api/
        events.api.ts                — GET /api/v1/events wrapper (TanStack Query queryFn)

  app/
    router.tsx                       — application router; "/" → <IntelligenceMap />
                                       (modified if it exists, created if it does not)

tests/
  integration/
    intelligence-map/
      map-initial-load.test.tsx      — render + API mock; assert map mounts at route "/"
      map-websocket.test.tsx         — WebSocket event push; assert pulse appears
      map-filters.test.tsx           — filter toggle; assert pulse visibility
```

### Modified Components

| File | Change | Reason |
|------|--------|--------|
| `src/app/router.tsx` | Register route `"/"` pointing to `<IntelligenceMap />` as the default root route with no intermediate dashboard | AC-001 — map is the first and only screen on load |
| `src/api/websocket-manager.ts` (or equivalent) | Subscribe to `ws/events` channel and `ws/scores` channel; expose `onEvent` and `onScoreUpdate` callbacks consumed by `useEventFeed` and `useScoreOverlay` respectively | AC-005 (live mode), score overlay integration |

### Interfaces and Contracts

```typescript
// src/features/intelligence-map/types/map.types.ts

export interface EventPulse {
  event_id: string;              // UUID
  category: string[];
  intensity: 1 | 2 | 3 | 4 | 5;
  headline: string;
  timestamp: string;             // ISO 8601
  lat: number;
  lon: number;
  relevance_window_end: string;  // ISO 8601
  affected_companies: Array<{
    company_id: string;
    ticker: string;
    score_delta: number;
  }>;
}

export interface ClusterProps {
  categories: Record<string, number>;  // category → count
  max_intensity: number;               // 1–5
  event_count: number;
}

export interface ScoreMarker {
  company_id: string;
  ticker: string;
  lat: number;
  lon: number;
  geo_adjusted: number;          // 0–100; drives green→red ramp
  score_delta: number;           // new_geo_adjusted - previous
}

// Web Worker message contracts
export interface WorkerRequest {
  events: EventPulse[];
  zoom: number;
  bbox: [number, number, number, number];  // [west, south, east, north]
}

export interface WorkerResponse {
  clusters: GeoJSON.FeatureCollection;
  individualEvents: EventPulse[];          // intensity-5 or zoom ≥ 7 events
}


// src/features/intelligence-map/api/events.api.ts

export interface EventsQueryParams {
  bbox?: string;       // "west,south,east,north"
  zoom?: number;
  context?: "global" | "portfolio" | "sector";
  sector?: string;
}

export async function fetchEvents(params: EventsQueryParams): Promise<EventPulse[]>;


// src/features/intelligence-map/lib/cluster-properties.ts

// Supercluster clusterProperties reducers (passed to new Supercluster({ clusterProperties }))
export const clusterProperties: Supercluster.ClusterProperties = {
  categories: [
    ["+", ["accumulated"], ["get", "categories"]],
    ["get", "categories"]         // initial value: the event's first category string
  ],
  max_intensity: [
    ["max", ["accumulated"], ["get", "intensity"]],
    ["get", "intensity"]
  ],
  event_count: [["+", ["accumulated"], 1], 1],
};


// src/features/intelligence-map/lib/pulse-animation.ts

export interface PulseAnimationParams {
  timestamp: string;              // event arrival ISO string
  relevance_window_end: string;   // ISO string
  intensity: number;              // 1–5; controls base size
}

export interface PulseState {
  radius: number;    // CSS px; intensity * BASE_RADIUS
  opacity: number;   // 0–1; decays linearly over relevance window
  period_ms: number; // animation cycle; fast (400ms) → slow (2000ms) → static (0)
}

export function computePulseState(params: PulseAnimationParams, now: Date): PulseState;


// src/features/intelligence-map/workers/supercluster.worker.ts
// (Comlink or raw postMessage; input/output are WorkerRequest / WorkerResponse)
```

## Implementation Tasks

### TASK-001: Type definitions and color palette · S/no-TDD · src/features/intelligence-map/types/map.types.ts,src/features/intelligence-map/lib/color-palette.ts

Define all TypeScript interfaces: `EventPulse`, `ClusterProps`, `ScoreMarker`,
`WorkerRequest`, `WorkerResponse` in `map.types.ts`. Define the six fixed
colorblind-safe category colors as a `CATEGORY_COLORS` constant map in `color-palette.ts`.
The palette must be Okabe-Ito or equivalent; document the palette name and hex values in a
comment. Export both from their respective barrel `index.ts` files.

No logic, no rendering, no side effects — these are pure data contracts.

**AC covered**: AC-002 (color-per-category contract established), enables all subsequent tasks

---

### TASK-002: Events API wrapper and TanStack Query hook · M/TDD · src/features/intelligence-map/api/events.api.ts,src/features/intelligence-map/hooks/useEventFeed.ts,src/features/intelligence-map/hooks/useEventFeed.test.ts

Implement `fetchEvents(params: EventsQueryParams): Promise<EventPulse[]>` in
`events.api.ts`. The function calls `GET /api/v1/events` with bbox, zoom, and context as
query parameters. It validates the response shape (Zod schema) and throws a typed
`EventFetchError` on HTTP errors or schema violations. Attach JWT from the application auth
context as the `Authorization: Bearer` header.

Implement `useEventFeed(context, zoom, bbox)` as a TanStack Query `useQuery` hook that:
- Fetches the initial event list via `fetchEvents`.
- Maintains a local `EventPulse[]` state extended by WebSocket pushes.
- Subscribes to `ws/events` via the existing WebSocket manager on hook mount; appends
  validated incoming `EventPulse` objects to the local list.
- Unsubscribes on unmount.
- Returns `{ events, isLoading, isError, error }`.

**Tests to write first (TDD):**
- `useEventFeed` with MSW mock returning 3 events → `events` has length 3 after `isLoading` resolves
- Simulated WebSocket push of one event → `events` length becomes 4 without a re-fetch
- `fetchEvents` receiving HTTP 401 → throws `EventFetchError` with `code: "UNAUTHORIZED"`
- `fetchEvents` receiving a response with a malformed event (missing `lat`) → throws `EventFetchError` with `code: "SCHEMA_VIOLATION"`
- Unmounting `useEventFeed` → WebSocket unsubscribe is called exactly once (mock assertion)

**AC covered**: AC-001 (events loaded on mount), AC-005 (WebSocket subscription wired)

---

### TASK-003: Pulse animation library · M/TDD · src/features/intelligence-map/lib/pulse-animation.ts,src/features/intelligence-map/lib/pulse-animation.test.ts

Implement `computePulseState(params, now): PulseState`. The function must:
- Compute `elapsed_ratio = (now - timestamp) / (relevance_window_end - timestamp)` clamped
  to `[0, 1]`.
- `radius = intensity * BASE_RADIUS` (constant; BASE_RADIUS = 6px).
- `opacity = 1.0 - (elapsed_ratio * 0.85)` — minimum 0.15 (never fully invisible within
  the relevance window).
- `period_ms`: lerp from 400ms (at elapsed_ratio=0) to 2000ms (at elapsed_ratio=1); when
  `elapsed_ratio >= 1`, return `period_ms = 0` (static dot, no animation).
- Export `BASE_RADIUS` and `MIN_OPACITY` as named constants so layer renderers can
  reference them without magic numbers.

**Tests to write first (TDD):**
- Fresh event (elapsed_ratio=0) → `opacity` close to 1.0, `period_ms` close to 400ms
- Halfway through relevance window (elapsed_ratio=0.5) → `opacity` = 0.575, `period_ms` = 1200ms
- At end of relevance window (elapsed_ratio=1.0) → `opacity` = 0.15, `period_ms` = 0
- Past end of window (now > relevance_window_end) → `period_ms` = 0, `opacity` = 0.15 (clamped, not negative)
- Intensity=5 → radius = 30; intensity=1 → radius = 6
- `computePulseState` is a pure function: same inputs always produce identical output

**AC covered**: AC-002 (animation rate and size encoding)

---

### TASK-004: Supercluster Web Worker · M/TDD · src/features/intelligence-map/workers/supercluster.worker.ts,src/features/intelligence-map/workers/supercluster.worker.test.ts,src/features/intelligence-map/lib/cluster-properties.ts,src/features/intelligence-map/lib/cluster-properties.test.ts

Implement the Supercluster Web Worker. On `message` receipt of a `WorkerRequest`:
1. Construct a `Supercluster` instance with `clusterProperties` (from `cluster-properties.ts`)
   and `minZoom=0`, `maxZoom=7`, `radius=60`.
2. Load input `events` as GeoJSON points with properties `{category, intensity, headline,
   event_id, timestamp, relevance_window_end, affected_companies}`.
3. Partition events: any event with `intensity === 5` is placed in `individualEvents` and
   excluded from Supercluster input (intensity-5 always punches through at all zoom levels).
   Also, at zoom ≥ 7, all events go to `individualEvents`.
4. Call `supercluster.getClusters(bbox, zoom)` on the remaining events.
5. `postMessage` a `WorkerResponse` with the cluster `FeatureCollection` and the
   `individualEvents` array.

Implement `cluster-properties.ts` with the `clusterProperties` object that aggregates
`categories` (object of category→count), `max_intensity` (max), and `event_count` (sum).

**Tests to write first (TDD):**
- Worker given 5 events all within a small bbox at zoom=2 → returns 1 cluster with `event_count=5`
- Worker given one intensity-5 event + 4 intensity-3 events at zoom=2 → the intensity-5 event appears in `individualEvents`, cluster `event_count=4`
- Cluster `max_intensity` equals the highest intensity among its members
- Cluster `categories` sums counts correctly for multiple events sharing a category
- At zoom=7, all events are placed in `individualEvents` (no clusters)
- Worker is invoked off the main thread — test that the worker runs inside a `Worker` object (not inline) using a worker test harness (e.g., vitest worker environment)

**AC covered**: AC-003 (clustering with custom properties), AC-004 (intensity-5 punch-through)

---

### TASK-005: ClusterLayer component · M/TDD · src/features/intelligence-map/components/ClusterLayer.tsx,src/features/intelligence-map/components/ClusterLayer.test.tsx,src/features/intelligence-map/components/ClusterDonut.tsx,src/features/intelligence-map/components/ClusterDonut.test.tsx

Implement `<ClusterLayer clusters={...} onClusterClick={...} />`. The component:
- Renders cluster GeoJSON features from the `WorkerResponse.clusters` collection as MapLibre
  `circle` layers: circle size = log-scaled by `event_count`; circle color = dominant
  category (the category with the highest count in the `categories` object); ring color =
  `max_intensity` mapped to the intensity color ramp (1=grey → 5=red).
- On cluster click: calls `onClusterClick(cluster)`, which in `IntelligenceMap` triggers
  `map.flyTo({ zoom: currentZoom + 1, center: cluster.geometry.coordinates })`.
- Renders a `<ClusterDonut />` on hover: a D3 arc chart showing category proportions from
  the cluster's `categories` object. The donut is positioned as an absolutely-positioned
  tooltip near the hovered cluster.

`<ClusterDonut />` accepts `categories: Record<string, number>` and `colors: Record<string, string>`
and renders an SVG pie/donut using D3's `arc` and `pie` generators. It has no MapLibre
dependency.

**Tests to write first (TDD):**
- `<ClusterDonut categories={{ CONFLICT: 3, ECONOMIC: 1 }} colors={...} />` → renders 2 arc path elements with correct proportional radians (assert via `aria-label` or test-id attributes)
- `<ClusterLayer clusters={emptyFeatureCollection} />` → renders no circle elements
- `<ClusterLayer clusters={oneClusterFC} onClusterClick={mockFn} />` → simulating a click fires `mockFn` with the cluster feature
- Dominant category color is the category with the highest count (unit test on the color-selection helper function)

**AC covered**: AC-003 (cluster rendering and click-to-zoom), enables AC-001 (map populated with clusters)

---

### TASK-006: PulseLayer component (WebGL custom layer) · L/TDD · src/features/intelligence-map/components/PulseLayer.tsx,src/features/intelligence-map/components/PulseLayer.test.tsx

Implement `<PulseLayer events={EventPulse[]} activeFilters={MapFilters} />` as a MapLibre
custom layer using the `CustomLayerInterface`. The layer:
- Converts each `EventPulse` to a screen-space circle drawn via WebGL (custom vertex and
  fragment shaders): color from `CATEGORY_COLORS[event.category[0]]`, radius from
  `computePulseState().radius`, opacity from `computePulseState().opacity`.
- Uses a `requestAnimationFrame` loop to advance pulse phase offsets. The animation
  oscillation period per event is `computePulseState().period_ms`; when `period_ms = 0`,
  the event is rendered as a static filled dot with `MIN_OPACITY`.
- Filters out events excluded by `activeFilters.categories` or `activeFilters.intensities`
  before uploading to the GPU buffer — no DOM mutation, no re-render, just skip the vertex.
- On individual pulse click (MapLibre `queryRenderedFeatures`): dispatches an `onPulseClick`
  callback with the `EventPulse` so `IntelligenceMap` can open a popup.

WebGL shader requirements: vertex shader computes `gl_Position` from lng/lat to clip space
via the MapLibre projection matrix exposed as `map.transform.projMatrix`. Fragment shader
outputs the pulse color with a soft circular gradient (step or smoothstep on `gl_PointCoord`
distance from center).

**Tests to write first (TDD):**
- `computePulseState` integration: given an event arriving 30% into its window, the rendered opacity matches the expected value (unit; no DOM)
- Filter: `activeFilters = { categories: ["ECONOMIC"], intensities: [1,2,3,4,5] }` with one CONFLICT event and one ECONOMIC event → only 1 event is uploaded to the GPU buffer (assert via mock WebGL context call count)
- Filter: intensity filter `[4,5]` with three events of intensities 2, 4, 5 → 2 events in buffer
- `onPulseClick` callback is called with the correct `EventPulse` when the MapLibre click event targets the layer (mock `queryRenderedFeatures`)
- Snapshot: shader source strings are stable (guard against accidental shader regression via inline snapshot)

**AC covered**: AC-002 (pulse color/size/animation), AC-007 (immediate filter without reload)

---

### TASK-007: Filter panel and map filters hook · M/TDD · src/features/intelligence-map/components/FilterPanel.tsx,src/features/intelligence-map/components/FilterPanel.test.tsx,src/features/intelligence-map/hooks/useMapFilters.ts,src/features/intelligence-map/hooks/useMapFilters.test.ts

Implement `useMapFilters()` as a pure state hook with a reducer. State shape:
```typescript
interface MapFilters {
  categories: string[];    // active categories; all enabled by default
  intensities: number[];   // active intensity levels (1–5); all enabled by default
}
```
Actions: `TOGGLE_CATEGORY(category: string)`, `TOGGLE_INTENSITY(level: number)`.
Toggling the last active category or intensity is a no-op (at least one must remain
checked). The hook exposes `{ filters, toggleCategory, toggleIntensity }`.

Implement `<FilterPanel filters={MapFilters} onToggleCategory={...} onToggleIntensity={...} />`
using shadcn/ui `Checkbox` components. Each category checkbox is labeled with its name
and colored with its `CATEGORY_COLORS` swatch. Intensity checkboxes are numbered 1–5.
Filter changes call the respective callback immediately — no debounce, no submit button.

**Tests to write first (TDD):**
- Initial state: all 6 categories enabled, all 5 intensities enabled
- `TOGGLE_CATEGORY("CONFLICT")` when 2 categories active → categories array excludes "CONFLICT"
- `TOGGLE_CATEGORY("CONFLICT")` when "CONFLICT" is the only active category → state unchanged (no-op guard)
- `TOGGLE_INTENSITY(3)` when active → intensity 3 removed from array
- `TOGGLE_INTENSITY(3)` when 3 is the only active intensity → state unchanged
- `<FilterPanel />` with mock callbacks: clicking a category checkbox fires `onToggleCategory` with the correct category string

**AC covered**: AC-007 (immediate toggle without reload)

---

### TASK-008: Score overlay hook and component · M/TDD · src/features/intelligence-map/hooks/useScoreOverlay.ts,src/features/intelligence-map/hooks/useScoreOverlay.test.ts,src/features/intelligence-map/components/ScoreOverlay.tsx,src/features/intelligence-map/components/ScoreOverlay.test.tsx

Implement `useScoreOverlay(profileActive: boolean)`. When `profileActive` is false, the
hook returns an empty `ScoreMarker[]` and does not subscribe to the WebSocket. When true,
the hook subscribes to the `ws/scores` WebSocket channel and maintains a `Map<company_id,
ScoreMarker>` in state, updating each entry when a `GeoModifierPayload` message arrives.
It returns `scoreMarkers: ScoreMarker[]` (the current values of the map).

The `ScoreMarker.lat` and `lon` values must be sourced from the company's associated event
coordinates (use the `affected_companies[].company_id` from the current event list — join
in-memory; no extra fetch required).

`geo_adjusted` 0–100 is mapped to a green→red linear color ramp:
- 0–33: `hsl(0, 80%, 50%)` (red; low score)
- 34–66: `hsl(40, 80%, 50%)` (amber)
- 67–100: `hsl(120, 60%, 40%)` (green; high score)

Implement `<ScoreOverlay markers={ScoreMarker[]} />` as a MapLibre `GeoJSON` source +
`circle` layer rendering secondary markers at company coordinates, colored by the ramp, with
a thin `line` layer connecting the company marker to its associated event pulse centroid.

**Tests to write first (TDD):**
- `useScoreOverlay(false)` → returns empty array; no WebSocket subscription established
- `useScoreOverlay(true)` receiving a `GeoModifierPayload` with 2 companies → `scoreMarkers` has 2 entries
- Second `GeoModifierPayload` for the same company → entry is updated (not duplicated)
- `geo_adjusted = 20` → color in red range; `geo_adjusted = 80` → color in green range (unit test on the color ramp function)
- Unmounting `useScoreOverlay(true)` → WebSocket unsubscribe called once

**AC covered**: AC-005 (score-coloring overlay wired to WebSocket score channel)

---

### TASK-009: Context mode switcher and map mode hook · S/no-TDD · src/features/intelligence-map/components/MapContextSwitcher.tsx,src/features/intelligence-map/components/MapContextSwitcher.test.tsx,src/features/intelligence-map/hooks/useMapMode.ts

Implement `useMapMode()` hook: state `{ mode: "global" | "portfolio" | "sector", sector: string | null }`,
actions `SET_MODE(mode)` and `SET_SECTOR(sector)`. Switching mode triggers re-execution of
the `useEventFeed` query (via TanStack Query key change) with the new `context` parameter.

Implement `<MapContextSwitcher mode={...} onSetMode={...} />` as a three-button toggle
(Global / Portfolio / Sector) using shadcn/ui `ToggleGroup`. When "Sector" is selected, a
`Select` dropdown appears for sector choice. The switcher is rendered as an overlay at the
top-left of the map canvas via `position: absolute`.

**AC covered**: AC-001 (Global/Portfolio/Sector context modes available from map root)

---

### TASK-010: Empty state component and message generator · M/TDD · src/features/intelligence-map/components/EmptyState.tsx,src/features/intelligence-map/components/EmptyState.test.tsx,src/features/intelligence-map/lib/empty-state-message.ts,src/features/intelligence-map/lib/empty-state-message.test.ts

Implement `generateEmptyStateMessage(context, filters, eventCount): string`. The function
produces a contextual human-readable message when no events pass current filters:
- If `eventCount > 0` but all are filtered: `"X events hidden by your filters. Try enabling more categories or intensities."`
- If `mode === "portfolio"` and `eventCount === 0`: `"Quiet session. No events near your holdings right now."`
- If low-intensity events are near holdings (future hook; pass as `nearHoldingsCount`):
  `"Quiet session. {nearHoldingsCount} low-intensity event(s) near your holdings."`
- Fallback: `"No events to display right now. Markets are quiet."`

Implement `<EmptyState message={string} />` as a centered, floating translucent card
(shadcn/ui `Card`) rendered over the map via absolute positioning. It is only shown when
`events.length === 0` after filtering.

**Tests to write first (TDD):**
- `generateEmptyStateMessage("global", allFiltersActive, 0)` → contains "quiet" or "no events" (case-insensitive)
- `generateEmptyStateMessage("portfolio", allFiltersActive, 0)` → contains "holdings"
- `generateEmptyStateMessage("global", categoriesFiltered, 15)` → mentions the count "15" and references filters
- `generateEmptyStateMessage("global", allFiltersActive, 0, 2)` → contains "2" and "near your holdings"
- `<EmptyState />` with a message string → `getByText(message)` is in the DOM

**AC covered**: AC-006 (human-readable empty/quiet state)

---

### TASK-011: IntelligenceMap root component and router wiring · L/TDD · src/features/intelligence-map/IntelligenceMap.tsx,src/features/intelligence-map/IntelligenceMap.test.tsx,src/app/router.tsx

Implement `<IntelligenceMap />` as the composition root:
1. Initializes MapLibre GL JS `Map` instance in a `useEffect` pointing at a public tile
   source (e.g., `https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json`).
2. Mounts `<PulseLayer>` and `<ClusterLayer>` once the map `load` event fires.
3. Calls `useEventFeed(mode, zoom, bbox)`, re-running the query on zoom/bbox change
   (debounced 200ms to avoid thrashing on scroll).
4. Dispatches `WorkerRequest` to `supercluster.worker.ts` when the event list or zoom/bbox
   changes; receives `WorkerResponse` and passes clusters to `<ClusterLayer>` and
   `individualEvents` to `<PulseLayer>`.
5. Integrates `useMapFilters()`, passing `filters` to `<PulseLayer>` and `<FilterPanel>`.
6. Integrates `useMapMode()`, passing `mode` to the query and `<MapContextSwitcher>`.
7. Integrates `useScoreOverlay(profileActive)`, rendering `<ScoreOverlay>` when markers
   exist.
8. Derives `showEmptyState` = `events.length === 0 && !isLoading`; renders `<EmptyState>`
   when true.
9. On individual pulse click: opens a MapLibre `Popup` with event title, intensity badge,
   and headline. The popup includes an "Expand" button (wired to the progressive disclosure
   panel — PLAN-F-020; stub the callback here).

Wires the application router so that `"/"` renders `<IntelligenceMap />` with no
intermediate redirect or dashboard.

**Tests to write first (TDD):**
- Mounting `<IntelligenceMap />` at route `"/"` with MSW returning 0 events → `<EmptyState>` is visible after loading
- Mounting with 5 events returned → `<EmptyState>` is not rendered; map container is visible
- WebSocket message received with a new event → hook updates event list (assert via spy on `useEventFeed`)
- Cluster click → `map.flyTo` is called with `zoom: currentZoom + 1` (mock MapLibre)
- Filter toggle: toggling a category filter → `PulseLayer` receives updated `activeFilters`
- Context switcher toggled to "portfolio" → `useEventFeed` query is re-executed with `context: "portfolio"` (TanStack Query key assertion)
- Route `"/"` renders `<IntelligenceMap />` without any redirect (integration: React Router renders test)

**AC covered**: AC-001, AC-003, AC-004, AC-005, AC-006, AC-007

---

### TASK-012: Integration tests — initial load and live mode · M/TDD · tests/integration/intelligence-map/map-initial-load.test.tsx,tests/integration/intelligence-map/map-websocket.test.tsx,tests/integration/intelligence-map/map-filters.test.tsx

Write integration test suites using React Testing Library + MSW + fake WebSocket:

**`map-initial-load.test.tsx`:**
- Render `<IntelligenceMap />` at `"/"` with MSW serving 10 events → assert map container
  element is present in the DOM; assert no redirect occurred.
- Assert `<EmptyState>` is absent when events are loaded.
- Assert `GET /api/v1/events` was called exactly once on mount with no extra fetches.

**`map-websocket.test.tsx`:**
- Establish a fake `ws://host/ws/events` server. Render the component. Push one
  `EventPulse` via the fake server. Assert that `useEventFeed` now returns 11 events
  (10 initial + 1 pushed) without any new HTTP fetch.
- Push an invalid WebSocket message → assert the component does not crash (error boundary
  not triggered); event count unchanged.

**`map-filters.test.tsx`:**
- Render with 3 CONFLICT events and 2 ECONOMIC events. Toggle off CONFLICT via
  `<FilterPanel>`. Assert that the events passed to `<PulseLayer>` now contain only
  2 ECONOMIC events (spy on PulseLayer prop).
- Re-enable CONFLICT → 5 events passed to PulseLayer. Assert no `GET /api/v1/events`
  re-fetch occurred during either toggle.

**Tests to write first (TDD):**
(Covered above — each bullet above is a discrete test case.)

**AC covered**: AC-001, AC-005, AC-007

---

## Acceptance Criteria Coverage

- AC-001: Application loads → route `/` renders the MapLibre GL JS world map as the first and only visible screen without any intermediate landing page or dashboard → TASK-009, TASK-011, TASK-012
- AC-002: Events exist → pulses render with color = category (6 colorblind-safe palette), size proportional to intensity (1–5), animation rate decaying over the event's relevance window → TASK-001, TASK-003, TASK-006
- AC-003: User at zoom level z0–z2 → events clustered by Supercluster with custom clusterProperties aggregating category counts and max intensity per cluster; clicking a cluster zooms in one level → TASK-004, TASK-005, TASK-011
- AC-004: Event with intensity=5 exists → renders as individual pulse at all zoom levels (z0–z7+), never hidden inside a cluster → TASK-004, TASK-011
- AC-005: Live mode active → WebSocket connection established on map load; new events appear as pulses within 5 seconds; score overlay subscribes to ws/scores → TASK-002, TASK-008, TASK-011, TASK-012
- AC-006: No events match current filter/context → map displays human-readable message rather than blank or broken state → TASK-010, TASK-011
- AC-007: Category checkbox filter toggled → matching event pulses immediately hide or show without a page reload → TASK-006, TASK-007, TASK-011, TASK-012

## Acceptance Notes

AC-005 targets "within 5 seconds" for live-mode pulses. The constraint is a pipeline SLA
(Mode A end-to-end ≤ 90 seconds from event arrival; WebSocket dispatch at step 12). The
frontend's contribution is zero-delay: `useEventFeed` appends the WebSocket message to the
event list synchronously upon receipt. The 5-second sub-target is meaningful only when the
backend pipeline is also running. Integration tests use a fake WebSocket server and assert
immediate update with no polling.

The score-coloring overlay (AC-005 secondary assertion) co-locates company secondary markers
at the event coordinates of the associated pulse rather than at the company's actual
headquarters. This is a MVP simplification — a future plan can add company `lat/lon` to
the `company` table and use those coordinates instead.

## Risks and Notes

- **WebGL custom layer complexity (TASK-006):** Custom WebGL layers in MapLibre require
  managing shader compilation, buffer uploads, and the MapLibre projection matrix. Shader
  errors are silent in production (WebGL does not throw; the layer simply renders nothing).
  Test the shader strings against a headless WebGL context in CI. Consider using
  `deck.gl` ScatterplotLayer as a fallback if the custom shader proves unstable — it wraps
  MapLibre with hardware-accelerated layers and would reduce shader authoring risk without
  changing the user-visible behaviour.

- **Web Worker bundling (TASK-004):** Vite's Worker support requires the worker file to be
  imported as `new Worker(new URL('./workers/supercluster.worker.ts', import.meta.url),
  { type: 'module' })`. Vitest requires the `@vitest/web-worker` plugin or manual mocking
  to test workers. Verify Vite + Vitest configuration supports this pattern before TASK-004
  implementation begins.

- **Supercluster clusterProperties with object accumulator:** Supercluster's
  `clusterProperties` spec supports numeric `max` and `sum` operations natively. Aggregating
  a `categories` object (key → count) requires a map-reduce expression; the standard
  approach uses a string-concatenated intermediate that is decoded post-cluster. An
  alternative is to expand to 6 fixed boolean properties (`is_CONFLICT`, `count_CONFLICT`,
  etc.) and aggregate numerically. Choose the numeric-expansion approach for correctness and
  testability; document the tradeoff in `cluster-properties.ts`.

- **MapLibre tile source for MVP:** No tile-hosting budget is allocated. Use a free public
  CDN-hosted style (CARTO Dark Matter or MapTiler Community) with an appropriate attribution.
  Store the style URL in an environment variable (`VITE_MAP_STYLE_URL`) so it can be swapped
  without code changes.

- **RTL + MapLibre canvas testing:** React Testing Library renders a JSDOM environment that
  does not support WebGL. MapLibre cannot mount a real canvas. All component tests that
  instantiate MapLibre must mock the `maplibre-gl` module (`vi.mock('maplibre-gl', ...)`)
  and assert on prop/callback behavior, not on actual canvas rendering.

- **Popup stub for progressive disclosure (TASK-011):** The `onPulseClick` → expand
  callback is stubbed here as a no-op console log. PLAN-F-020 (Progressive Disclosure UI)
  owns the side panel implementation. The stub must be wired as an injectable prop
  (`onExpandEvent?: (event: EventPulse) => void`) so PLAN-F-020 can inject the real handler
  without modifying `IntelligenceMap.tsx`.
