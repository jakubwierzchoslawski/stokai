---
source_file: docs/kb/ui_design.md
checksum: 658153c855e3b69bc90624b223744025
digested_at: 2026-06-02T00:00:00Z
domain: root
doc_type: other
arch_relevant: auto
---

# Digest: ui_design.md

## Business Rules
1. The application must open directly to the map; no landing dashboard may bury the map one click deep.
2. UI depth follows progressive disclosure: pulse → popup (3-second read) → side panel (30-second read) → full analysis (deep dive); the user controls depth.
3. Every AI output must display confidence level and sample size inline; transparency is a product feature, not fine print.
4. Every recommendation, score, and map color must have a traceable "why" explanation reachable in one click.
5. The interface must be calm (quiet) by default and only escalate visual prominence for high-intensity, high-relevance events (anti-fatigue visual rule).
6. The decision interface (map + panels) is desktop-first; alerts and brief-reading are mobile-first.
7. At world zoom (z0–z2) events must be clustered by region into aggregate bubbles; bubble size = event count, color = dominant category, ring = max intensity in cluster.
8. At continental zoom (z3–z4) clusters must break into country-level groups.
9. At regional zoom (z5–z6) sub-country clusters form; high-intensity events de-cluster into individual pulses.
10. At local zoom (z7+) every event renders as an individual pulse with full granularity.
11. Clicking a cluster must zoom in one level and re-center; clicking an individual pulse opens the popup.
12. A cluster must show a category-breakdown donut on hover.
13. A single intensity-5 event must punch through as an individual pulse even at low zoom — it must never hide inside a cluster.
14. Pulse color = event category (6 categories, 6 fixed colorblind-safe colors); pulse size = intensity (1–5); pulse animation rate = recency (fast/bright for new, slow glow over relevance window, then static dot).
15. When a scoring profile is active and "show portfolio companies" is on, affected companies render as secondary markers near the event colored by custom score (green→red), connected by a thin line.
16. The popup (3-second read) must show: category, intensity, headline, time, location, number of holdings exposed, ticker symbols with score delta, AI one-word recommendation, and confidence; "Expand" opens the side panel.
17. The side panel must include a "Why this read?" link that opens the full audit trail (historical analogs, prompt version, agent reasoning).
18. When the AI's read contradicts the naive interpretation, the side panel must lead with a "history says" callout showing the contrarian historical read and supporting statistics.
19. When social sources are enabled, the side panel must show the triggering social posts with timestamps.
20. Live mode delivers real-time pulses via WebSocket.
21. Historical mode provides a date-range slider; companies are colored by their score at the selected time (requires score history / time-machine isolation).
22. Playback mode animates forward through a chosen window with speed control (1×/4×/16×).
23. A calm/quiet market state must display a meaningful message (e.g., "Quiet session. 2 low-intensity events near your holdings"), not a broken-looking empty map.
24. An empty watchlist must show a guided prompt to add companies.
25. The Screener must be reachable from the map ("show in screener" button) and from the top bar; it is a sortable/filterable table of companies with custom scores, current price, and active-event flags.
26. When the Screener is entered from a map event it must pre-filter to that event's affected companies.
27. The Screener must support CSV export.
28. The Indicator Builder must provide a visual DSL editor with: parameter palette (left), formula canvas with live validation (center), live preview on 5 sample companies (right).
29. Every Indicator Builder save must create a new version; diff and rollback between versions must be supported.
30. Indicators must be groupable into profiles.
31. Company Detail must show: price chart, fundamentals, all custom scores with breakdown, active events touching the company, AI analysis history, recommendation track record.
32. On-Demand Analysis is triggered from the Company Detail screen.
33. Reports/Briefs reader must support per-report confidence display and user feedback (thumbs up/down/edit) that feeds the user-feedback memory layer and audit/override loop.
34. The Q&A/Chat interface must be scoped to the user's portfolio and event archive; responses must show sources and confidence per answer.
35. The Alerts Center must list all fired alerts, each linking back to the map event or report; alert-rule management (create/edit, thresholds, quiet hours, channels) lives here or in settings.
36. User Settings must expose: price-freshness mode (delayed/realtime/EOD), anti-fatigue controls (daily alert limit, quiet hours, per-ticker thresholds), narrative writing tone, notification channels, default scoring profile.
37. Portfolio/Watchlist onboarding must support: manual entry (ticker + shares + cost basis), CSV import, and broker connection (Interactive Brokers, Phase 3).
38. The admin panel is the operator's control surface, distinct from end-user settings; access is gated by role (admin/operator vs end-user).
39. The admin panel must list all data sources with status, health, last-fetch time, and cost tier.
40. An admin must be able to enable/disable any data source without a code deploy; disabling reroutes to the configured fallback.
41. Adding a new source requires only admin-side configuration (credentials + config); the adapter must exist in code but activation is database-driven.
42. Per-source admin configuration must include: API keys (vault reference), rate limits, poll frequency, TTL overrides, and priority (primary/fallback order).
43. Market-to-source binding (which provider serves which market for which interface) must be DB-backed and admin-editable, replacing hardcoded MARKET_REGISTRY.
44. Social-source stubs (StockTwits, Reddit, Telegram, Truth Social, Twitter/X) must be listed and toggleable; Twitter/X must be off by default.
45. The admin must have a per-source health and cost dashboard showing: calls today, % of rate-limit used, errors, and estimated cost.
46. The DSL scoring parameter catalog must be admin-managed: add parameters, enable/disable parameters, define derived/composite parameters, manage benchmark groups and peer sets.
47. The AI Audit Console must log every AI recommendation/classification with: inputs, retrieved analogs, prompt version, model, confidence, output, and Langfuse trace link; it must be searchable/filterable.
48. An admin must be able to replay the full reasoning chain for any AI decision (tool calls and intermediate outputs).
49. An admin override of an AI decision must: write to user-feedback memory, add to golden-dataset candidate pool, and surface a proposed prompt adjustment for review; on approval the prompt change flows through the git+Langfuse versioning pipeline.
50. The admin must have a calibration dashboard showing whether high-confidence calls are more accurate (Tier-3 ex-post calibration).
51. Prompt version history must be visible with quality metrics per version, and rollback control must be available.
52. The admin panel must show per-source ingestion jobs, schedules, last run, failures, and a manual trigger.
53. Mode B workflow history (status, cost, duration) must be visible and re-runnable from the admin panel.
54. The HIL (human-in-the-loop) review queue for pending reports must live in the admin panel.
55. The admin cost monitor must show aggregate spend vs. budget broken down by source, model, and workflow, with alerts at threshold.
56. The admin must be able to manage the tracked company universe (~100–200 companies) and promote on-demand companies to tracked.
57. The admin must have cache/data management controls: inspect, force-refresh, view storage growth, purge.
58. Feature flags (real-time mode, specific workflows, social sources) must be toggleable per environment from the admin panel.
59. Even in single-user MVP, login is required; the user table must have a role field (admin/operator vs end-user) from day 1.
60. The document is explicitly marked as a proposal that "should be rethought to fulfill all functional requirements from system_description.md."

