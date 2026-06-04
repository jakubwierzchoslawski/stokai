This is a proposal, should be rethinked to fullfill all functional requirements from *system_description.md*



PART B — UI & ADMIN REQUIREMENTS
This is the missing layer. The architecture described what the system computes but not how the user sees and steers it. Since the map is the heart, it gets the deepest treatment, followed by the surrounding application screens and the admin panel.
B0. UI design principles
Six principles, mirroring the architecture's "map is the center":

Map-first, not menu-first. The application opens to the map. Everything else is reachable from it or layered over it. No landing dashboard that buries the map one click deep.
Progressive disclosure. Pulse → popup (3-second read) → side panel (30-second read) → full analysis (deep dive). The user controls depth. Never dump everything at once.
Confidence is always visible. Every AI output shows confidence and sample size inline. Transparency is a product feature, not fine print.
The user can always ask "why." Every recommendation, every score, every map color has a traceable explanation reachable in one click (this is the audit requirement surfaced in UI).
Calm by default, loud when it matters. Anti-fatigue applies visually too: the interface is quiet until a high-intensity, high-relevance event justifies visual prominence.
Mobile-aware, desktop-first. The decision interface (map + panels) is desktop-first. Alerts and brief-reading are mobile-first. Don't force the full map onto a phone.

B1. The Map — primary interface (deep specification)
The map is the home screen and the heart. This section specifies its full behavior, incorporating your new zoom/clustering requirement.
B1.1 Layout
┌──────────────────────────────────────────────────────────────┐
│  TOP BAR                                                       │
│  [StockIQ]   [Profile: Value Investor ▾]  [Mode: Live ▾]      │
│              [Search ⌕]            [Alerts ●3]  [Settings ⚙]  │
├───────────┬──────────────────────────────────────┬───────────┤
│           │                                      │           │
│  LEFT     │                                      │  RIGHT    │
│  RAIL     │           WORLD MAP                  │  SIDE     │
│           │        (events as pulses)            │  PANEL    │
│  Filters: │                                      │           │
│  Category │     • clustered at low zoom          │ (event    │
│  □ Conflict│    • individual at high zoom         │  detail / │
│  □ Politic │                                      │  analysis │
│  □ Economic│                                      │  appears  │
│  □ Energy  │                                      │  here)    │
│  □ Reg.    │                                      │           │
│  □ News    │      [zoom +/−]   [reset view]       │  collapsed│
│           │                                      │  by       │
│  Intensity│                                      │  default  │
│  ●●●●● 5   │                                      │           │
│  ──○── min │                                      │           │
│           │                                      │           │
│  Context: │                                      │           │
│  ○ Global │                                      │           │
│  ● Portfo.│   TIME BAR (when in Historical mode): │           │
│  ○ Sector │   ├────────●──────────────┤ ▶ playback│           │
└───────────┴──────────────────────────────────────┴───────────┘
B1.2 Zoom & clustering behavior (your new requirement)
This is the part you specifically flagged. Full spec:
Zoom levelEvent renderingLabelWorld (z0-2)Events clustered by region into aggregate bubbles. Bubble size = event count, color = dominant category, ring = max intensity in cluster."Middle East · 12 events"Continental (z3-4)Clusters break into country-level groups."Saudi Arabia · 4 events"Regional (z5-6)Sub-country clusters; high-intensity events de-cluster into individual pulses.Individual + small clustersLocal (z7+)Every event is an individual pulse. Full granularity.Individual pulses only
Interaction: Clicking a cluster zooms in one level and re-centers (standard marker-cluster behavior). Clicking an individual pulse opens the popup. A cluster shows a tiny category-breakdown donut on hover.
Technical note for the build: MapLibre GL supports clustering natively via GeoJSON cluster sources, but the category-aware clustering (dominant color, intensity ring, donut breakdown) needs a custom cluster renderer. Supercluster (the library MapLibre uses under the hood) supports cluster properties aggregation — use clusterProperties to aggregate category counts and max intensity per cluster. This is the right tool; budget a few days for the custom cluster styling.
De-clustering at high intensity: Per your requirement, a single intensity-5 event should not hide inside a cluster even at low zoom — it punches through as an individual pulse with a subtle "important" treatment, because that's exactly the event the user must not miss.
B1.3 The pulse

Color = category (6 categories, 6 fixed colors, colorblind-safe palette).
Size = intensity (1-5).
Animation = pulse rate tied to recency: a brand-new event pulses fast and bright, decaying to a slow steady glow over its relevance window, then to a static dot.
Score-coloring overlay (P1): when a scoring profile is active and "show portfolio companies" is on, affected companies render as small secondary markers near the event, colored by their custom score (green→red), connected to the event by a thin line.

