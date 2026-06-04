---
source_file: docs/kb/system_description.md
checksum: 18189a5fc42d3b090a14b67fdd9eb23e
digested_at: 2026-06-02T00:00:00Z
domain: root
doc_type: architecture
arch_relevant: true
---

# Digest: system_description.md

## Business Rules

1. StokAI interprets what world events mean for portfolio companies, not merely reports what happened.
2. Target information edge: alerts 20–90 minutes ahead of average retail investor.
3. Every AI recommendation must carry confidence level, historical sample size, and cited sources.
4. Recommendations are decision frameworks, not transaction signals; no buy/sell execution implied.
5. When fewer than 5 historical analogies exist, a clear disclaimer must accompany the recommendation.
6. Starting market is US only (NYSE + NASDAQ); other markets added via configuration, not code changes.
7. Company analysis scope is ~100–200 tracked companies; additional companies fetchable on demand.
8. Price freshness default is 15-minute delay; real-time switch is a parameter change, not a code change.
9. All data sources are configurable through the admin panel; no hardcoding of provider selections.
10. Adding a new market must require only a MARKET_REGISTRY entry and (optionally) a new provider adapter; any other change signals a broken abstraction.
11. Twitter/X free API used for MVP; $100/month paid tier is optional and user-decision-dependent.
12. Every fetch is saved locally with timestamp and TTL; external APIs are the last resort (cache-or-fetch rule).
13. Historical data (past prices, embeddings) is fetched once and never re-fetched (immutable past).
14. Computed scores are invalidated event-driven, not on a fixed schedule.
15. Scoring profiles (Value Investor, Growth Hunter, Macro Aware) switch the entire market rating and map coloring.
16. Every user data table carries tenant_id from day one, enforcing row-level isolation.
17. AI audit trail and override feedback must be accessible for every map interaction.
18. Anti-fatigue controls (daily push limit, quiet hours, per-ticker threshold, deduplication) govern all alert dispatch.
19. Morning Brief is delivered at 06:00 daily via HTML email.
20. GDELT commercial license must be verified before launch; ACLED is designated backup.
21. Legal: system operates on derived data (scores, analyses), not raw prices, to manage data redistribution risk.
22. Cold-start requirement: GDELT historical archive (1979+) seeded with historical prices so analogy engine is useful at launch.
23. New-user first-run must offer preset scoring profiles and guided portfolio setup to prevent empty-map bounce.

## System Behaviours Required

- Detect market-relevant events and deliver alert to user within 90 seconds of event occurrence (Breaking Geo intensity 4–5).
- Deliver High-Signal Tweet alert within 30 seconds of TIER1 tweet hitting Filtered Stream.
- Score Change alert delivered within 5 minutes of a score-changing event.
- SEC Filing alert delivered within 20 minutes of filing.
- Complete Event Analysis Pipeline in ≤90 seconds: detection (0–15 s) → LLM classification (15–45 s) → exposure mapping (45–60 s) → historical matching (60–75 s) → recommendation (75–90 s) → dispatch (90+ s).
- Intelligence Map renders animated WebGL pulses; color encodes event category, size encodes intensity.
- Map supports checkbox category/intensity filters with immediate hide (no reload).
- Map supports context modes: Global, Portfolio, Sector.
- Map supports zoom-driven event clustering: low zoom = clustered events, high zoom = individual events.
- Map supports time modes: live, historical, playback (slider).
- Clicking a region or event on the map filters the Global Screener to affected companies sorted by custom score.
- Side panel shows: category, title, location/date/intensity, AI summary, T±7 day price sparklines, action signal, confidence, sample size, rationale, forecast, historical analogies, affected companies with custom scores.
- Screener supports AND/OR operator composition and CSV export.
- Indicator Builder accepts DSL formulas; Scoring Engine normalizes against benchmark and applies geo modifier.
- Cache-or-fetch sequence: Redis → local PostgreSQL → external API (only on cache miss).
- Real-time/delayed price switch: provider registry selects appropriate source via configuration parameter only.
- WebSocket pushes real-time events and score changes to the map and alert subscribers.
- Alert dispatcher sends email (HTML), push notification, and (for breaking geo) SMS.
- Celery workers execute scheduled ingestion, scoring, and alert evaluation tasks.
- All backend modules interact with external APIs exclusively through provider adapter interfaces; direct API calls from business layers are forbidden.

## Data Entities