## System Behaviours Required
- System opens to the world map as the home screen on every session start.
- WebSocket connection established immediately for live event pulses in Live mode.
- Map clusters events dynamically per zoom level using Supercluster with custom clusterProperties aggregating category counts and max intensity.
- Category-aware cluster renderer applies dominant-category color, intensity ring, and donut breakdown per cluster.
- Intensity-5 (maximum) events bypass clustering and render as individual pulses at all zoom levels.
- Clicking a cluster triggers zoom-in by one level and map re-centering.
- Pulse animation rate decays over the event's relevance window; pulse becomes a static dot at end of window.
- Score-coloring overlay renders secondary company markers linked to event by thin line when scoring profile is active.
- Side panel is collapsed by default; opened by "Expand" from popup.
- "Why this read?" opens a full audit trail view showing historical analogs, prompt version, and agent reasoning chain.
- Historical mode replays scores at the selected time window; Playback mode animates at selectable speed (1×/4×/16×).
- Empty/quiet states display contextual human-readable messages rather than blank or error states.
- Screener pre-filters to the triggering event's affected companies when launched from map event context.
- Indicator Builder provides live score preview on 5 sample companies as the formula is edited; every save creates a versioned snapshot.
- User feedback (thumbs up/down/edit) on reports is captured and routed to user-feedback memory layer and audit loop.
- Admin enable/disable of a source takes effect at runtime without code deployment; fallback routing is automatic.
- Admin source configuration writes credentials as vault references, never plaintext.
- AI override by admin triggers: feedback memory write, golden-dataset candidate creation, proposed prompt adjustment surfaced for review; on approval, prompt versioned through git+Langfuse pipeline.
- provider_registry and MARKET_REGISTRY are loaded from database at startup and refreshable at runtime.
- Admin cost monitor fires alerts when spend crosses configured threshold.
- Role-based access gates the admin panel from end-user routes.

