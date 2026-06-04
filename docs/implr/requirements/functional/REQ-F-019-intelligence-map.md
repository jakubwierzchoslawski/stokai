---
req_id: REQ-F-019
slug: intelligence-map
title: Intelligence Map (Primary Interface)
type: functional
status: approved
complexity: XL
tdd_required: true
source_docs:
  - ui-design-digest.md
  - system-description-digest.md
dependencies:
  - { id: "", reason: "portfolio-scoring-and-geo-modifier: Score updates propagated via WebSocket to map" }
  - { id: "", reason: "event-classification-and-extraction: geo_events with categories and intensities required for map rendering" }
superseded_by:
jira:
  id:
  issue_type: Story
  epic_link:
  priority: High
  labels: [frontend, map, real-time, webgl]
  story_points:
  components: [intelligence-map, frontend]
created_at: 2026-06-02T00:00:00Z
updated_at: 2026-06-02T00:00:00Z
---

# REQ-F-??? — Intelligence Map (Primary Interface)

## Domain Context
The Intelligence Map is the home screen and primary decision interface. React 18 + TypeScript, MapLibre GL JS, custom WebGL pulse layer, Supercluster clustering. The application opens directly to the map — no landing page or dashboard intermediary.

## Summary
The system must render the world map as the application root route with animated WebGL event pulses, zoom-level-driven Supercluster clustering (with custom clusterProperties for category + max intensity), intensity-5 events always punching through clustering, and real-time updates via WebSocket in Live mode.

## Detailed Description
As specified in ui-design-digest.md §Business Rules items 1–25 and system-description-digest.md §System Behaviours Required:

**Technology stack:** React 18 + TypeScript, MapLibre GL JS, Supercluster, custom WebGL pulse layer, D3 for pulse animation, TanStack Query for data fetching.

**Pulse encoding:**
- Color = event category; 6 fixed colorblind-safe colors (one per category)
- Size = intensity (1–5)
- Animation rate = recency (fast/bright for new events; slow glow over relevance window; static dot at end of window)

**Zoom-level clustering rules (Supercluster):**
- z0–z2 (world): clustered by region; bubble = event count, color = dominant category, ring = max intensity
- z3–z4 (continental): country-level groups
- z5–z6 (regional): sub-country clusters; high-intensity events de-cluster
- z7+ (local): every event is an individual pulse, full granularity
- Intensity-5 events always punch through clustering at all zoom levels

**Cluster interaction:**
- Click cluster → zoom in one level + re-center
- Hover cluster → show category-breakdown donut
- Click individual pulse → open popup

**Context modes:** Global (all events), Portfolio (events affecting holdings), Sector (filter by sector)

**Score-coloring overlay:** When a scoring profile is active and "show portfolio companies" is on, affected companies render as secondary markers near the event colored by custom score (green→red), connected by a thin line.

**Live mode:** WebSocket connection delivers real-time event pulses.

**Filters:** Checkbox category/intensity filters with immediate hide (no reload).

**Empty/quiet state:** Meaningful human-readable message when no events are visible.

## Desired Outcome
Users open the application and see an up-to-date world map with animated event pulses, can filter and zoom to explore events at any granularity, and immediately understand which events affect their portfolio without navigating away from the map.

## Acceptance Criteria
- [ ] AC-001: Given the application loads, the route `/ ` renders the MapLibre GL JS world map as the first and only visible screen without any intermediate landing page or dashboard.
- [ ] AC-002: Given events exist in the system, pulses render with color = category (from the 6 colorblind-safe palette), size proportional to intensity (1–5), and animation rate decaying over the event's relevance window.
- [ ] AC-003: Given the user is at zoom level z0–z2, events are clustered by Supercluster with custom clusterProperties aggregating category counts and max intensity per cluster; clicking a cluster zooms in one level.
- [ ] AC-004: Given an event with intensity=5 exists, it renders as an individual pulse at all zoom levels (z0–z7+) and is never hidden inside a cluster.
- [ ] AC-005: Given Live mode is active, a WebSocket connection is established on map load and new events appear as pulses within 5 seconds of being processed by the pipeline.
- [ ] AC-006: Given no events match the current filter/context, the map displays a human-readable message (e.g., "Quiet session. 2 low-intensity events near your holdings") rather than a blank or broken state.
- [ ] AC-007: Given a category checkbox filter is toggled, matching event pulses immediately hide or show without a page reload.

## Out of Scope
- Map tiles hosting (MapLibre GL uses external tile sources configured via environment)
- 3D globe projection (2D mercator map for MVP)
- Offline map support

## Data Models
```
Event/Pulse (frontend):
  event_id: UUID
  category: string[]
  intensity: int (1-5)
  headline: string
  timestamp: ISO string
  lat: float
  lon: float
  relevance_window_end: ISO string
  affected_companies: list[{company_id, ticker, score_delta}]

ClusterProperties (Supercluster):
  categories: dict[string, int]  -- category → count
  max_intensity: int
  event_count: int
```

## Process Sequence
1. App loads → root route renders MapLibre GL map
2. WebSocket connection established (Live mode)
3. Initial events fetched via TanStack Query (REST endpoint)
4. Events rendered as Supercluster points with custom clusterProperties
5. User zooms: Supercluster recomputes clusters per zoom level
6. Intensity-5 events bypassed from clustering
7. WebSocket events push new geo_events → add to Supercluster data source
8. User clicks cluster: zoom+recenter; clicks pulse: open popup

## Subtasks
- [ ] ST-001: Implement MapLibre GL JS map with React 18 + TypeScript — complexity: M
- [ ] ST-002: Implement custom WebGL pulse layer with color/size/animation encoding — complexity: XL
- [ ] ST-003: Implement Supercluster integration with custom clusterProperties — complexity: L
- [ ] ST-004: Implement intensity-5 clustering bypass — complexity: S
- [ ] ST-005: Implement zoom-level cluster rendering rules (z0–z7+) — complexity: M
- [ ] ST-006: Implement cluster hover donut, click zoom-in, pulse click popup trigger — complexity: M
- [ ] ST-007: Implement WebSocket subscription for Live mode event delivery — complexity: M
- [ ] ST-008: Implement context mode switching (Global/Portfolio/Sector) — complexity: M
- [ ] ST-009: Implement category/intensity filter controls — complexity: S
- [ ] ST-010: Implement score-coloring company overlay — complexity: M
- [ ] ST-011: Implement empty/quiet state messages — complexity: S
- [ ] ST-012: Component and integration tests for clustering, zoom rules, filter behavior — complexity: L

## Source Document References
| Document | Relevant Section | Contribution |
|----------|-----------------|-------------|
| ui-design-digest.md | §Business Rules items 1-25; §System Behaviours Required; §Architecture Signals | Map-first SPA, pulse encoding, zoom rules, clustering, context modes, WebSocket, intensity-5 bypass, empty states |
| system-description-digest.md | §System Behaviours Required; §Integration Points | WebGL pulses, category/intensity filters, MapLibre GL JS, Supercluster |