- market: market_id, name, timezone, currency, sector_taxonomy, enabled
- company: company_id, market_id, ticker, name, sector_internal, sector_gics, market_cap, hq_country, geo_revenue (JSONB), is_tracked
- price_bar: (company_id, ts, interval) PK, OHLCV, source, fetched_at — TimescaleDB hypertable
- geo_event: event_id, occurred_at, detected_at, category[], intensity (1–5), title, summary, lat, lon, geo_regions[], affected_sectors[], sentiment, cameo_code, source_provider, tenant_id
- event_exposure: (event_id, company_id) PK, exposure_type, direction, magnitude (0–1), price_change_t1d
- event_embedding: event_id, embedding VECTOR(1536), hnsw index — pgvector
- indicator: tenant_id, formula_dsl, benchmark_mode, normalization, direction, geo_weight, version
- company_score: (company_id, indicator_id) PK, score (0–100), raw_value, percentile, geo_adjusted, inputs_hash
- ai_recommendation: event_id, company_id, action_signal (HOLD|WATCH|BUY_OPP|REDUCE_RISK|HEDGE|CONTRARIAN), direction, confidence (0–1), sample_size, rationale, forecast (JSONB), analogies (JSONB), scenario_tree (JSONB), model_version, actual_t1d, accuracy
- portfolio: tenant_id (+ standard portfolio fields)
- position: tenant_id, portfolio_id, company_id (+ standard position fields)
- alert_rule: tenant_id (+ rule configuration fields)
- MarketConfig dataclass: market_id, name, timezone, currency, calendar, ticker_format, sector_taxonomy, price_provider, fundamentals_provider, filings_source, enabled
- MARKET_REGISTRY: dict[str, MarketConfig] — central market configuration map

## Integration Points

- Finnhub.io: primary US price provider (15-min REST delayed → RT WebSocket stream)
- FMP (Financial Modeling Prep): primary fundamentals provider ($14/month), secondary price fallback
- Twelve Data: secondary price provider fallback
- GDELT: primary geopolitical news/events provider (free, 15-min poll cycle)
- Finnhub News: market news (free), fallback geopolitical news
- FRED (Federal Reserve Economic Data): primary macro data provider (free)
- World Bank / IMF: macro data fallback
- SEC EDGAR: primary filings provider (free), source-of-truth for fundamentals cross-validation
- Twitter/X Filtered Stream: primary social signal provider (<5 s latency for TIER1 tweets)
- StockTwits: social fallback stub (ready to activate)
- Reddit: social fallback stub (ready to activate)
- Telegram: social fallback stub (ready to activate)
- Truth Social: social fallback stub (ready to activate)
- Benzinga: market news phase-2 provider
- Polygon.io: US price RT/delayed streaming alternative
- Azure OpenAI GPT-4o-mini: LLM for high-volume event classification and embeddings (VNet-isolated)
- Claude API (Opus): LLM for complex reasoning — recommendations and Historical Q&A
- SendGrid / Azure Communication Services: outbound email (prefer free tier)
- FCM / APNs: push notifications (phase 2)
- Interactive Brokers: trade execution integration (phase 3)
- Webhooks: outbound event notification (phase 3)
- Azure Container Apps: backend API and Celery worker hosting
- Azure DB for PostgreSQL Flexible: managed database option (or self-hosted container)
- Azure Cache for Redis: managed Redis option (or self-hosted container)
- Azure Blob Storage / MinIO: report and blob storage
- Azure Key Vault / HashiCorp Vault / .env: secrets management
- Azure Monitor + Application Insights: observability (optional for MVP cost)
- ACLED: designated backup for GDELT if GDELT commercial license is denied

## Non-Functional Signals

- Event-to-alert latency ≤90 s (breaking geo intensity 4–5) → Latency / Performance NFR candidate
- Tweet-to-alert latency ≤30 s (TIER1 tweets) → Latency / Performance NFR candidate
- Score-change alert ≤5 min → Latency NFR candidate
- SEC filing alert ≤20 min → Latency NFR candidate
- Price freshness 15 min delayed / 5 s real-time stream → Data freshness NFR candidate
- MVP infrastructure cost target ~$30–50 AI + ~$30–40 Azure = total ~$268/month single-user → Cost / Operability NFR candidate
- Local-first cache ensures data cost grows sublinearly with user count → Scalability / Cost NFR candidate
- Viewing a chart 100 times incurs 0 additional API calls → Performance / Cost NFR candidate
- Row-level tenant isolation via tenant_id on every user table → Security / Multitenancy NFR candidate
- No hard Azure lock-in: self-hosting via `docker compose up` + environment variable change → Portability NFR candidate
- Docker + Compose / K8s containerization across all components → Portability / Operability NFR candidate
- 12-factor app compliance → Operability NFR candidate
- pgvector HNSW index for semantic search → Performance NFR candidate
- TimescaleDB hypertables for OHLCV → Performance / Scalability NFR candidate
- AI confidence + sample_size always visible; ex-post accuracy tracked → Auditability / Compliance NFR candidate
- Legal liability for recommendations requires clear disclaimers → Compliance / Legal NFR candidate
- Rate limiting on free APIs mitigated by aggressive cache + nightly batch + Redis TTL per endpoint → Reliability NFR candidate