## Data Entities
- source_config: source_id (PK), interface_type, display_name, enabled, credentials_ref, config (JSONB), cost_tier, priority, updated_at
- market_source_binding: market_id (FK→market), interface_type, source_id (FK→source_config), role (primary|fallback); PK (market_id, interface_type, source_id)
- Event/Pulse: category, intensity (1–5), headline, timestamp, location (geospatial), relevance_window, affected_companies
- Company: ticker, shares, cost_basis, custom_scores (per profile), active_events, AI_analysis_history, recommendation_track_record
- ScoringProfile: profile_id, indicator_definitions, version history
- Indicator/Parameter: name, category, data_source, fetch/compute spec, enabled flag; derived/composite indicator definitions
- BenchmarkGroup: sector definitions, custom peer sets
- AIDecision: inputs, retrieved_analogs, prompt_version, model, confidence, output, langfuse_trace_link, overrides
- PromptVersion: version_id, content, quality_metrics, active_from, rolled_back_at
- UserFeedbackMemory: decision_ref, feedback_type (thumbs_up/down/edit), correction, timestamp
- GoldenDatasetCandidate: decision_ref, override_ref, approval_status
- Alert: rule_id, fired_at, linked_event_or_report, channel, status
- AlertRule: threshold, quiet_hours, per_ticker_thresholds, channels
- Portfolio/Watchlist: ticker, shares, cost_basis, added_at, source (manual|csv|broker)
- Report/Brief: type (morning_brief|watchlist_scan|earnings_brief|event_deep_dive), content, confidence, feedback, hil_status
- User: user_id, role (admin|operator|end_user), settings, scoring_profile_default
- HILQueueItem: report_ref, status (pending|approved|rejected), reviewer, reviewed_at

## Integration Points
- MapLibre GL: map rendering engine for world map, zoom/clustering, pulse markers
- Supercluster: cluster aggregation library used by MapLibre; clusterProperties used for category counts and max intensity per cluster
- WebSocket: real-time event push channel for Live mode
- Interactive Brokers: broker connection for portfolio import (Phase 3)
- Langfuse: AI reasoning trace storage and prompt version quality metrics
- Git + Langfuse pipeline: prompt versioning and rollback on admin approval of override-driven prompt changes
- Secrets vault: storage for API credentials; source_config holds vault references only
- Social sources (stub/toggleable): StockTwits, Reddit, Telegram, Truth Social, Twitter/X
- Data providers referenced via source_config/market_source_binding: PriceProvider, NewsProvider, and other interface types (admin-configured, not hardcoded)
- Recharts or visx: candidate charting library for sparklines and price/score history (D3 reserved for custom map/pulse work)
- TanStack Query: candidate data-fetching/caching layer for real-time map + WebSocket subscriptions

