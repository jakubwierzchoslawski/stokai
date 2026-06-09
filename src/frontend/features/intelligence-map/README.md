# Intelligence Map

The hero route at `/`. Renders a MapLibre world map with live and historical
event pulses and clusters.

## Data flow

```
GET /api/v1/events                ─┐
  (REST seed via lib/api/client)   │
                                   ├──► useEventFeed merges into local state ──► supercluster worker
WSS /api/v1/events/feed            │                                               │
  (apiSocket, appends frames)     ─┘                                               ▼
                                                                         MapLibre PulseLayer / ClusterLayer
```

## Time modes

- **Live** — `useEventFeed` + WS.
- **Historical** — `useHistoricalEvents`, date-range slider.
- **Playback** — replays historical range over a virtual clock.

## Pulse click

`PulseLayer` invokes `onPulseClick(event)` on the `IntelligenceMap` parent,
which opens a MapLibre Popup with `EventPopup`. "View details →" navigates
to `/events/:eventId/deep-dive` (handled by Phase 2b).

## Stub mode

`StubModeBadge` reads `useIntegrations()`. When `market_data` or `news` is
`mode: stub`, the badge sits top-left of the canvas. Click it for the reason
and an admin link.

## Score overlay

`useScoreOverlay` subscribes to `WSS /ws/scores` via `apiSocket`. When a
scoring profile is active, affected portfolio companies appear as secondary
markers near each event, colored by geo-adjusted score (green → red ramp).