## Ambiguities Detected

- Section 16 states total MVP cost "~$268/month" but the itemised breakdown (data free, AI $30–50, Azure $30–40) sums to ~$60–90; the $268 figure is unexplained — likely a data entry error or includes unlisted items.
- Twitter/X integration: "free API for MVP if exists" — it is unclear whether a suitable free-tier Filtered Stream endpoint actually exists at time of implementation; needs verification.
- GDELT commercial license: document says "verify before launch" but does not state current license status or whether MVP use is permitted — ambiguity blocks GDELT production use.
- Action signal values include CONTRARIAN but rationale for when CONTRARIAN is chosen vs HEDGE is not defined in any section.
- "~100–200 tracked companies" scope: no rule defines which companies are tracked vs on-demand; criteria for promotion to tracked status are absent.
- Section 10 mentions "OAuth2 production" auth but no spec is given; MVP username/password boundaries vs OAuth2 scope are undefined.
- SendGrid / Azure Communication Services preference: document says "prefer free option" but no threshold or fallback rule is specified.
- Phase 2/3 features (push FCM/APNs, Interactive Brokers, Webhooks) have no timeline or acceptance criteria defined beyond phase label.
- "Score replay" and "Analog Finder" (Phase 5) are named but not specified — their data model and behaviour requirements are absent.
- Admin panel is referenced repeatedly as the configuration UI but its own requirements (access control, audit, UI tech) are not specified anywhere.
- Benzinga "phase 2" integration: no trigger condition or cost estimate provided.
- Insider data (SEC Form 4 / FMP fallback) appears in Section 06 provider list but has no corresponding data entity in Section 07 — possible missing entity.

## Architecture Signals

- Modular monolith chosen over microservices; modules separated by interfaces for future extraction as scale demands.
- Six-layer architecture: External World → Ingestion & Cache → Storage → Processing → Serving → Presentation; presentation layer never calls provider APIs directly.
- Provider abstraction via Protocol interfaces (PriceProvider, FundamentalsProvider, NewsProvider) enforced as a hard boundary; data_providers module is the only module allowed to touch external APIs.
- Repository pattern used for all persistence; storage module abstracts database technology from business logic.
- Cache-or-fetch pattern (Redis → PostgreSQL → API) is the universal data access strategy.
- TTL policy is per-data-type, with historical data and embeddings having infinite TTL (immutable past).
- MARKET_REGISTRY is the single extension point for new markets; zero changes required outside of it and a new adapter.
- Hybrid cloud topology: data layer local (PostgreSQL + TimescaleDB + pgvector + Redis), compute layer cloud (Azure OpenAI VNet, Container Apps, Claude API).
- LLM division of responsibility: GPT-4o-mini for high-volume cheap classification; Claude Opus for low-volume complex reasoning; model abstraction layer makes both replaceable.
- pgvector (HNSW) embedded in the same PostgreSQL instance for event embeddings and semantic historical search — no separate vector database.
- TimescaleDB as a PostgreSQL extension for OHLCV hypertables — no separate time-series database.
- Redis serves dual role: hot cache (cache-or-fetch layer) and Celery task queue broker.
- MapLibre GL JS (open-source WebGL) chosen over proprietary mapping SDK; custom WebGL + D3 for animated pulse layer.
- Multi-tenant schema from day one (tenant_id on all user tables) with single-tenant operations; multi-tenant activation deferred to Phase 5.
- Self-host parity: replacing managed Azure services with containerised equivalents requires only environment variable changes and `docker compose up`.
- Scoring DSL is a custom language with arithmetic, logical, ranking, and time-series operators; formulas are parsed and evaluated at runtime, not compiled.
- Geo-modifier on scores means a geopolitical event can adjust company scores in real time without a full recalculation cycle.
- Event analysis pipeline is a strict sequential stage gate with defined latency budgets per stage (15 s increments to 90 s total).
- GDELT historical archive seed (1979+) is a cold-start architectural requirement for the analogy engine to be functional at launch.
- Abstraction correctness test is an explicitly stated architectural invariant: any market addition requiring changes beyond MARKET_REGISTRY signals a broken abstraction.