## Non-Functional Signals
- "3-second read" popup design constraint → Latency / UX responsiveness NFR candidate
- "30-second read" side panel design constraint → UX readability / information density NFR candidate
- Real-time pulses via WebSocket → Low-latency event delivery NFR candidate
- Playback speed up to 16× → Historical data throughput / animation performance NFR candidate
- Admin enable/disable without code deploy → Operational configurability / zero-downtime reconfiguration NFR candidate
- Runtime-refreshable provider_registry and MARKET_REGISTRY → Hot-reload / availability NFR candidate
- Credentials stored in secrets vault, never plaintext → Security NFR candidate
- Role-based admin gate → Authorization / access control NFR candidate
- Cost monitor with threshold alerts and per-source/model/workflow breakdown → Cost observability NFR candidate
- Supercluster custom cluster renderer noted as "budget a few days" → Build complexity / performance NFR candidate
- Score history required for Historical mode time-machine isolation → Data retention / time-series storage NFR candidate
- Anti-fatigue controls (daily limit, quiet hours, per-ticker thresholds) → Alert rate-limiting / UX quality NFR candidate
- Mobile-first for alerts and brief-reading → Responsive design NFR candidate
- Colorblind-safe palette mandated → Accessibility NFR candidate

## Ambiguities Detected
- Document is explicitly self-flagged as a proposal that "should be rethought to fulfill all functional requirements from system_description.md" — scope finality is unresolved; unclear which sections are approved vs. pending revision.
- "Master Section 11" and "Master Section 08" are referenced for the side panel layout and DSL parameter catalog respectively, but those sections are not in this file and their source is unspecified — downstream digests must resolve this cross-reference.
- "system_description.md" is referenced but not linked or included; gap between this proposal and that document is undefined.
- Social Q&A / Chat scope: the interface is described as "scoped to the user's portfolio and event archive" but the boundary with the AI audit trail and the agentic doc's HIL queue is not precisely defined.
- Broker connection (Interactive Brokers) is deferred to Phase 3 with no specification of the integration protocol or OAuth/credential model.
- Twitter/X is "off by default" per admin stance, but the condition under which it may be enabled and by whom is not stated.
- Historical mode requires "score history / time-machine isolation" — the retention period, granularity, and storage strategy are not specified here.
- The admin panel is described as potentially the "same React app under an /admin route guard, or a separate lighter admin bundle" — the decision is deferred to implementation without a stated criterion for choosing.
- "Recommendation track record" (was the AI right before?) on Company Detail implies a ground-truth evaluation mechanism, but how correctness is determined is not specified.
- The document references "agentic doc Section 06" for the HIL queue but that document is not included in this file.
- "~100–200 tracked companies" is a soft figure; the hard upper limit and promotion criteria for on-demand-to-tracked are not defined.
- Calibration dashboard references "Tier-3 ex-post calibration" from "the agentic doc's eval framework" — the evaluation framework document is not referenced by path.

## Architecture Signals
- Map-first single-page application architecture with the world map as the root route/home screen.
- Progressive-disclosure UI pattern drives a layered component hierarchy: pulse → popup → side panel → full analysis page.
- WebSocket subscription manager required at the frontend data layer for real-time event delivery.
- TanStack Query proposed as data-fetching/caching layer alongside WebSocket; implies a hybrid push/pull frontend data architecture.
- MapLibre GL is the mandated map engine; Supercluster is the mandated clustering library with custom clusterProperties aggregation.
- D3 reserved for custom map/pulse work; Recharts or visx for standard charts — explicit technology segmentation within the frontend.
- React 18 + TypeScript is the mandated frontend stack.
- Admin panel co-located in the same React app under an /admin route guard (preferred MVP approach).
- provider_registry and MARKET_REGISTRY are architectural components that must migrate from code constants to database-backed services (source_config and market_source_binding tables) — this is an explicit architectural change driven by the admin panel requirement.
- Adapter interface pattern: code holds interface implementations; database holds which are active and how they're configured — explicit separation of configuration plane from implementation plane.
- Secrets vault integration required for credential storage; source_config references vault, not raw keys.
- Langfuse is a required platform integration for AI reasoning traces and prompt version metrics.
- Git + Langfuse pipeline constitutes the prompt versioning and governance architecture.
- Role-based access control must be designed into the user table from day 1 (role field) to avoid costly retrofit; same philosophy applied to tenant_id.
- Score history / time-series data storage is a required backend capability for Historical mode and time-machine isolation.
- HIL queue is a first-class system component living in the admin panel, fed by Mode B workflows.
- Feature flag system required at the environment level for toggling real-time mode, workflows, and social sources.