B1.4 Popup (the 3-second read)
On click of an individual pulse:
┌────────────────────────────┐
│ ⚡ ENERGY · intensity 5     │
│ Strait of Hormuz incident  │
│ 2h ago · Persian Gulf      │
│ ──────────────────────────│
│ 3 of your holdings exposed │
│ XOM ↑2.1  CVX ↑1.8  ...    │
│ AI: CONTRARIAN (72%)       │
│ [ Expand → ]               │
└────────────────────────────┘
3-second read: what, where, how it touches me, the AI's one-word take, confidence. The "Expand" opens the side panel.
B1.5 Side panel (the 30-second read)
Already well-specified in Master Section 11. Confirmed layout stands. Three additions from your edits:

"Why this read?" link under the AI recommendation → opens the audit trail (B4.3): which historical analogs, which prompt version, the agent's reasoning. This is the audit requirement surfaced.
Historical-context emphasis: the panel must lead with "history says" when the AI's read contradicts the naive interpretation (your war≠drop requirement). A visual treatment like a callout: "⚠ Naive read: bearish. Historical read: bullish (8/10 similar events recovered within 1W)."
Social-signal block (when enabled): if social sources are on, show the triggering posts (e.g. a Truth Social / Reddit / StockTwits post) that contributed, with timestamp, so the user sees the immediacy edge.

B1.6 Time modes

Live (default): real-time pulses via WebSocket.
Historical: date-range slider. Map shows events as of that window; companies colored by their score at that time (requires score history / time-machine isolation).
Playback: animate forward through a chosen window, watching events fire and scores shift. Speed control (1×/4×/16×). This is the "Time Machine" of Phase 5.

