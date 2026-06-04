# StokAI — Master Architecture Document

> **Master Architecture Document · Commercial Project**
> Version 1.0 — May 2026 · Scope: Architecture · Data · Integrations · Requirements · Starting market: US (NYSE + NASDAQ) · Status: **Ready for implementation**

---

## Key Decisions

| Decision | Value |
|---|---|
| Tenancy model | Single-user / multi-tenant ready |
| Hosting | Azure + self-host option |
| Company scope | ~100–200 tracked + on-demand |
| Price freshness | 15 min default / RT-switchable |
| Storage | Local-first / cache-or-fetch |

---

## Table of Contents

**Foundations**
- [Section 00 — Executive Summary](#section-00--executive-summary)
- [Section 01 — Architectural Principles](#section-01--architectural-principles)
- [Section 02 — System Overview](#section-02--system-overview)

**Architecture**
- [Section 03 — Layered Architecture](#section-03--layered-architecture)
- [Section 04 — Market Abstraction](#section-04--market-abstraction)
- [Section 05 — Data Layer & Cache](#section-05--data-layer--cache)
- [Section 06 — Provider Abstraction](#section-06--provider-abstraction)

**Data**
- [Section 07 — Data Model](#section-07--data-model)
- [Section 08 — Scoring Model](#section-08--scoring-model)
- [Section 09 — Map ↔ Scoring Correlation](#section-09--map--scoring-correlation)

**Features**
- [Section 10 — Functional Requirements](#section-10--functional-requirements)
- [Section 11 — Map as the Center](#section-11--map-as-the-center)
- [Section 12 — AI Intelligence Engine](#section-12--ai-intelligence-engine)
- [Section 13 — Alert System](#section-13--alert-system)

**Integrations & Deployment**
- [Section 14 — External Integrations](#section-14--external-integrations)
- [Section 15 — Azure Deployment](#section-15--azure-deployment)
- [Section 16 — Cost Model](#section-16--cost-model)
- [Section 17 — Roadmap](#section-17--roadmap)
- [Section 18 — Risks](#section-18--risks)

---

## Section 00 — Executive Summary

*What StokAI is and why it makes commercial sense*

StokAI is a platform that turns the chaos of world events into a concrete investment edge. Unlike financial terminals that show "what happened", StokAI interprets "what this means for your companies" — with a world map as the central decision interface.

### The Problem We Solve

A retail investor learns about market-relevant events 30–120 minutes after the fact — from Twitter, news portals, newsletters. By then, the price has already moved. At the same time, no available tool automatically connects: a geopolitical event → specific portfolio companies → historical context → action recommendation. Today, an analyst assembles this synthesis manually in 20–40 minutes. StokAI does it in 90 seconds.

### Three Pillars of Value

**Map as the Center**
The world seen through the lens of your portfolio. Events pulse on the map, each connected to affected companies and their custom scores. This is not a visualization — it is a decision interface.

**Information Edge**
Alerts arriving before the news hits the mainstream. Realistic goal: 20–90 minutes ahead of the average retail investor. We do not compete with HFT — we compete with latency.

**AI Synthesis**
Every event automatically analyzed: affected companies, direction, historical analogies, decision framework. With full transparency of sources and confidence levels.

### Fundamental Decisions in This Document

| Decision | Choice | Rationale |
|---|---|---|
| Starting market | US (NYSE + NASDAQ) | Best data availability and quality, cheapest APIs, deepest news coverage. Architecture ready to add further markets without rebuilding. |
| Tenancy model | Single-user, MT-ready | Zero operational multi-tenancy cost now, but schema and data isolation ready from day 1. Adding tenants = configuration, not refactor. |
| Hosting | Azure + self-host | Everything containerized. Azure for convenience and AI compute, but no hard lock-in — can be run on-premise. |
| Analysis scope | ~100–200 companies | Portfolio + watchlist with full AI analysis. Rest of US market available on-demand. Controls data and compute costs. |
| Price freshness | 15 min → RT switch | Default delayed (cheaper), but provider abstraction allows switching to real-time at runtime without changes to business logic. |
| Data storage | Local-first cache | Every fetch saved locally. API queried only when data is missing or stale. Drastic reduction of repeated fetch costs. |

> **Financial conclusion:** An MVP with a real information edge costs **~$30/month** in data. The system is designed so that each growth phase is self-financing through subscriptions when it moves from single-user to a commercial product.

---

## Section 01 — Architectural Principles

*Immutable rules on which the entire system stands*

These principles are binding for every implementation decision. Breaking any one of them means technical debt that will block scaling.

### 1. Everything Behind an Interface (Abstraction Everywhere)

No business layer touches directly: a data provider, a specific market, or a specific database. Everything behind an interface. Changing the price provider from Finnhub API to anything else = a new interface implementation, zero changes in scoring or map logic.

`Provider abstraction` · `Market abstraction` · `Repository pattern`

### 2. Local-First Data

Every fetch from an external API is saved locally with a timestamp and TTL. Before every API call the system checks: do I have this data locally and is it fresh enough? An external call is the last resort, not the default behavior. This directly protects the budget.

`Cache-or-fetch` · `TTL per data type` · `Cost control`

### 3. Multi-Tenant Schema, Single-Tenant Operations

Every user data table has a `tenant_id` from day one. Now there is one tenant, but adding more requires no schema migration and no rewriting of queries. Data isolation built into the foundation.

`tenant_id everywhere` · `Row-level isolation`

### 4. Containerized & Portable

The entire system runs in Docker containers, orchestrated by Azure Container Apps or Kubernetes. No dependency on Azure-only services where a portable alternative exists. Self-hosting is a change of deployment configuration, not a rewrite.

`Docker` · `No hard cloud lock-in` · `12-factor app`

### 5. Map is the Center

The map is not one of many views — it is the main interface. Custom scoring, screener, alerts, and AI analysis are correlated with the map and accessible from its context. The data architecture reflects this centrality: events, companies, and scores are connected by relationships that the map explores.

`Event ↔ Company ↔ Score` · `Spatial-first UX`

### 6. Transparent AI

Every AI recommendation carries a confidence level, historical sample size, and sources. The system never pretends to certainty it does not have. Recommendations are decision frameworks, not transaction signals — this is the foundation of legal responsibility for a commercial product.

`Confidence scores` · `Sample size visible` · `Audit trail`

---

## Section 02 — System Overview

*How the elements connect into a whole — from data to decision*

The value flow in StokAI has one direction: raw data from the world → structure → correlation with companies → AI synthesis → investor decision on the map. In general all sources per category (external world / social etc has to be configurable through admin panel. full implementation abstraction, no hardcoding. I need to have full possibility of adding removig/disablinch sources)

```
① External World — signal sources
   ├── Market prices (Finnhub API)
   ├── Fundamentals (FMP)
   ├── Geopolitics (GDELT)
   ├── Macro (FRED)
   ├── Social (Twitter/X)
   └── Filings (SEC EDGAR)
   Each source behind an interface — replaceable without affecting the rest

                        ↓

② Ingestion & Cache — local-first
   ├── Provider Adapters
   ├── Cache-or-Fetch Logic
   ├── Ingestion Scheduler
   ├── Data Validator
   └── Rate Limiter
   Checks local storage before every API call — cost control

                        ↓

③ Storage — local, persistent
   ├── PostgreSQL + TimescaleDB
   ├── pgvector (embeddings)
   ├── Redis (hot cache)
   └── Blob Storage (reports)
   Time-series for prices, relational for entities, vector for semantic news search

                        ↓

④ Processing — AI & Analytics
   ├── Event Classifier (LLM)
   ├── Exposure Mapper
   ├── Scoring Engine
   ├── Historical Matcher
   └── Recommendation Engine
   The heart of the system — turns data into knowledge. AI compute in cloud (Azure OpenAI)

                        ↓

⑤ Serving — API
   ├── REST / GraphQL API
   ├── WebSocket (real-time push)
   └── Alert Dispatcher

                        ↓

⑥ Presentation — map at the center
   ├── Intelligence Map
   ├── Screener
   ├── Indicator Builder
   ├── Side Panel (analysis)
   └── Email Alerts
```

> **Key architectural observation:** Three layers (①②③) concern **data** and must be cheap and reliable. Layer ④ is **value** — this is where the competitive edge is created. Layers ⑤⑥ are **experience** — with the map as the central point. The boundaries between them are strict: the presentation layer never calls provider APIs directly.

---

## Section 03 — Layered Architecture

*Detailed component structure and responsibilities*

### Technology Stack

| Layer | Technology | Rationale |
|---|---|---|
| Backend core | Python 3.12 + FastAPI | Best ecosystem for financial data and AI (pandas, numpy). FastAPI — performant async, automatic OpenAPI docs, Pydantic validation. |
| Relational DB | PostgreSQL 16 | Proven, free, rich in extensions. Azure Database for PostgreSQL Flexible Server or self-hosted. |
| Time-series | TimescaleDB | PostgreSQL extension — OHLCV prices as hypertables. Compression, fast range queries, no separate database. |
| Vectors | pgvector | News embeddings for semantic search in the same database. No separate Pinecone/Weaviate at start. |
| Hot cache | Redis 7 | Computed scores, session data, rate-limit counters. Azure Cache for Redis or self-hosted. |
| Task queue | Celery + Redis | Scheduled ingestion, batch scoring, alert dispatch. Independent workers, scalable. |
| AI / LLM | Azure OpenAI + Claude API | Azure OpenAI for classification (low cost, in VNet). Claude API for complex analysis and Q&A. Model abstraction — replaceable. |
| Frontend | React 18 + TypeScript | Map requires rich interactivity. TypeScript for type safety in a commercial project. |
| Map | MapLibre GL + D3 | MapLibre — open-source (no Mapbox costs), WebGL rendering thousands of points. D3 for custom visualizations and pulse animations. |
| Containerization | Docker + Compose / K8s | Identical dev/prod environment. Azure Container Apps to start, K8s at scale. |

> **Decision: modular monolith, not microservices.** At the single-user and early product stage, a **modular monolith** (single deployment, clearly separated internal modules) is correct. Microservices would add operational complexity without benefit at this scale. However, modules are separated by interfaces so that extraction into separate services (e.g. AI engine, alert dispatcher) is possible later without rewriting business logic.

### Backend Modules and Responsibilities

| Module | Responsibility | Depends on |
|---|---|---|
| `data_providers` | Adapters to external APIs. Implementations of PriceProvider, FundamentalsProvider, NewsProvider interfaces. The only place touching external APIs. | — |
| `ingestion` | Cache-or-fetch logic, fetch scheduler, validation, rate limiting. Decides when to fetch from API vs. locally. | `data_providers`, `storage` |
| `storage` | Repositories (repository pattern) over the database. Persistence abstraction — the rest of the system does not know SQL. | — |
| `markets` | Market abstraction. Per-market configuration: session calendar, timezone, ticker mapping, currency. | `storage` |
| `scoring` | Custom indicator engine. DSL parser, normalization, benchmark, composite score calculation. | `storage` |
| `events` | Geopolitical event classification, exposure mapping to companies, taxonomy management. | `ai`, `storage` |
| `ai` | LLM abstraction. Classification, recommendation generation, Q&A, embeddings. Replaceable model provider. | `storage` |
| `historical` | Pattern matching, semantic search for analogies, time-machine isolation (no future data leakage). | `ai`, `storage` |
| `alerts` | Alert rules, condition evaluation, dispatch (email/push), anti-fatigue logic. | `events`, `scoring`, `storage` |
| `api` | REST/GraphQL endpoints, WebSocket, authorization, serialization. Entry layer. | all |

---

## Section 04 — Market Abstraction

*How to add a new market without rebuilding the system*

This is a critical requirement: start on US, but adding another market must be configuration, not a project. We achieve this by fully separating market-specific logic from business logic.

### What Differs Between Markets

| Aspect | Example difference | Where handled |
|---|---|---|
| Session calendar | US: 9:30–16:00 ET. Other markets: different hours, different holidays. | `MarketConfig.calendar` |
| Timezone | US: America/New_York. Normalized to UTC in storage. | `MarketConfig.timezone` |
| Currency | US: USD. Others: EUR, GBP, JPY. Conversion for comparisons. | `MarketConfig.currency` |
| Ticker format | US: AAPL. Other exchanges: suffixes (.L, .DE), other conventions. | `MarketConfig.ticker_format` |
| Data provider | US: Finnhub API. Another market: possibly a different provider with better coverage.  One-time historical backfill (e.g. 10-15 years of daily bars for ~200 companies) may need a one-off paid month of FMP or a bulk source, after which it's stored forever locally| `MarketConfig.providers` |
| Sector classification | US: GICS. Mapping to common internal taxonomy. | `MarketConfig.sector_map` |
| Filings source | US: SEC EDGAR. Others: KNF ESPI, ESMA, etc. | `MarketConfig.filings_source` |

### Market Configuration Interface

```python
# markets/config.py — market abstraction
from dataclasses import dataclass
from typing import Protocol

@dataclass
class MarketConfig:
    market_id: str              # "US", "LSE", "XETRA" — adding = new entry
    name: str                   # "United States (NYSE + NASDAQ)"
    timezone: str               # "America/New_York"
    currency: str               # "USD"
    calendar: MarketCalendar    # session hours + holidays
    ticker_format: TickerFormat # how to normalize symbols
    sector_taxonomy: str        # "GICS" + mapping to internal
    price_provider: str         # "Finnhub API" — key in provider registry
    fundamentals_provider: str  # "fmp"
    filings_source: str         # "sec_edgar"
    enabled: bool = True

# Adding a new market = registering a configuration.
# Zero changes in scoring, events, ai, alerts, or the map.
MARKET_REGISTRY: dict[str, MarketConfig] = {
    "US": MarketConfig(
        market_id="US",
        name="United States (NYSE + NASDAQ)",
        timezone="America/New_York",
        currency="USD",
        calendar=NYSE_CALENDAR,
        ticker_format=US_TICKER_FORMAT,
        sector_taxonomy="GICS",
        price_provider="Finnhub",
        fundamentals_provider="fmp",
        filings_source="sec_edgar",
    ),
    # Phase 4: uncomment below = new market ready
    # "LSE": MarketConfig(market_id="LSE", ... ),
}
```

> **Abstraction correctness test:** If adding a market requires changing anything beyond `MARKET_REGISTRY` and possibly a new provider adapter implementation — the abstraction is broken. All scoring, map, AI, and alert logic operates on normalized entities independent of the market.

---

## Section 05 — Data Layer & Cache

*Local-first: how the system minimizes fetch costs*

### The Cache-or-Fetch Principle

Before every data request the system asks three questions in order: (1) Do I have this in the hot cache (Redis)? (2) If not — do I have it in the local database and is it fresh enough? (3) Only if not — fetch from the API, save locally, return. External APIs are the last resort.

```python
# ingestion/cache_or_fetch.py — the heart of cost control
async def get_price_data(
    ticker: str,
    market: str,
    date_range: DateRange,
    freshness: Freshness = Freshness.DELAYED_15M,
) -> PriceSeries:
    # 1. Hot cache — Redis, sub-millisecond
    if cached := await redis.get_prices(ticker, date_range):
        if cached.is_fresh_enough(freshness):
            return cached  # 0 API cost

    # 2. Local database — TimescaleDB
    local = await price_repo.get_series(ticker, market, date_range)
    if local and local.covers(date_range) and local.is_fresh_enough(freshness):
        await redis.cache_prices(ticker, local)  # promote to hot cache
        return local  # 0 API cost

    # 3. Last resort — fetch only the missing fragment
    missing = date_range.subtract(local.coverage if local else None)
    provider = provider_registry.get_price_provider(market)
    fresh = await provider.fetch_prices(ticker, missing)  # API COST

    await price_repo.save(fresh)      # save locally — never fetch this again
    await redis.cache_prices(ticker, fresh)
    return merge(local, fresh)
```

### TTL — How Long Data Is "Fresh"

Different data types go stale at different rates. TTL (time-to-live), configured per data type, determines when local data is considered outdated.

| Data type | TTL — delayed mode | TTL — real-time mode | Rationale |
|---|---|---|---|
| Intraday prices (portfolio) | 15 min | 5 sec (stream) | Switchable — provider abstraction changes the source without changing the logic |
| EOD prices (rest of market) | until end of day | until end of day | Closing price does not change — fetch once |
| Historical data (>1 day) | never | never | The past is immutable — fetch once, keep forever |
| Fundamentals (balance sheets, P&L) | 24 h | 24 h | Updated quarterly — check once a day for a new report |
| News / events | 15 min | 15 min | GDELT updates every 15 min — aligned with source cycle |
| Macro data (CPI, GDP) | until next release | until next release | Published on a calendar — TTL to next publication date |
| News embeddings | never | never | Text does not change — embedding computed once is eternal |
| Computed scores | event-driven invalidation | event-driven invalidation | Recomputed when input data changes, not by time |

> **Cost impact — concretely:** Historical data and embeddings fetched **once in the system's lifetime**. With ~150 companies, fetching full history is a one-time cost. EOD prices — one fetch per day per company. As a result, the monthly API bill is flat and predictable, regardless of how many times you look at the same data. **Viewing a chart 100 times = 0 additional API calls.**

### Real-time / Delayed Switching Strategy

Switching freshness is a parameter change, not a code change. The system has a global mode (set by the user) and the ability to override per request.

```python
# Global switch — in user settings
user_settings.price_mode = Freshness.REALTIME  # or DELAYED_15M, EOD

# Provider registry automatically selects the appropriate source:
# DELAYED_15M -> Finnhub API REST (cheaper plan)
# REALTIME    -> Finnhub API WebSocket stream (more expensive plan)
# Business logic (scoring, map) does NOT know which option is active
```

---

## Section 06 — Provider Abstraction

*Why swapping Polygon API for anything else is one file*

The biggest business risk in the system: a provider raises prices or disappears. Twitter/X changed its API pricing three times in two years. Provider abstraction is insurance against this risk.

### Provider Interfaces

Each data type has an interface (protocol) that every provider must implement. The rest of the system knows only the interface, never the concrete implementation.

```python
# data_providers/interfaces.py
from typing import Protocol

class PriceProvider(Protocol):
    async def fetch_prices(self, ticker: str, rng: DateRange) -> PriceSeries: ...
    async def stream_realtime(self, tickers: list[str]) -> AsyncIterator: ...
    def supported_markets(self) -> list[str]: ...

class FundamentalsProvider(Protocol):
    async def fetch_statements(self, ticker: str) -> Financials: ...
    async def fetch_ratios(self, ticker: str) -> Ratios: ...

class NewsProvider(Protocol):
    async def fetch_events(self, since: datetime) -> list[RawEvent]: ...

# --- Concrete implementations ---
class FinnhubProvider:  # implements PriceProvider
    async def fetch_prices(self, ticker, rng):
        # maps Finnhub API -> internal PriceSeries
        ...

class FMPProvider:  # implements FundamentalsProvider + PriceProvider (fallback)
    ...

# --- Registry: the only place binding market to provider ---
provider_registry.register("finnhub", FinnhubProvider())
provider_registry.register("fmp", FMPProvider())
# Swapping price provider = one line in MarketConfig
```

### US Market Providers — Assignment

| Interface | Primary | Fallback | Mode |
|---|---|---|---|
| `PriceProvider` | Finnhub.io | FMP / Twelve Data | 15 min REST → RT WebSocket (switchable) |
| `FundamentalsProvider` | FMP | SEC EDGAR (parsed) | 24 h TTL |
| `NewsProvider` (geo) | GDELT | Finnhub News | 15 min poll |
| `NewsProvider` (market) | Finnhub | Benzinga (phase 2) | Real-time poll |
| `MacroProvider` | FRED | World Bank / IMF | Calendar-based |
| `SocialProvider` | Twitter/X Filtered Stream | StockTwits / Reddit | Real-time stream |
| `FilingsProvider` | SEC EDGAR | — | Real-time feed |
| `InsiderProvider` | SEC Form 4 (EDGAR) | FMP | Real-time feed |

> **Insurance against Twitter/X risk:** If X Inc. raises the price of Filtered Stream from $100 to $5,000 — swapping the `SocialProvider` for a combination of StockTwits + Reddit + Telegram monitoring is a replacement of an implementation behind an interface. Alert logic, classification, and the map remain untouched. Without abstraction this would be a complete rebuild of the entire social signal pipeline. Create stub abstract for StockTwisk and reddit and telegram and truth social as well. I'm not realy kean to pay for twitter but it will be useful to have interface in case i change my mind

---

## Section 07 — Data Model

*Entities, relationships, and how everything connects around the map*

The data model reflects the central principle: events, companies, and scores are connected by relationships that the map explores. Every user entity has a `tenant_id` for future multi-tenancy.

### Entity Relationship Overview

```
  MARKET 1───* COMPANY 1───* PRICE_BAR  (TimescaleDB hypertable)
                │           1───* FUNDAMENTAL
                │           1───* COMPANY_SCORE *───1 INDICATOR
                │           *───* GEO_EVENT  (via EVENT_EXPOSURE)
                │
  GEO_EVENT 1──* EVENT_EXPOSURE *──1 COMPANY   ← MAP connects these three
       │     1──* AI_RECOMMENDATION *──1 COMPANY
       │     1──1 EVENT_EMBEDDING  (pgvector)
       │     *──* GEO_EVENT (historical analogies, via similarity)
       │
  USER 1──* PORTFOLIO 1──* POSITION *──1 COMPANY
       1──* WATCHLIST *──* COMPANY
       1──* INDICATOR (custom scoring definitions)
       1──* ALERT_RULE
       1──1 USER_SETTINGS (price_mode, alert prefs)
```

### Core Entities — Market and Companies

```sql
-- MARKET: market registry (abstraction)
CREATE TABLE market (
  market_id      TEXT PRIMARY KEY,   -- "US", "LSE" (phase 4)
  name           TEXT NOT NULL,
  timezone       TEXT NOT NULL,
  currency       TEXT NOT NULL,
  sector_taxonomy TEXT,              -- "GICS"
  enabled        BOOLEAN DEFAULT true
);

-- COMPANY: normalized, market-independent
CREATE TABLE company (
  company_id     UUID PRIMARY KEY,
  market_id      TEXT REFERENCES market,
  ticker         TEXT NOT NULL,      -- normalized symbol
  name           TEXT NOT NULL,
  sector_internal TEXT,              -- common internal taxonomy
  sector_gics    TEXT,               -- original from market
  industry       TEXT,
  market_cap     NUMERIC,
  hq_country     TEXT,               -- for map: HQ location
  geo_revenue    JSONB,              -- geographic revenue exposure
  is_tracked     BOOLEAN DEFAULT false, -- portfolio/watchlist vs on-demand
  UNIQUE(market_id, ticker)
);
CREATE INDEX ON company(sector_internal) WHERE is_tracked;

-- PRICE_BAR: TimescaleDB hypertable, partitioned by time
CREATE TABLE price_bar (
  company_id     UUID REFERENCES company,
  ts             TIMESTAMPTZ NOT NULL, -- always UTC
  interval       TEXT NOT NULL,     -- "1d", "15m", "1m"
  open           NUMERIC, high NUMERIC, low NUMERIC, close NUMERIC,
  volume         BIGINT,
  source         TEXT,              -- "Finnhub" — origin audit
  fetched_at     TIMESTAMPTZ,       -- when fetched (for TTL)
  PRIMARY KEY (company_id, ts, interval)
);
SELECT create_hypertable('price_bar', 'ts');  -- TimescaleDB
```

### Geopolitical Entities — the Heart of the Map

```sql
-- GEO_EVENT: geopolitical event (pulses on the map)
CREATE TABLE geo_event (
  event_id       UUID PRIMARY KEY,
  occurred_at    TIMESTAMPTZ NOT NULL,
  detected_at    TIMESTAMPTZ NOT NULL,  -- for edge latency audit
  category       TEXT[] NOT NULL,       -- [conflict, political, economic, ...]
  intensity      SMALLINT,              -- 1-5 (map filter)
  title          TEXT NOT NULL,
  summary        TEXT,
  lat            NUMERIC, lon NUMERIC,  -- pulse position on map
  geo_regions    TEXT[],               -- ISO country codes
  affected_sectors TEXT[],             -- internal taxonomy
  sentiment      TEXT,                 -- risk_off | risk_on | neutral
  cameo_code     TEXT,                 -- GDELT CAMEO classification
  source_urls    TEXT[],
  source_provider TEXT,                -- "gdelt" | "finnhub"
  tenant_id      UUID                  -- multi-tenant ready (NULL = global event)
);
CREATE INDEX ON geo_event(occurred_at DESC);
CREATE INDEX ON geo_event USING GIN(category);  -- fast category filtering

-- EVENT_EXPOSURE: event ↔ company link (key for the map)
CREATE TABLE event_exposure (
  event_id       UUID REFERENCES geo_event,
  company_id     UUID REFERENCES company,
  exposure_type  TEXT,             -- direct | supply_chain | sector | currency
  direction      TEXT,             -- bullish | bearish | neutral
  magnitude      NUMERIC,          -- exposure strength 0-1
  price_change_t1d NUMERIC,        -- observed reaction (filled in later)
  PRIMARY KEY (event_id, company_id)
);

-- EVENT_EMBEDDING: pgvector for semantic search of historical analogies
CREATE TABLE event_embedding (
  event_id       UUID PRIMARY KEY REFERENCES geo_event,
  embedding      VECTOR(1536)      -- OpenAI text-embedding
);
CREATE INDEX ON event_embedding
  USING hnsw (embedding vector_cosine_ops);  -- fast similarity search
```

### Custom Scoring — Indicators and Scores

```sql
-- INDICATOR: custom indicator definition (user-defined)
CREATE TABLE indicator (
  indicator_id   UUID PRIMARY KEY,
  tenant_id      UUID NOT NULL,     -- whose indicator
  name           TEXT NOT NULL,
  formula_dsl    TEXT NOT NULL,     -- "(ROE*0.3)+RANK_SECTOR(FCF_YIELD,0.4)"
  benchmark_mode TEXT,              -- sector | market | custom_peer | hist_self
  normalization  TEXT,              -- percentile | zscore | minmax | raw
  direction      TEXT,              -- higher_better | lower_better
  geo_weight     NUMERIC DEFAULT 0, -- geopolitical modifier weight
  version        INT DEFAULT 1,     -- definition versioning
  created_at     TIMESTAMPTZ
);

-- COMPANY_SCORE: computed company score per indicator
CREATE TABLE company_score (
  company_id     UUID REFERENCES company,
  indicator_id   UUID REFERENCES indicator,
  score          NUMERIC NOT NULL,  -- normalized 0-100
  raw_value      NUMERIC,           -- before normalization
  percentile     NUMERIC,           -- position in benchmark
  geo_adjusted   NUMERIC,           -- after geopolitical modifier
  computed_at    TIMESTAMPTZ,
  inputs_hash    TEXT,              -- hash of input data (invalidation)
  PRIMARY KEY (company_id, indicator_id)
);
```

### AI and Recommendations

```sql
-- AI_RECOMMENDATION: recommendation per event × company
CREATE TABLE ai_recommendation (
  rec_id         UUID PRIMARY KEY,
  event_id       UUID REFERENCES geo_event,
  company_id     UUID REFERENCES company,
  generated_at   TIMESTAMPTZ,       -- latency audit
  action_signal  TEXT,              -- HOLD|WATCH|BUY_OPP|REDUCE_RISK|HEDGE|CONTRARIAN
  direction      TEXT,              -- BULLISH|BEARISH|NEUTRAL|MIXED
  confidence     NUMERIC,           -- 0-1 (always visible)
  sample_size    INT,               -- number of analogies (transparency)
  rationale      TEXT,              -- NL justification
  forecast       JSONB,             -- {t1d:{median,p25,p75}, t1w:{...}}
  analogies      JSONB,             -- [{event_id, similarity, actual_return}]
  scenario_tree  JSONB,             -- [{scenario, probability, impact}]
  model_version  TEXT,              -- reproducibility
  actual_t1d     NUMERIC,           -- actual result (ex-post)
  accuracy       NUMERIC            -- system track record
);
```

### User, Portfolio, Alerts

```sql
-- All with tenant_id for future multi-tenancy
CREATE TABLE portfolio (
  portfolio_id   UUID PRIMARY KEY,
  tenant_id      UUID NOT NULL,
  name           TEXT
);
CREATE TABLE position (
  portfolio_id   UUID REFERENCES portfolio,
  company_id     UUID REFERENCES company,
  shares         NUMERIC, avg_cost NUMERIC,
  PRIMARY KEY (portfolio_id, company_id)
);
CREATE TABLE alert_rule (
  rule_id        UUID PRIMARY KEY,
  tenant_id      UUID NOT NULL,
  alert_type     TEXT,             -- breaking_geo|tweet|score_change|...
  min_intensity  SMALLINT DEFAULT 4,
  scope          JSONB,            -- {tickers_core, tickers_watch, sectors}
  channels       JSONB,            -- {email, push, sms}
  daily_limit    INT DEFAULT 5,
  quiet_hours    JSONB,
  enabled        BOOLEAN DEFAULT true
);
```

> **Why this model supports the map as the center:** The map renders `GEO_EVENT` as pulses. A click opens a panel that through `EVENT_EXPOSURE` shows affected companies, through `COMPANY_SCORE` their custom scores, and through `AI_RECOMMENDATION` the analysis and recommendation. All of these are queries on foreign keys — fast and natural. The map is not an add-on; it is the entry point into the entire data graph.

---

## Section 08 — Scoring Model

*How custom indicators turn data into a company rating*

Scoring is the engine that turns raw fundamental, technical, and contextual data into a single, comparable number — with full user control over the logic. There has to be administration pannel to configure more parameters for custom scorings.

### Parameters Available in Indicator Formulas

| Category | Parameters | Data source |
|---|---|---|
| Valuation | `PE, PE_FWD, PB, PS, EV_EBITDA, PEG, P_FCF, DIV_YIELD` | FMP |
| Profitability | `ROE, ROA, ROIC, GROSS_MARGIN, OP_MARGIN, NET_MARGIN` | FMP |
| Growth | `REV_GROWTH_YOY, EPS_GROWTH, FCF_GROWTH, CAGR_3Y, CAGR_5Y` | FMP |
| Balance sheet | `NET_DEBT_EBITDA, DEBT_EQUITY, CURRENT_RATIO, ALTMAN_Z` | FMP |
| Technical | `RSI, MACD, PRICE_CHG_3M, MOMENTUM, REL_52W_HIGH, SMA_50_200` | Finnhub |
| Sentiment | `NEWS_SENTIMENT, ANALYST_REVISION, SHORT_FLOAT` | GDELT, Finnhub |
| Geo-context | `GEO_RISK_SCORE, GEO_EXPOSURE_PCT, ACTIVE_EVENTS` | Events engine |
| Macro | `RATE_SENSITIVITY, FX_EXPOSURE, COMMODITY_BETA` | FRED + computed |

### DSL Operators

| Type | Operators | Example |
|---|---|---|
| Arithmetic | `+ - * / %` | `ROE * 0.5 + ROA * 0.5` |
| Logical | `AND OR IF` | `IF(PE < 15, 1, 0)` |
| Ranking | `RANK_SECTOR PERCENTILE` | `RANK_SECTOR(FCF_YIELD)` |
| Time-series | `CHANGE CAGR CORR ZSCORE` | `ZSCORE(REV_GROWTH, 5Y)` |

### Score Calculation Pipeline

**Step 1 — DSL Formula Parsing**
The `formula_dsl` is parsed into an AST tree. Validation: do all parameters exist, are all operators correct? Returns a list of required input data.

**Step 2 — Data Fetch (cache-or-fetch)**
For each parameter — fetch through the data layer. Locally if fresh, from API only when necessary. Fundamental data has a 24 h TTL, so a score computed multiple times during the day generates no API costs.

**Step 3 — Evaluation on Raw Values**
The AST tree is evaluated → `raw_value`. Ranking operators (`RANK_SECTOR`) require data for the entire benchmark — fetched once for the whole group, cached.

**Step 4 — Normalization Against Benchmark**
The raw value is normalized according to `benchmark_mode` (sector/market/peer/history) and `normalization` (percentile/z-score). Winsorization of outliers. Result: `score` 0–100.

**Step 5 — Geopolitical Modifier**
If `geo_weight > 0`: score is adjusted for active geopolitical events affecting the company. A company with high exposure to a crisis region gets a `geo_adjusted` penalty. **This connects scoring to the map.**

**Step 6 — Persistence + Invalidation**
Score saved with `inputs_hash` (hash of input data). When data changes (new report, new event) — hash differs → automatic recomputation. Otherwise — cached value is returned.

> **Scoring profiles:** The user creates multiple indicators grouped into profiles (e.g. "Value Investor", "Growth Hunter", "Macro Aware"). Switching profile changes how the entire market is rated and colored on the map. Composite score is the weighted sum of indicators in the active profile.

---

## Section 09 — Map ↔ Scoring Correlation

*How custom ratings from the beginning of the project connect with the map*

This requirement was closed directly: custom ratings must be correlated with the map. The map is the center. Here is how these two elements become one cohesive system.

### Three Directions of Flow Between Map and Scoring

**Score colors the map**
Companies on the map (through HQ location or geo exposure) colored by the active custom score. High score = green, low = red. You see at a glance which of your companies are strong/weak according to your logic.

**Event modifies score**
When an event pulses on the map, its effect through the indicator's `geo_weight` adjusts the scores of affected companies in real time. A conflict in a region → drop in `geo_adjusted` score for companies exposed there. We need to have sophisticated ai reasoning for new events but in historical context. eg if there is a war in region it doesnt automatically means stock drop, lets check first how it impact stock in history with similar events. Nowdays social media info are more important eg Trump writes something on social and maket reacts immediately. You haave to be realy creative at this point, this is crutial part to get proper insights from the news.

**Map filters the screener**
Click on a region/event on the map → screener shows companies affected by that event, sorted by custom score. "Show me the best companies by my indicator affected by this conflict."

### Example User Journey

```
# Scenario: morning, you open StokAI

1. Map loads with active scoring profile "Value Investor"
   └─ Your companies colored by Value score (green=cheap+good)

2. A red event pulses in the Persian Gulf (conflict, intensity 5)
   └─ System finds via EVENT_EXPOSURE: 3 energy companies
      in the portfolio with exposure to the region

3. Indicator geo_weight (0.2) adjusts their score:
   └─ XOM: score 78 -> geo_adjusted 71 (regional risk)
   └─ but: AI flags CONTRARIAN — historically energy
      GAINED on such events

4. You click the event -> panel shows:
   └─ 3 affected companies + their score + AI recommendation
   └─ analogies: "8 similar events, XOM T+1W median: +4.2%"

5. You click "show in screener" -> list of affected energy,
   sorted by your Value score
   └─ investment decision in 90 seconds instead of 40 minutes
```

> **This is the core of the product.** The map, custom scoring, and AI are not three separate features — they are one integrated decision flow. Event on the map → affected companies → your scoring → historical context → recommendation. Each element amplifies the others. What no financial terminal offers: *personalized synthesis at the point of decision*.

---

## Section 10 — Functional Requirements

*Complete feature list with priorities*

Collected and consolidated requirements from the entire process. Priorities: P0 = critical for MVP, P1 = important, P2 = useful later.

### Map Module (Application Center)

| Feature | Description | Priority |
|---|---|---|
| Intelligence Map | World map with animated event pulses. Color = category, size = intensity. WebGL rendering. | P0 |
| Category filters | Category checkboxes (conflicts, political, economic, energy, regulatory, news). Unchecking hides pulses. | P0 |
| Intensity filter | Separate filter layer: high/medium/low intensity. | P0 |
| Popup → Panel | Click on pulse → mini popup (title, companies, price changes) → "Expand" → side panel with full analysis. | P0 |
| Context modes | Global / Portfolio / Sector — filtering events by relation to companies. Companies split into sectors. | P0 |
| Time mode | Live (real-time feed) / Historical (date slider) / Playback (animation). User-modifiable dates. | P1 |
| Score coloring | Companies on map colored by the active custom score. | P1 |
| Background heatmap | Countries shaded by geopolitical activity intensity. | P2 |
| Map Zoom-in/Zoom-out | There could be many events in the same region. Map has to be able to zoom in and out to see grouped events, for zoom in the evenst get better granularity so when max zoom in i can see particular events. Event clustering at low zoom, de-clustering to individual events at high zoom|
|Source configurability (add/remove/disable via admin) | Each data source (external/internal) has to be configurable in dedicated admin panel| P1 |
| Audit of every AI decision + override feedback loop| Prompt evaluation will use that | P0 |
|User onboarding / portfolio setup | UI which allow user portfolio setup. Dedicated section in admin panel | P2 |
| User authentication and app security | Login with username and password as a bare minimum for MVP. Production - OAuth2 | P0 |

### Custom Scoring & Screener

| Feature | Description | Priority |
|---|---|---|
| Indicator Builder | Visual indicator creator. DSL formula editor, parameter library, versioning. | P0 |
| Scoring Engine | Normalization, benchmark (sector/market/peer/history), composite scores, geo modifier. | P0 |
| Global Screener | Filtering US companies by all indicators and scores. AND/OR operators. Sorting, export. | P0 |
| Scoring profiles | Multiple profiles (Value/Growth/Macro), quick switching affecting map and screener. | P1 |
| Geo overlay screener | Overlay filter: companies affected by event X, sorted by custom score. | P1 |

### AI Intelligence

| Feature | Description | Priority |
|---|---|---|
| Morning Brief | Daily personalized report per portfolio (06:00). What happened, what is relevant for your companies. | P0 |
| Instant Event Analysis | Within 90 sec of event: affected companies, direction, analogies, recommendation. | P0 |
| Action Recommendation | Decision framework per company (HOLD/WATCH/BUY_OPP/REDUCE_RISK/HEDGE/CONTRARIAN). Framework, not signal. | P0 |
| Historical Context Q&A | Chat: questions about a company in historical context. Semantic search over archive. | P0 |
| Event Impact Forecast | Probabilistic forecast T+1D/1W/1M/3M/1Y (median, p25, p75) from historical analogies. | P1 |
| Contrarian Flag | Overreaction detection vs. historical medians — contrarian opportunities. | P1 |
| Scenario Tree | Scenario tree (escalation/de-escalation) with probabilities. | P2 |

### Alert System

| Feature | Description | Priority |
|---|---|---|
| Breaking Event Alert | Intensity 4-5 event affecting your companies. <90 sec. Email + push. | P0 |
| High-Signal Tweet Alert | Tweet from TIER1 (CEO, Fed, minister) with tickers. <30 sec. Biggest edge. | P0 |
| Email HTML Brief | Responsive email, readable in 60 sec on phone. Charts, companies, recommendation. | P0 |
| Anti-fatigue control | Daily limit, quiet hours, thresholds per ticker (core vs watchlist). | P0 |
| Score Change Alert | Change in composite score above threshold with reason stated. | P1 |
| Earnings Risk Alert | 14/7/1 days before report: AI brief on macro/geo context. | P1 |
| SEC Filing Alert | Form 8-K, insider buy/sell above threshold. <20 min from filing. | P1 |

---

## Section 11 — Map as the Center — Specification

*Technical details of the central interface*

### Rendering Technology

| Element | Technology | Why |
|---|---|---|
| Base map | MapLibre GL JS - rethink best map interface. Map has to be zoomable | Open-source (zero license costs vs Mapbox). WebGL — smooth rendering of thousands of points. Self-hostable tiles. |
| Event pulses | Custom WebGL layer + D3 | Animated pulsing circles. Color by category, size by intensity. Efficient with hundreds of events. |
| Heatmap | MapLibre heatmap layer | Native GL heatmap layer — intensity per region. |
| Real-time push | WebSocket | New events appear on the map without page reload. |

### Interactions (confirmed during design process)

**Animated pulses** — Every event is a pulsing circle. Color identifies category, size identifies intensity. Confirmed choice: pulse/animated circles.

**Checkbox filters** — Categories as checkboxes. Unchecking a category immediately removes its pulses from the map. Plus intensity filter.

**Hybrid mode** — Global + option to highlight portfolio/sector. Companies split into sectors. Confirmed choice.

**Popup + Panel** — Click → popup with "Expand" option → side panel. Both levels of detail. Confirmed choice.

**Time mode** — Historical (slider) + Playback (animation) to choose from. In time mode shows price impact on portfolio/sector companies.

**Context in panel** — Companies visible in side panel, not on the map. Map shows events, panel connects them to companies.

### Side Panel Content (after "Expand")

```
┌─────────────────────────────────────┐
│ [category] Event title               │
│ Location · date · intensity          │
├─────────────────────────────────────┤
│ EVENT DESCRIPTION (AI summary)       │
│ Tags · Sources                       │
├─────────────────────────────────────┤
│ PRICE IMPACT — T±7 day window        │
│ [sparkline chart per company]        │
│ ↑ event line T=0                     │
├─────────────────────────────────────┤
│ AI RECOMMENDATION                    │
│ Signal: CONTRARIAN · Confidence: 72% │
│ Sample: 8 historical analogies       │
│ Rationale: [justification]           │
│ Forecast T+1W: +4.2% (p25:+1, p75:+8)│
├─────────────────────────────────────┤
│ HISTORICAL ANALOGIES                 │
│ [list of similar events + results]   │
├─────────────────────────────────────┤
│ AFFECTED COMPANIES + CUSTOM SCORE    │
│ XOM · score 71 · +2.1% [Expand]      │
│ [button: Show in screener]           │
└─────────────────────────────────────┘
```

---

## Section 12 — AI Intelligence Engine

*How synthesis works and where the edge comes from*

AI is the layer that turns data into decisions. The edge is not in the speed of the feed (that is a commodity) — it is in the automatic synthesis that takes an analyst 20–40 minutes, and the system 90 seconds.

### Event Analysis Pipeline (Real-time)

**Step 1 — Detection (0–15 sec)**
New event from GDELT (15 min poll) or tweet from Twitter Filtered Stream (<5 sec). Or other social media defined earlier Saved to `geo_event` with `detected_at` for latency audit.

**Step 2 — LLM Classification (15–45 sec)**
Azure OpenAI classifies: category, region, sectors, intensity, sentiment. Cheap, fast classification in VNet. Event embedding → pgvector.

**Step 3 — Exposure Mapping (45–60 sec)**
System finds affected companies: directly mentioned + through `geo_revenue` (geographic exposure) + through sector. Creates `event_exposure` records.

**Step 4 — Historical Matching (60–75 sec)**
Semantic search in pgvector: find N most similar historical events. For each — how did affected companies react (from `price_bar`). This yields analogies and sample size.

**Step 5 — Recommendation (75–90 sec)**
Claude API synthesizes: context + analogies + scores → `ai_recommendation` with action_signal, confidence, forecast (percentiles), rationale. Saved with model_version.

**Step 6 — Dispatch (90+ sec)**
If event meets alert rule — email/push. Appearance on map via WebSocket. User knows before the retail market catches on.

### Division of Labor Between LLM Models

| Task | Model | Why |
|---|---|---|
| Event classification | Azure OpenAI (GPT-4o-mini) | High volume, simple classification. Low cost, low latency, in VNet (privacy). |
| Embeddings | Azure OpenAI embeddings | Cheap vectorization, once per event (TTL infinite). |
| Recommendations & analysis | Claude API (Opus) | Complex reasoning, context synthesis, nuance. Quality justifies cost at lower volume. |
| Historical Q&A | Claude API | Interactive chat requiring deep understanding of context. |

> **Transparency as a legal requirement:** Every recommendation carries `confidence` and `sample_size`. When analogies < 5 — a clear disclaimer. The `actual_t1d` field filled in ex-post builds a measurable track record for the system. Recommendations are decision frameworks, not transaction signals — the foundation of responsibility for a commercial product.

---

## Section 13 — Alert System — Being Ahead of the Market

*The only feature running when the application is closed*

Alerts are the most critical part of the edge. Realistic goal: arriving 20–90 minutes ahead of the average retail investor. We do not compete with HFT — we compete with information latency.

### Latency Hierarchy of Market Participants

| Participant | Latency | Our position |
|---|---|---|
| HFT / Algo | <1 ms | Not competing — different game |
| Sell-side (banks) | minutes–hours ahead | Not competing — onside |
| Large funds | 5–30 min | Difficult fight |
| **StokAI** | **2–10 min** | **Real advantage vs retail** |
| Retail investors | 30–120 min | Our market — 20–90 min edge |

### Alert Types and Target Latency

| Type | Source | Latency | Channel | Priority |
|---|---|---|---|---|
| High-Signal Tweet | X Filtered Stream | <30 sec | Push+Email | P0 |
| Breaking Geo (4-5) | GDELT+LLM | <90 sec | Email+Push+SMS | P0 |
| Score Change | Scoring engine | <5 min | Email+In-app | P1 |
| Earnings Risk | Calendar+LLM | 14/7/1D | Email | P1 |
| SEC Filing | EDGAR feed | <20 min | Email+In-app | P1 |
| Morning Brief | Batch LLM | 06:00 | Email HTML | P0 |
| Overnight Brief | Batch LLM | 22:00 | Email | P2 |

> **Biggest edge: TIER1 tweet.** A tweet from a CEO/Fed member/minister hits Filtered Stream in <5 sec. LLM extracts tickers and sentiment in 20–30 sec. Alert to you before the news reaches aggregators. This is the **greatest real advantage in the system** — why Twitter/X Basic ($100/month) is in the MVP despite the cost. Twitter/X in production app, for MVP use free api if exists.

### Anti-fatigue — Protection from Information Overload

A commercial system must respect the user's attention. Without overload control, alerts become noise that the user disables — losing the entire edge.

| Mechanism | Action |
|---|---|
| `daily_push_limit` | Max number of pushes per day (default 5). Rest aggregated in digest. |
| `quiet_hours` | No push during defined hours (e.g. 22:00–06:30). |
| `threshold per ticker` | Core holdings: alert at intensity 3+. Watchlist: only intensity 5. |
| `deduplication` | Same event from multiple sources = one alert. |

---

## Section 14 — External Integrations

*All data sources for the US market. All sources fully configurable through admin panel.*

### MVP Stack — US Market

| Integration | Role | Cost/month | Latency/TTL |
|---|---|---|---|
| Finnhub.io and Polygon.io| US prices real-time/delayed, OHLCV, streaming | $0 | 15 min / RT switch |
| Financial Modeling Prep | Fundamentals, ratios, earnings (SEC source) | $14 | 24 h TTL |
| GDELT Project | Geopolitics, CAMEO events, 100+ languages | $0 | 15 min poll |
| FRED | Macro: CPI, GDP, rates, yields (800k series) | $0 | Calendar |
| Finnhub | Per-ticker market news, earnings calendar | $0 | Real-time |
| SEC EDGAR | Filings 8-K/10-K, Form 4 insider (real-time) | $0 | Real-time feed |
| Twitter/X API | Filtered Stream — TIER1 tweets (max edge) | $100 | <5 sec stream |
| Azure OpenAI | Event classification, embeddings | ~$15 | On-demand |
| Claude API | Recommendations, analysis, Q&A | ~$30 | On-demand |
| **TOTAL MVP** | **Full information edge** | **as low as possible** | — |

### Outbound Integrations (Phase 2+)

| Integration | Purpose | Phase |
|---|---|---|
| SendGrid / Azure Comm. | Sending alert emails (HTML responsive) Consider something for free. | MVP |
| Push (FCM/APNs) | Mobile push notifications | Phase 2 |
| Interactive Brokers API | Live portfolio view (optional) | Phase 3 |
| Webhooks (Zapier/Make) | User integrations with their own tools | Phase 3 |

> **Note on data freshness — provider switch:** The MVP stack uses Finnhub API in 15 min mode ($0). Switching to real-time requires Finnhub Websocket ($0 for <60 calls per second) — that is a plan change with the provider + a flag in configuration, **not a code change**. Provider abstraction (Section 06) ensures the business logic does not know which option is active.

---

## Section 15 — Azure Deployment

*Hybrid: local database + cloud compute, with self-host option*

### Component to Azure Mapping

| Component | Azure Service | Self-host alternative |
|---|---|---|
| Backend API | Azure Container Apps | Docker Compose / K8s |
| PostgreSQL+Timescale | Azure DB for PostgreSQL Flexible | PostgreSQL container |
| Redis | Azure Cache for Redis | Redis container |
| Task workers | Container Apps (Celery) | Celery container |
| LLM classification | Azure OpenAI (in VNet) and possiblity to extend to other LLM, access has to be abstracted | External API / local model |
| Blob storage | Azure Blob Storage | MinIO / local FS |
| Secrets | Azure Key Vault | HashiCorp Vault / .env |
| Monitoring | Azure Monitor (optional due to saving costs for MVP) + App Insights (optional due to saving costs) | Prometheus + Grafana |

### Hybrid Topology

```
Data Layer — local (cost control + privacy)
├── PostgreSQL + TimescaleDB
├── pgvector
└── Redis cache
Can run on-premise or in Azure DB. Fetched data kept locally — drastic API cost reduction.

        ↕ VNet / private connection

Compute Layer — cloud (AI scalability)
├── Azure OpenAI
├── Container Apps (API + workers)
└── Claude API (external)
AI compute where the power is. Classification in VNet (data privacy),
complex analysis via Claude API.
```

### Containerization Strategy

```yaml
# docker-compose.yml — identical dev and self-host
services:
  api:
    build: ./backend
    environment:
      - DATABASE_URL=${DATABASE_URL}
      - PROVIDER_MODE=${PROVIDER_MODE}  # 15min|realtime|eod
      - LLM_CLASSIFIER=${LLM_CLASSIFIER}  # azure|local
  worker:
    build: ./backend
    command: celery worker
  postgres:
    image: timescale/timescaledb-ha:pg16
  redis:
    image: redis:7

# Azure: same containers -> Container Apps
# Self-host: docker compose up -> works identically
```

> **No hard lock-in:** The only Azure-specific services are OpenAI (has an alternative in Claude API or a local model) and optionally managed PostgreSQL/Redis (have containerized equivalents). Moving everything to a private server is a change of environment variables and `docker compose up`. This fulfills the requirement of "local hosting option".

---

## Section 16 — Cost Model

*Realistic costs across three phases*

### Phase MVP (single-user — you)

| Item | Cost/month |
|---|---|
| Data (Finnhub API + FMP + Twitter + free) | should be free if possible for mvp, we can pay if soluition will work well |
| AI (Azure OpenAI + Claude API) | ~$30-50 minimum costs as possible |
| Azure infrastructure (Container Apps, DB, Redis — small) | ~$30-40 goal is to minimize costs for mvp, if app will work well we can scale out |
| **TOTAL MVP** | **~$268/month** |

### Phase Growth (50 paying users)

| Item | Cost/month |
|---|---|
| Data (Finnhub Websocket or REST API + FMP Pro + Benzinga) | ~$400 |
| AI (scaled with volume) | ~$300 |
| Infrastructure (scaled) | ~$300 |
| **TOTAL Growth** | **~$1,000/month** |

> **Unit economics:** At 50 users paying $30/month = $1,500 revenue vs ~$1,000 costs. Each phase is self-financing at the right subscription pricing. Local-first storage means data costs grow slower than linearly with number of users — because the same market data is shared (fetched once, served to all).

---

## Section 17 — Implementation Roadmap

*From data foundation to full edge*

### Phase 1 — Data Foundation (Month 1–2)

Provider abstraction, market abstraction (US), cache-or-fetch, storage (PostgreSQL+Timescale). Ingestion of prices and fundamentals for ~150 companies. This is the foundation — nothing works without it.

Tags: `Provider abstraction` · `Local-first cache` · `US market` · `~150 companies`

### Phase 2 — Scoring + Screener (Month 2–3)

Indicator Builder (DSL parser), Scoring Engine (normalization, benchmark), Global Screener. Custom ratings working — foundation for correlation with the map.

Tags: `DSL engine` · `Scoring` · `Screener` · `Profiles`

### Phase 3 — Map + Events (Month 3–5) CENTER

GDELT integration, event classifier (LLM), exposure mapping, Intelligence Map (MapLibre + pulses), side panel, score and map correlation. This is the heart of the product.

Tags: `Intelligence Map` · `Event classifier` · `Exposure mapping` · `Score and Map`

### Phase 4 — AI + Alerts (Month 5–7)

Recommendation engine (Claude), historical matching (pgvector), Twitter Filtered Stream, alert engine with anti-fatigue, Morning Brief, HTML email. Information edge active.

Tags: `AI recommendations` · `Twitter edge` · `Alerts` · `Historical Q&A`

### Phase 5 — Time Machine + Polish (Month 7–9)

Historical map mode (slider, playback), Score Replay, Analog Finder, scenario trees. UX refinement. Preparation for multi-tenant (activation of tenant_id logic).

Tags: `Time Machine` · `Playback` · `Multi-tenant ready`

### Phase 6 — New Markets (Month 9+)

Test of market abstraction: adding LSE/XETRA as configuration. If abstraction was done correctly (Section 04) — this is configuration + provider adapter, not a rebuild.

Tags: `Market expansion` · `LSE / XETRA` · `Config-only`

---

## Section 18 — Risks and Mitigations

*What can go wrong and how we protect ourselves*

| Risk | Mitigation | Level |
|---|---|---|
| Twitter/X raises API prices | Provider abstraction — swap to StockTwits+Reddit+Telegram without changing logic | HIGH |
| Data quality (incorrect fundamentals) | SEC EDGAR as source of truth + cross-source validation at ingestion | HIGH |
| AI hallucinations in recommendations | Confidence + sample_size visible, recommendations are frameworks not signals, ex-post track record | HIGH |
| API costs grow with usage | Local-first cache — data fetched once, TTL per type, history kept forever. Find free alternatives for paid services. | MEDIUM |
| Vendor lock-in (provider/Azure) | Abstraction + containerization — swap provider or move to self-host without refactor | MEDIUM |
| GDELT commercial license | License verification before launch + ACLED as backup conflict data | MEDIUM |
| Rate limiting on free APIs | Aggressive cache, nightly batch jobs, Redis TTL per endpoint | MEDIUM |
| Legal liability for recommendations | Clear disclaimers, decision frameworks not signals, no user risk profile factored in | REVIEW |
| Data redistribution (licenses) | System operates on derived data (scores, analyses), not raw prices. Legal review before launch. | REVIEW |

---

> **The most important technical decision from day 1:**
> Build the **data abstraction layer** and **market abstraction** before writing the first line of business logic. This is not a later optimization — it is the foundation. Every provider change, every new market, every switch between real-time/delayed goes through these layers. Skipping them means rewriting the system at the first change. This is the difference between a commercial project and a prototype.

---

**Cold-start problem for historical analogies**
The AI edge needs a deep event+price archive to find analogies. On day 1, the event archive is empty (GDELT backfill helps for geo events, but the event→price-reaction pairs that make analogies useful accrue over time). Document a backfill strategy: seed the event archive from GDELT's historical files (1979+) and pair with historical prices, so the analogy engine isn't useless for the first 6 months. Without this, "8 similar historical events" can't be delivered at launch.

Beyond entering a portfolio, the first-run should establish a scoring profile (or offer presets: Value/Growth/Macro) so the map is meaningful on first load. A new user with no profile and no holdings sees an empty map and bounces. Presets + a guided setup convert the first session.


*StokAI MASTER ARCHITECTURE DOCUMENT · v1.0 · May 2026*
*Ready for implementation · All requirements consolidated*