B1.7 Empty/quiet states
A calm market morning should not look broken. When few events: "Quiet session. 2 low-intensity events near your holdings." Empty watchlist: a guided prompt to add companies. These states matter for a commercial feel.
B2. Surrounding application screens
The map is home, but the app needs these connected screens:
B2.1 Screener
Reachable from the map ("show in screener" buttons) and from the top bar. A sortable, filterable table of companies with their custom scores, current price, and active-event flags. Filter by score thresholds, sector, exposure to a selected event. Export (CSV). When entered from a map event, pre-filtered to that event's affected companies.
B2.2 Indicator Builder
Visual editor for custom scoring formulas (DSL). Left: parameter palette (the catalog from Master Section 08, now admin-extensible). Center: formula canvas with live validation. Right: live preview — pick 5 sample companies, see their scores update as you edit. Versioning: every save is a version; you can diff and roll back. Group indicators into profiles.
B2.3 Company Detail
Reached by clicking any company anywhere. Full view: price chart, fundamentals, all custom scores with breakdown, active events touching it, AI analysis history, recommendation track record (was the AI right before?). The "On-Demand Analysis" workflow is triggered from here.
B2.4 Reports / Briefs
A reader for Morning Briefs, Watchlist Scans, Earnings Briefs, Event Deep-Dives. List view (chronological) + reader view. Each report shows confidence, and — importantly — lets the user give feedback (👍/👎/edit), which feeds the user-feedback memory layer and the audit/override loop.
B2.5 Q&A / Chat
The interactive Historical Context Q&A. A chat interface scoped to the user's portfolio and the event archive. "Why did MSFT drop last week?" / "What usually happens to semis when Taiwan tensions spike?" Shows sources and confidence per answer.
B2.6 Alerts Center
In-app mirror of what goes out by email/push. List of fired alerts, each linking back to the map event or report. Alert-rule management (create/edit rules, set thresholds, quiet hours, channels) lives here or in settings.
B2.7 User Settings
Price-freshness mode (delayed/realtime/EOD), alert preferences (anti-fatigue controls: daily limit, quiet hours, per-ticker thresholds), writing tone for narratives, notification channels, scoring-profile default.
B3. Portfolio & Watchlist management (onboarding gap — see C)
How the user gets their holdings into the system. Manual entry (ticker + shares + cost basis), CSV import, or broker connection (Interactive Brokers, Phase 3). Watchlist: add by ticker search, or "add to watchlist" from anywhere. This was an implicit gap — there was no described path for the foundational act of telling the system what you own.
B4. ADMIN PANEL (entirely new — major addition)
You explicitly required this and it did not exist. The admin panel is the operator's control surface — distinct from end-user settings. Even as a single-user MVP, you are the admin and need these controls.
B4.1 Source Management (your top priority — "add/remove/disable, no hardcoding")
This directly addresses your Section 02 requirement and resolves the architectural tension in A4. The provider and source registries must move from code constants to database-backed, admin-editable configuration.
CapabilityDescriptionList all sourcesEvery data source (price, fundamentals, news, geo, macro, social, filings) with status (enabled/disabled), health, last-fetch time, cost tier.Enable/disable a sourceToggle without code deploy. Disabling reroutes to the configured fallback.Add a sourceRegister a new provider against an existing interface (PriceProvider, NewsProvider, etc.) by supplying credentials + config. The adapter must exist in code (it's an interface implementation), but activation and configuration is admin-side.Configure per sourceAPI keys (stored in secrets vault, referenced here), rate limits, poll frequency, TTL overrides, priority (primary/fallback order).Assign sources to marketsBind which provider serves which market for which interface — the DB-backed replacement for the hardcoded MARKET_REGISTRY.Social-source stubsStockTwits, Reddit, Telegram, Truth Social, Twitter/X — all listed, all toggleable, Twitter off by default (your stance). Stub adapters present, ready to activate if you add credentials.Health & cost dashboardPer-source: calls today, % of rate limit used, errors, estimated cost. The cost-control nerve center.
Architectural change this forces (document it): provider_registry and MARKET_REGISTRY become services backed by source_config and market_source_binding tables, loaded at startup and refreshable at runtime. Code still holds the adapter implementations; the database holds which are active and how they're configured. This preserves the abstraction principle while delivering runtime configurability.
sql CREATE TABLE source_config (
  source_id      TEXT PRIMARY KEY,        -- "finnhub", "fmp", "gdelt"
  interface_type TEXT NOT NULL,           -- "PriceProvider", "NewsProvider"...
  display_name   TEXT,
  enabled        BOOLEAN DEFAULT true,
  credentials_ref TEXT,                    -- pointer to secret in vault
  config         JSONB,                    -- poll freq, rate limit, TTL overrides
  cost_tier      TEXT,                     -- free | compute | paid
  priority       INT,                      -- ordering for primary/fallback
  updated_at     TIMESTAMPTZ
);

CREATE TABLE market_source_binding (
  market_id      TEXT REFERENCES market,
  interface_type TEXT,
  source_id      TEXT REFERENCES source_config,
  role           TEXT,                     -- "primary" | "fallback"
  PRIMARY KEY (market_id, interface_type, source_id)
);
B4.2 Scoring Parameter Management (your Section 08 edit)
You asked for admin configuration of scoring parameters. The DSL parameter catalog (PE, ROE, RSI, etc.) becomes admin-managed:

Add a new parameter: define its name, category, data source, and how it's fetched/computed.
Enable/disable parameters available to the Indicator Builder.
Define derived/composite parameters from existing ones.
Manage benchmark groups (sector definitions, custom peer sets).

This lets you extend scoring capability without code changes, as you required.
B4.3 AI Audit & Override Console (your audit requirement)
This surfaces the audit module (A1.3) and implements your requirement that "each AI reasoning and decision is stored… in case of user override or adjust, the AI system has to be adjusted as well, like prompts."
CapabilityDescriptionDecision logEvery AI recommendation/classification with: inputs, retrieved analogs, prompt version, model, confidence, output, and Langfuse trace link. Searchable/filterable.Reasoning replayOpen any decision and see the full reasoning chain (the agent's tool calls and intermediate outputs).OverrideThe admin can mark a decision wrong and provide the correct read.Override → improvement loopAn override is captured as a labeled example. It (a) writes to user-feedback memory, (b) is added to the golden-dataset candidate pool, and (c) surfaces a proposed prompt adjustment for review. On approval, the prompt change flows through the git+Langfuse versioning pipeline. This is the concrete mechanism behind your "AI system has to be adjusted as well" requirement — overrides don't just correct one output, they propose a systemic fix.Calibration dashboardThe Tier-3 ex-post calibration view: are high-confidence calls actually more accurate? (From the agentic doc's eval framework.)Prompt version historyWhich prompt version ran when, with quality metrics per version. Rollback control.
B4.4 System Operations
CapabilityDescriptionIngestion statusPer-source fetch jobs, schedules, last run, failures. Manual trigger.Workflow runsMode B workflow history, status, cost, duration. Re-run / debug.HIL queueThe human-in-the-loop review queue (from agentic doc Section 06) lives here — pending reports awaiting approval before send.Cost monitorAggregate spend vs. budget, per source / per model / per workflow. Alerts at threshold.Company universeManage the ~100-200 tracked set; promote on-demand companies to tracked.Cache/data managementInspect cache, force-refresh, view storage growth, purge if needed.Feature flagsToggle features (real-time mode, specific workflows, social sources) per environment.
B4.5 Admin panel — who sees it
In single-user MVP: you, behind login. In multi-tenant future: a role on the user (admin/operator vs end-user). The admin panel is gated by role. This is also where the authentication gap (C2) must be resolved — even single-user needs a login, and the admin/end-user distinction needs a role field on the user table from day 1 (same philosophy as tenant_id: cheap now, expensive to retrofit).
B5. Frontend technology note
The Master picks React 18 + TypeScript + MapLibre GL + D3 — all appropriate. Additions for the above:

Marker clustering: Supercluster (via MapLibre cluster sources) + custom cluster renderer for category-aware styling.
Charts: a lightweight charting lib for sparklines and price/score history (the master mentions D3; for speed, a higher-level lib like Recharts or visx for standard charts, D3 reserved for the custom map/pulse work).
Admin panel: can be the same React app under an /admin route guard, or a separate lighter admin bundle. For MVP, same app + route guard is simplest.
State/data: the real-time map + WebSocket pushes argue for a solid data-fetching/caching layer (TanStack Query) and a WebSocket subscription manager.
