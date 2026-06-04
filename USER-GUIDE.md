# StokAI — Complete User & Operations Guide

StokAI is a geopolitical intelligence platform for retail investors. It compresses 20–40 minutes
of manual news analysis into a 90-second interactive briefing by combining a deterministic
reactive event pipeline (Mode A) with deliberative multi-agent AI workflows (Mode B).

This guide covers everything: getting the stack running, configuring external data sources,
managing users and tenants, navigating every screen of the frontend, understanding how the
AI workflows operate, and operating the admin console.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Prerequisites](#prerequisites)
3. [First-Time Setup](#first-time-setup)
4. [Running the Stack](#running-the-stack)
   - [Full Docker Stack](#full-docker-stack)
   - [Backend Manually (Hot-Reload)](#backend-manually-hot-reload)
5. [Authentication & Tenant Management](#authentication--tenant-management)
   - [Tenant Model](#tenant-model)
   - [Creating the First Admin](#creating-the-first-admin)
   - [Login Flow](#login-flow)
   - [Token Lifecycle](#token-lifecycle)
   - [Roles & Permissions](#roles--permissions)
   - [Creating Additional Users](#creating-additional-users)
6. [External Data Sources](#external-data-sources)
   - [Source Architecture](#source-architecture)
   - [GDELT](#gdelt-geopolitical-event-database)
   - [ACLED](#acled-armed-conflict-location--event-data)
   - [Finnhub](#finnhub)
   - [FMP (Financial Modeling Prep)](#fmp-financial-modeling-prep)
   - [FRED (Federal Reserve)](#fred-federal-reserve-economic-data)
   - [SEC EDGAR](#sec-edgar)
   - [SendGrid (Email Delivery)](#sendgrid-email-delivery)
   - [Configuring a Source End-to-End](#configuring-a-source-end-to-end)
   - [Market-Source Bindings](#market-source-bindings)
7. [Using the Application](#using-the-application)
   - [Onboarding Flow](#onboarding-flow)
   - [Intelligence Map](#intelligence-map)
   - [Company Detail](#company-detail)
   - [Screener](#screener)
   - [Briefs](#briefs)
   - [Q&A Chat](#qa-chat)
   - [Portfolio & Watchlist](#portfolio--watchlist)
   - [Alerts & Notifications](#alerts--notifications)
8. [AI Workflows In Depth](#ai-workflows-in-depth)
   - [Mode A — Reactive Pipeline (12 Steps)](#mode-a--reactive-pipeline-12-steps)
   - [Mode B — LangGraph Workflows](#mode-b--langgraph-workflows)
   - [Morning Brief](#morning-brief-workflow)
   - [Event Deep Dive](#event-deep-dive-workflow)
   - [On-Demand Analysis](#on-demand-analysis-workflow)
   - [Earnings Risk Brief](#earnings-risk-brief-workflow)
   - [Watchlist Scan](#watchlist-scan-workflow)
   - [Cost Controls & Budget Hierarchy](#cost-controls--budget-hierarchy)
   - [Human-in-the-Loop (HIL)](#human-in-the-loop-hil)
9. [Admin Console](#admin-console)
   - [Data Sources Tab](#data-sources-tab)
   - [System Ops Tab](#system-ops-tab)
   - [AI Audit Console](#ai-audit-console)
   - [HIL Queue](#hil-queue)
10. [Prompt Management](#prompt-management)
11. [Database Migrations](#database-migrations)
12. [Seeding Historical Data](#seeding-historical-data)
13. [Observability](#observability)
14. [Testing](#testing)
15. [Service URLs & Ports](#service-urls--ports)
16. [Environment Variables Reference](#environment-variables-reference)
17. [Makefile Cheat-Sheet](#makefile-cheat-sheet)
18. [Backend Module Reference](#backend-module-reference)

---

## Architecture Overview

```
External sources
(GDELT · ACLED · Finnhub · FMP · FRED · SEC EDGAR)
        │
        ▼
┌─────────────────────────────────┐
│  Ingestion / Cache Layer        │  Redis hot → PostgreSQL persistent → provider
└─────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────┐
│  PostgreSQL / TimescaleDB       │  + pgvector for semantic search
└─────────────────────────────────┘
        │
   ┌────┴────────────────┐
   │                     │
   ▼                     ▼
Mode A               Mode B
Reactive Pipeline    LangGraph Workflows
12 steps, <90 s      2–5 min, $0.50–$5.00
~$0.05/event         Claude Sonnet 4.6 + Opus
   │                     │
   └────────┬────────────┘
            ▼
    FastAPI REST + WebSocket
            │
            ▼
    React 18 SPA
(MapLibre GL · Recharts · TanStack Query)
```

**Mode A** processes every incoming geopolitical event through 12 deterministic steps in
under 90 seconds: classify → extract tickers → embed → compute exposure → find analogies →
generate alert text → evaluate rules → dispatch.

**Mode B** runs five deliberative LangGraph workflows with nine named Claude agents.
Workflows: Morning Brief, On-Demand Analysis, Watchlist Scan, Earnings Risk Brief,
Event Deep-Dive.

---

## Prerequisites

| Tool | Minimum version | Notes |
|------|----------------|-------|
| Docker Desktop | 24+ | Compose v2 is included |
| Python | 3.12+ | Only for manual backend runs |
| Node.js | 20+ | Only for frontend tests |
| make | any | Optional — raw commands listed throughout |

**API keys required before the first run:**

| Key | Service | Where to get it |
|-----|---------|-----------------|
| `ANTHROPIC_API_KEY` | Claude models (primary reasoning) | console.anthropic.com |
| `OPENAI_API_KEY` | Embeddings (`text-embedding-3-small`) | platform.openai.com |
| `LANGFUSE_SECRET_KEY` + `LANGFUSE_PUBLIC_KEY` | Self-hosted Langfuse | Generated during first Langfuse startup (see below) |

**Optional keys** (features degrade gracefully when absent):

| Key | Purpose |
|-----|---------|
| `FINNHUB_API_KEY` | Live stock prices |
| `FMP_API_KEY` | Financial Modeling Prep (fundamentals) |
| `SENDGRID_API_KEY` | Email delivery for alerts and briefs |
| `ACLED_API_KEY` | Alternative event seeding source |
| `FRED_API_KEY` | Macro indicators (rates, GDP, inflation) |

---

## First-Time Setup

```bash
# 1. Clone the repo (skip if already done)
git clone <repo-url>
cd stokai

# 2. Copy the environment template
cp .env.example .env

# 3. Fill in every REPLACE_ME value in .env (use any editor)
#    Required fields to fill:
#      POSTGRES_PASSWORD
#      ANTHROPIC_API_KEY
#      OPENAI_API_KEY
#      LANGFUSE_SECRET_KEY
#      LANGFUSE_PUBLIC_KEY
#      LANGFUSE_DB_PASSWORD
#      JWT_SECRET_KEY            (min 32 random chars)
#      JWT_REFRESH_SECRET_KEY    (min 32 random chars, different from above)
#      SEED_ADMIN_EMAIL          (e.g. admin@yourdomain.com)
#      SEED_ADMIN_PASSWORD       (min 12 chars)

# 4. Generate strong JWT secrets:
python -c "import secrets; print(secrets.token_hex(32))"
# Run twice — one value for JWT_SECRET_KEY, another for JWT_REFRESH_SECRET_KEY
```

**Langfuse key generation:** On the first `make up`, Langfuse starts at http://localhost:3000.
Create an account, then go to Settings → API Keys to obtain the public and secret keys.
Stop the stack, add them to `.env`, and restart.

> **Never commit `.env`.** It is already listed in `.gitignore`.

---

## Running the Stack

### Full Docker Stack

```bash
# Build images and start all eight services
make up
# or
docker compose up -d --build

# First startup takes 2–4 minutes (image build + pulls)
# Subsequent starts are fast (layers cached)

# Stream logs
make logs
docker compose logs -f api      # API only
docker compose logs -f worker   # Celery worker only

# Check service health
make ps

# Stop everything
make down
```

**Services started:**

| Container | Role |
|-----------|------|
| `postgres` | TimescaleDB (PostgreSQL 16 + pgvector) |
| `redis` | Hot cache + Celery broker |
| `langfuse-db` | Langfuse metadata store |
| `clickhouse` | Langfuse analytics backend |
| `langfuse-server` | Observability UI (port 3000) |
| `api` | FastAPI application (port 8000) |
| `worker` | Celery task worker (Mode B workflows) |
| `beat` | Celery scheduler (morning briefs, scans) |

### Backend Manually (Hot-Reload)

Use this during active development to avoid Docker rebuild cycles.

```bash
# Start only infrastructure services
docker compose up -d postgres redis langfuse-db clickhouse langfuse-server

# Create and activate virtualenv
python -m venv .venv
.venv\Scripts\activate           # Windows
# source .venv/bin/activate      # macOS / Linux

# Install dependencies
pip install -e ".[dev]"

# Override service URLs to point at localhost
# Windows (PowerShell)
$env:DATABASE_URL = "postgresql+asyncpg://stokai:<password>@localhost:5432/stokai"
$env:REDIS_URL    = "redis://localhost:6379/0"
$env:LANGFUSE_HOST = "http://localhost:3000"

# Run API with auto-reload
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

# --- In a second terminal (same venv + env vars) ---
# Celery worker (required for Mode B workflows)
celery -A src.config.celery_app worker --loglevel=info

# --- In a third terminal ---
# Celery beat (scheduled jobs: morning brief, watchlist scan)
celery -A src.config.celery_app beat --scheduler celery.schedulers.PersistentScheduler
```

---

## Authentication & Tenant Management

### Tenant Model

StokAI uses a **lightweight multi-tenant model**: there is no dedicated `tenant` table.
Instead, every database entity carries a `tenant_id` UUID column. The JWT middleware
extracts `tenant_id` from the token and injects it into every query automatically.

Tenants are logical namespaces — a tenant UUID is just a UUID you choose and set in
`SEED_TENANT_ID`. All users, portfolios, events, and briefs belonging to the same
`tenant_id` are isolated from other tenants. Cross-tenant access returns **404** (not 403)
by design to prevent information leakage.

### Creating the First Admin

There is no sign-up UI. The initial admin account is created via the seed script using
environment variables:

```bash
# Set these in .env before seeding
SEED_ADMIN_EMAIL=admin@yourdomain.com
SEED_ADMIN_PASSWORD=MinTwelveChars!
SEED_TENANT_ID=00000000-0000-0000-0000-000000000001   # any UUID you choose

# Then run migrations first, then seed
make migrate
make shell-api
# Inside the container:
python scripts/seed.py
```

The seed script hashes the password with bcrypt, inserts a `User` row with `role=admin`,
and exits. The password is never logged or persisted in plaintext.

### Login Flow

All API clients (including the SPA) authenticate with JWT bearer tokens.

**Step 1 — Login:**

```http
POST /api/v1/auth/login
Content-Type: application/json
X-Tenant-ID: 00000000-0000-0000-0000-000000000001

{
  "email": "admin@yourdomain.com",
  "password": "MinTwelveChars!"
}
```

**Response:**

```json
{
  "data": {
    "access_token": "eyJhbGciOiJIUzI1NiIs...",
    "token_type": "bearer",
    "expires_in": 900
  }
}
```

The response also sets an **HttpOnly cookie** (`refresh_token`) with:
- Path restricted to `/api/v1/auth/refresh`
- `SameSite: Strict`
- `Secure: true` in non-local environments
- 7-day TTL

**Step 2 — Use the access token:**

```http
GET /api/v1/portfolios
Authorization: Bearer eyJhbGciOiJIUzI1NiIs...
```

### Token Lifecycle

| Token | TTL | Storage | Purpose |
|-------|-----|---------|---------|
| Access token | 15 min | Client memory / localStorage | Authenticates every API request |
| Refresh token | 7 days | HttpOnly cookie | Obtains new access tokens without re-login |

**Refreshing:**

```http
POST /api/v1/auth/refresh
X-Tenant-ID: <tenant-uuid>
Cookie: refresh_token=<auto-sent by browser>
```

The server verifies the refresh token against a bcrypt hash stored in the `refresh_token`
table, issues a new access token, and returns it.

**Logout:**

```http
POST /api/v1/auth/logout
```

Revokes the refresh token row in the database and clears the cookie. Always returns 204,
even if the token was already revoked.

**Access token claims (JWT payload):**

```json
{
  "sub": "<user_id UUID>",
  "tenant_id": "<tenant UUID>",
  "role": "admin",
  "iat": 1719000000,
  "exp": 1719000900
}
```

### Roles & Permissions

| Role | Who | Capabilities |
|------|-----|--------------|
| `admin` | Platform operator | All endpoints; data source management; AI audit console; user creation |
| `operator` | Internal team member | Trigger workflows; view reports; access HIL queue |
| `end_user` | Regular user | Own portfolios/watchlist; view own briefs; Q&A; alerts |

All routes for data-source management, system ops, evaluation, and the AI audit console
require `role=admin`. The HIL queue accepts `admin` or `operator`.

### Creating Additional Users

There is currently no self-service signup UI. Additional users are created either:

1. **Via the seed script** — add more entries to `scripts/seed.py` and re-run.
2. **Via direct database insert** — connect to PostgreSQL and insert a `user` row with a
   bcrypt-hashed password:

```python
import bcrypt, uuid
password_hash = bcrypt.hashpw(b"UserPassword!", bcrypt.gensalt(rounds=12)).decode()
# INSERT INTO "user" (user_id, tenant_id, email, password_hash, role)
# VALUES (gen_random_uuid(), '<tenant_id>', 'user@example.com', '<hash>', 'end_user');
```

3. **Via a future admin API** — an admin-creates-user endpoint is planned but not yet
   implemented in the current codebase.

> **Rate limits:** Login is capped at 10 requests/minute per IP. Refresh is capped at
> 30/minute. Both are enforced by SlowAPI.

---

## External Data Sources

### Source Architecture

External providers are not hardcoded. They are stored as `SourceConfig` rows in the
database and routed dynamically via the **Market Registry**. This means you can add,
enable, disable, or swap providers at runtime without redeploying.

**Credentials are never stored in the database.** The `credentials_ref` field holds a
pointer of the form `env:VAR_NAME` or `vault:SECRET_PATH`:

```
env:FINNHUB_API_KEY      → reads os.environ["FINNHUB_API_KEY"] at runtime
vault:secret/finnhub     → HashiCorp Vault lookup (stub implementation; not yet live)
```

**Interface types** classify what kind of data a source provides:

| Type | Data |
|------|------|
| `NewsProvider` | Geopolitical events, news articles |
| `PriceProvider` | Stock prices, market data |
| `FundamentalsProvider` | Balance sheets, earnings |
| `FilingsProvider` | SEC filings |
| `MacroProvider` | Macro indicators (rates, GDP) |
| `SocialProvider` | Twitter/X, social sentiment (disabled by default) |

---

### GDELT (Geopolitical Event Database)

**What it provides:** Global news events with geolocation, tone, and scale metrics dating
back to 1979. The primary source for historical event seeding.

**Credentials:** None required — GDELT is a free public API.

**Endpoints used:**
- GDELT v2 (April 2015+): `http://data.gdeltproject.org/gdeltv2/masterfilelist.txt`
- GDELT v1 (1979–2013): `http://data.gdeltproject.org/events/index.csv`

**Configuration in `.env`:**

```bash
SEEDING_PROVIDER=gdelt
GDELT_START_DATE=1979-01-01    # how far back to seed
SEEDING_BATCH_SIZE=500         # events per batch
EMBEDDING_CONCURRENCY=5        # parallel OpenAI embedding calls
```

**Admin source record (only needed if you want DB tracking):**

```json
POST /api/v1/admin/sources
{
  "display_name": "GDELT v2",
  "interface_type": "NewsProvider",
  "credentials_ref": "env:GDELT_PLACEHOLDER",
  "config": {},
  "cost_tier": "free",
  "priority": 1
}
```

**What breaks if absent:** Cold-start seeding produces no historical events. Workflows run
but have no event context to analyze.

**Free tier:** Fully free, no account required.

---

### ACLED (Armed Conflict Location & Event Data)

**What it provides:** Armed conflict, protest, and political violence events globally.
Higher signal-to-noise than GDELT for conflict-specific analysis.

**Credentials:** Free account at **https://acleddata.com/register/**

**Configuration:**

```bash
# .env
ACLED_API_KEY=your_key_here
SEEDING_PROVIDER=acled    # switch from gdelt if preferred
```

**Admin source record:**

```json
POST /api/v1/admin/sources
{
  "display_name": "ACLED Conflict Events",
  "interface_type": "NewsProvider",
  "credentials_ref": "env:ACLED_API_KEY",
  "config": {},
  "cost_tier": "low",
  "priority": 2
}
```

Then enable it:

```json
PATCH /api/v1/admin/sources/{source_id}/enable
{ "enabled": true }
```

**Free tier:** ~1,000 API requests/month on the free plan. For large seeding runs, request
academic access or a paid plan.

**What breaks if absent:** Only affects seeding when `SEEDING_PROVIDER=acled`. GDELT
remains the default fallback.

---

### Finnhub

**What it provides:** Real-time and delayed stock prices, company fundamentals, earnings
calendars, and news sentiment.

**Credentials:** Free account at **https://finnhub.io**

**Configuration:**

```bash
FINNHUB_API_KEY=your_key_here
```

**Admin source record:**

```json
POST /api/v1/admin/sources
{
  "display_name": "Finnhub",
  "interface_type": "PriceProvider",
  "credentials_ref": "env:FINNHUB_API_KEY",
  "config": {},
  "cost_tier": "low",
  "priority": 1
}
```

**Free tier limits:** 60 API calls/minute. The ingestion rate limiter respects this via a
per-source sliding window. If you hit limits, reduce `EMBEDDING_CONCURRENCY` and add
deliberate delays in the price-fetch path.

**What breaks if absent:** Live price data unavailable; company detail price charts show
no data; screener scores that depend on price momentum will be empty.

---

### FMP (Financial Modeling Prep)

**What it provides:** Company fundamentals (income statements, balance sheets), SEC filing
metadata, earnings calendar, and extended historical prices.

**Credentials:** Account at **https://financialmodelingprep.com** (free tier available)

**Configuration:**

```bash
FMP_API_KEY=your_key_here
```

**Admin source record:**

```json
POST /api/v1/admin/sources
{
  "display_name": "Financial Modeling Prep",
  "interface_type": "FundamentalsProvider",
  "credentials_ref": "env:FMP_API_KEY",
  "config": {},
  "cost_tier": "low",
  "priority": 1
}
```

**Free tier limits:** 250 API calls/day on the free plan. Fundamentals are cached for 24 h
(`FUNDAMENTALS_TTL_S=86400`) so repeated requests don't consume quota.

**What breaks if absent:** Company fundamentals panel (PE, EPS, revenue, D/E) shows no
data; earnings brief workflows have incomplete company state.

---

### FRED (Federal Reserve Economic Data)

**What it provides:** US macroeconomic indicators — inflation (CPI), unemployment, GDP
growth, federal funds rate, yield curves.

**Credentials:** Free account at **https://fred.stlouisfed.org/docs/api/fred/**

**Configuration:**

```bash
FRED_API_KEY=your_key_here
```

**Admin source record:**

```json
POST /api/v1/admin/sources
{
  "display_name": "FRED Macro",
  "interface_type": "MacroProvider",
  "credentials_ref": "env:FRED_API_KEY",
  "config": {},
  "cost_tier": "free",
  "priority": 1
}
```

**Free tier:** 120 requests/minute; effectively unlimited for typical usage.
Macro data is cached for 24 h (`MACRO_TTL_S=86400`).

**What breaks if absent:** Earnings brief and on-demand analysis workflows skip the
`fetch_macro_context` node gracefully, but macro-sensitive recommendations will be
less accurate.

---

### SEC EDGAR

**What it provides:** Full-text public company filings — 10-K (annual), 10-Q (quarterly),
8-K (material events).

**Credentials:** No API key required for the public EDGAR full-text API.

**Admin source record:**

```json
POST /api/v1/admin/sources
{
  "display_name": "SEC EDGAR",
  "interface_type": "FilingsProvider",
  "credentials_ref": "env:EDGAR_PLACEHOLDER",
  "config": { "user_agent": "stokai admin@yourdomain.com" },
  "cost_tier": "free",
  "priority": 1
}
```

> **Important:** EDGAR requires a valid `User-Agent` header identifying your application
> and contact email. Set it in the `config` JSON field. Requests without it will be blocked.

**What breaks if absent:** Filings-based analysis (10-K risk factor extraction) is
unavailable.

---

### SendGrid (Email Delivery)

**What it provides:** Transactional email delivery for morning briefs and watchlist scan
alerts.

**Credentials:** Account at **https://sendgrid.com** (free tier: 100 emails/day)

**Configuration:**

```bash
SENDGRID_API_KEY=SG.your_key_here
SENDGRID_FROM_EMAIL=noreply@yourdomain.com    # must be verified in SendGrid
SENDGRID_MORNING_BRIEF_TEMPLATE_ID=d-xxxxx   # dynamic template ID from SendGrid dashboard
```

**SendGrid setup checklist:**
1. Create a SendGrid account and verify your sender domain or email address.
2. Create a Dynamic Template in the SendGrid dashboard. Note the template ID (`d-xxxxx`).
3. Set `SENDGRID_MORNING_BRIEF_TEMPLATE_ID` to that template ID.
4. The template receives these variables: `user_name`, `brief_html`, `brief_date`,
   `portfolio_count`, `event_count`.

**What breaks if absent:** Morning briefs and watchlist scans are still generated and
stored in the database — users can read them in the Briefs UI. Only the email delivery
step is skipped.

---

### Configuring a Source End-to-End

Here is the full workflow to add any new provider:

```bash
# Step 1: Add the API key to .env
echo "MYPROVIDER_API_KEY=sk-abc123" >> .env

# Step 2: Restart the api container so it picks up the new env var
docker compose restart api

# Step 3: Create the source record via the admin API
curl -X POST http://localhost:8000/api/v1/admin/sources \
  -H "Authorization: Bearer <admin-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "display_name": "My Provider",
    "interface_type": "PriceProvider",
    "credentials_ref": "env:MYPROVIDER_API_KEY",
    "config": {},
    "cost_tier": "low",
    "priority": 1
  }'
# Note the returned source_id

# Step 4: Enable the source (triggers immediate registry refresh)
curl -X PATCH http://localhost:8000/api/v1/admin/sources/<source_id>/enable \
  -H "Authorization: Bearer <admin-token>" \
  -H "Content-Type: application/json" \
  -d '{"enabled": true}'

# Step 5: Bind the source to a market
curl -X PUT http://localhost:8000/api/v1/admin/bindings \
  -H "Authorization: Bearer <admin-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "market_id": "<market-uuid>",
    "interface_type": "PriceProvider",
    "source_id": "<source_id>",
    "role": "primary"
  }'
```

The registry refreshes synchronously on enable and binding changes — all subsequent
requests use the new routing within milliseconds.

### Market-Source Bindings

Bindings tell the Market Registry which provider to call for a given market and data type.

```
market_id (e.g. US Equities UUID)
  + interface_type (PriceProvider)
  + role (primary | fallback)
  → source_id
```

You can have a primary source and a fallback. If the primary fails or is rate-limited,
the registry falls back automatically. Configure bindings via the Admin → Data Sources →
Bindings tab in the UI, or directly via `PUT /api/v1/admin/bindings`.

---

## Using the Application

The SPA is served by FastAPI at **http://localhost:8000** after running `make up`.
The Swagger API docs are at **http://localhost:8000/docs**.

### Onboarding Flow

New users who have never completed onboarding are redirected here automatically before
they can access the main app.

**Step 1 — Choose a Scoring Profile**

Three pre-built profiles are offered:

| Profile | Focus |
|---------|-------|
| Value Investor | PE ratio, book value, dividend yield |
| Growth Hunter | Revenue growth, EPS momentum |
| Macro Aware | Sensitivity to interest rates, currency exposure |

Select one and click Next. The selection is saved via `POST /api/v1/onboarding/profile`.

**Step 2 — Add Holdings**

Upload a CSV of your portfolio or add positions manually (ticker, shares, optional cost
basis). You can click "Skip for now" to proceed without holdings — you can add them later
from the Portfolio page.

**Step 3 — Confirmation**

Click "Go to Map" to enter the main application.

---

### Intelligence Map

The home screen (`/map`) is an interactive globe powered by MapLibre GL.

**What you see:**
- Geopolitical events rendered as pulsing circles on their geolocated coordinates.
- Clusters (powered by Supercluster) aggregate nearby events — the number inside a cluster
  shows the count.
- Events are color-coded by severity (intensity 1–5 mapped to green→amber→red).

**Interacting with events:**

| Action | Result |
|--------|--------|
| Click a cluster | Zooms in and expands to individual events |
| Click an event marker | Opens Level 1 Popup |
| Click "More detail" in popup | Opens Level 2 Side Panel |
| Click "Why?" in side panel | Opens Audit Trail (prompt SHA + reasoning chain) |
| Click "Deep Dive" | Triggers Mode B Event Deep Dive workflow; opens Level 3 panel when ready |

**Progressive Disclosure levels:**

```
Level 1 — Popup (< 300 ms, cached data)
  Event title, category, date, one-line summary, affected tickers

Level 2 — Side Panel (1–3 s, LLM pre-computed)
  Sparkline price charts per affected company
  Top 5 historical analogies with dates and outcomes
  AI rationale paragraph

Level 3 — Deep Dive (90–180 s, live Mode B workflow)
  Full narrative analysis
  Portfolio-level recommendation
  Scenario tree
  Confidence score
```

**Deep-link navigation:** Append `?event=<event_id>&lat=<lat>&lon=<lon>` to fly the map
directly to an event and open its popup. Useful for sharing specific events.

**Real-time updates:** Event markers appear via WebSocket as Mode A processes new events.
No page refresh needed.

---

### Company Detail

Navigate to a company either by clicking an event's affected ticker in the side panel, or
by selecting a row in the Screener.

The Company Detail page is organized into panels:

| Panel | Contents |
|-------|----------|
| **Score Breakdown** | Current composite score, per-indicator breakdown, peer percentile |
| **Price Chart** | Historical price bars (1d / 1h / 15m intervals, up to 365 days) |
| **Fundamentals** | PE, EPS, revenue, D/E ratio — sourced from FMP |
| **Active Events** | Events currently affecting this company, with exposure score |
| **Analysis History** | Past AI workflow runs with confidence and cost |
| **Track Record** | Historical recommendation accuracy; items with low sample size show an AI disclaimer badge |

**Triggering on-demand analysis:** Click the "Analyze Now" button. This queues a Mode B
On-Demand Analysis workflow (202 response). The page subscribes via WebSocket
(`/ws/workflow/<run_id>`) and shows a progress indicator until the workflow completes.

---

### Screener

The Screener (`/screener`) provides a sortable, filterable table of all tracked companies.

**Filter bar:** Set filters for sector, score range, geo-exposure region, and other
indicator values. Filters are POSTed as a JSON payload (not query params) to support
complex combinations.

**Sorting:** Click any column header to sort. Default: `custom_score DESC`.

**Event filter:** If you arrive from the Intelligence Map via "Show affected companies",
a dismissible banner appears: "Filtered to companies affected by [event name]". Dismiss
it to see all companies.

**CSV export:** Click "Export CSV" to download all current rows as
`stokai-screener-YYYY-MM-DD.csv`. The button is disabled until at least one page has loaded.

**Pagination:** "Load more" appends the next cursor-page (50 rows per page by default).

**Row click:** Opens the Company Detail page for that company.

---

### Briefs

The Briefs page (`/briefs`) lists all AI-generated reports.

**Filter bar:** All | Morning Brief | Watchlist Scan | Earnings Brief | Event Deep Dive

**Brief list item shows:** Headline, brief type, date, confidence score, delivery status.

**Brief detail page** (`/briefs/<id>`):
- Full HTML narrative (safe-rendered)
- Confidence score with sample-size disclaimer if applicable
- Cost in USD
- Feedback widget: thumbs up / thumbs down / submit correction (text edit)

**Feedback** is submitted via `POST /api/v1/briefs/{brief_id}/feedback` and fed back into
the memory system as a `UserFeedback` event.

---

### Q&A Chat

Accessible from the navigation or from within a brief/company detail page.

**Creating a session:** `POST /api/v1/qa/sessions` — returns a `session_id`.

**Asking a question:** Questions are streamed back via Server-Sent Events. The chat panel
displays tokens as they arrive.

**SSE event types:**

| Event | Meaning |
|-------|---------|
| `chunk` | Partial text token — append to display |
| `done` | Final `QAAnswer` JSON with sources, citations |
| `cost_limited` | $0.40 per-session ceiling hit; partial answer included |
| `error` | Internal error — display error message |

**Context:** The Q&A agent has access to the four memory layers (episodic, semantic,
procedural, user feedback) and the tool library (40+ tools). It can retrieve current
prices, recent events, portfolio context, and historical analogies.

---

### Portfolio & Watchlist

**Portfolio page:**
- Create multiple portfolios (one per strategy or account).
- Add positions manually: ticker, number of shares, cost basis (optional).
- Import positions from CSV: click "Import CSV", upload file (max 1 MB).
  Expected columns: `ticker`, `shares`, `cost_basis`.
- Edit portfolio name inline.
- Delete a portfolio (removes all positions).

**Watchlist page:**
- Add any company by ticker or company_id.
- Watchlist is used by the Watchlist Scan workflow to scope daily analysis.
- Remove companies individually.

---

### Alerts & Notifications

**Alert rules** define conditions that trigger a push notification when an event is processed.

**Creating a rule:** Go to Alerts → Rules → New Rule. Specify conditions (e.g., "event
affects any watchlist company with intensity ≥ 4").

**Anti-fatigue settings** (per user, configurable in Settings):

| Setting | Default | Description |
|---------|---------|-------------|
| `daily_push_limit` | 20 | Max alerts per day |
| `dedup_window_minutes` | 60 | Suppress duplicate alerts within this window |
| `quiet_hours_start` / `_end` | user-set | No alerts during quiet hours |

**Email alerts:** Require `SENDGRID_API_KEY` and a valid `SENDGRID_FROM_EMAIL`. Alert
narratives are generated by Claude Sonnet 4.6 as part of the Mode A pipeline.

---

## AI Workflows In Depth

### Mode A — Reactive Pipeline (12 Steps)

Mode A runs synchronously on every incoming geopolitical event. It is deterministic
(no LangGraph, no agents) except for two LLM classification steps.

```
1.  persist_raw_event        Store raw event text and metadata
2.  classify_event           LLM: intensity (1–5), sentiment, region codes
3.  extract_tickers          LLM: affected company tickers
4.  embed_event              OpenAI: 1536-dim vector embedding
5.  compute_exposure_map     Score exposure per tracked company
6.  persist_event_record     Atomic insert: GeoEvent + EventExposure rows
7.  find_historical_analogies pgvector KNN search (k = ANALOGY_K, default 5)
8.  generate_alert_text      LLM: 2-sentence alert narrative
9.  evaluate_alert_rules     Check against user-defined alert rules
10. dispatch_or_log_silent   Send alert or log as silent (no matching rules)
11. enqueue_deep_dive        Queue Mode B Event Deep Dive (if configured)
12. return_pipeline_result   Compile PipelineResult with cost_usd
```

**Cost per event:** ~$0.05 (two Claude Sonnet calls + one OpenAI embedding)
**Latency target:** < 90 seconds end-to-end

All LLM calls inside Mode A use **Claude Sonnet 4.6**. Each step writes its cost to a
`CostRecord` row via the cost accumulator.

### Mode B — LangGraph Workflows

Mode B workflows run as Celery tasks. They use LangGraph with `AsyncPostgresSaver` for
state checkpointing — each node's output is persisted to PostgreSQL so workflows can
resume from any point (e.g., after human-in-the-loop review).

**Shared infrastructure:**
- `BaseWorkflow.execute()` opens a Langfuse trace, runs the graph, closes the trace.
- `WorkflowCostGuard` enforces a per-workflow USD ceiling (checked before dispatch).
- `ExecutionLimiter` enforces a per-agent USD ceiling inside each AgentNode.
- `GRAPH_NODES` constant validates the node sequence at import time.
- All state classes extend `WorkflowState` which carries `workflow_id`, `tenant_id`,
  `user_id`, `trace_id`, `cost_usd`.

**Node types:**
- `DeterministicNode` — pure data fetch/transform, no LLM call.
- `AgentNode` — LLM call via the Claude API; cost tracked; can be limited individually.

---

### Morning Brief Workflow

**Trigger:** Celery beat at each user's `dispatch_time` (default 06:00 UTC, configurable
per user). Can also be triggered on-demand via admin.

**Purpose:** Overnight portfolio intelligence — what happened while you slept and what
it means for your holdings.

**Node sequence:**

```
fetch_portfolio          → user's current positions
fetch_overnight_events   → events that occurred since last brief
relevance_analyst        → [LLM] filter events relevant to portfolio
recompute_scores         → recalculate per-company impact scores
anomaly_detector         → [LLM] identify anomalous price/volume changes
historical_context       → [LLM] per-event historical precedent analysis (parallel)
recommendation_synthesizer → [LLM] portfolio-level recommendation
evaluate_quality         → Tier-1 LLM-as-Judge (confidence threshold)
narrative_writer         → [LLM] generate email-ready HTML narrative
```

**Confidence routing** (after `evaluate_quality`):

| Confidence | Route | Outcome |
|------------|-------|---------|
| ≥ 0.75 | `narrative_writer` → send | Brief emailed; row status = COMPLETED |
| 0.50–0.75 | `hil_queue` | Paused for human review; status = HIL_PENDING |
| < 0.50 | `block_and_log` | Not sent; audit entry only; status = BLOCKED |

**Cost ceiling:** $2.00 per workflow
**Typical latency:** 60–90 seconds
**HIL deadline:** 17:45 UTC (close of US markets)

---

### Event Deep Dive Workflow

**Trigger:** User clicks "Deep Dive" on an event in the map or side panel; or auto-queued
by Mode A step 11 for high-intensity events.

**Purpose:** Thorough multi-company analysis of a specific geopolitical event and its
portfolio implications.

**Node sequence:**

```
fetch_event_full           → full event record + geo context
fetch_market_reaction      → price/index moves at event time
run_exposure_analysts      → parallel fan-out per exposed company
event_deep_dive_agent      → [LLM] synthesize event significance
historical_context_agent   → [LLM] historical analogues
recommendation_synthesizer → [LLM] portfolio-level recommendation
narrative_writer           → [LLM] deep-dive narrative
evaluate_quality           → Tier-1 judge
```

**Output:** `Brief` row + `MemoStore` entry. Accessible via `GET /api/v1/events/{id}/deep-dive`
(202 while pending, 200 when ready) and `GET /api/v1/events/{id}/memo`.

**Cost ceiling:** $5.00 per workflow
**Typical latency:** 90–180 seconds
**Timeout:** 600 seconds

---

### On-Demand Analysis Workflow

**Trigger:** User clicks "Analyze Now" on the Company Detail page.

**Purpose:** Fresh, comprehensive single-company analysis on demand.

**Node sequence:**

```
fetch_company_state        → profile + fundamentals
fetch_active_events        → current/recent events
exposure_analyst           → [LLM] event exposure analysis
historical_context         → [LLM] historical precedents
anomaly_detector           → [LLM] anomaly detection
recommendation_synthesizer → [LLM] recommendation
tier1_eval                 → Tier-1 LLM judge
evaluate_quality           → confidence gate
narrative_writer           → [LLM] final narrative
```

**Response pattern:** API returns `run_id` immediately (202 Accepted). The frontend
subscribes to `/ws/workflow/<run_id>` for live progress events.

**Cost ceiling:** $2.50 per workflow
**Typical latency:** 30–60 seconds
**Timeout:** 300 seconds (5 minutes). If exceeded, status = TIMEOUT.

---

### Earnings Risk Brief Workflow

**Trigger:** On-demand via user action or scheduled before an earnings release.

**Purpose:** Forward-looking risk analysis for a company's upcoming earnings announcement.

**Node sequence:**

```
fetch_company_state           → financials + metadata
fetch_earnings_history        → quarterly earnings records
fetch_macro_context           → rates, GDP, inflation context
fetch_sector_recent_earnings  → peer earnings for comparison
earnings_context              → [LLM] analyze the numbers
historical_context            → [LLM] identify earnings trends
recommendation_synthesizer    → [LLM] recommendation
narrative_writer              → [LLM] final narrative
evaluate_quality              → Tier-1 judge
```

**Cost ceiling:** $3.00 per workflow
**Typical latency:** 120–150 seconds
**HIL deadline:** 17:45 UTC
**Hard timeout:** 600 seconds (`EARNINGS_BRIEF_HARD_TIMEOUT_SECONDS`)

---

### Watchlist Scan Workflow

**Trigger:** Celery beat, daily before market open.

**Purpose:** Morning scan of everything relevant to your watchlist — score changes,
anomalies, upcoming events.

**Node sequence:**

```
fetch_scoped_companies   → user's watchlist companies
fetch_today_events       → events affecting watchlist
fetch_score_changes      → score deltas vs yesterday
filter_relevant_events   → [LLM] filter high-relevance events
detect_anomalies         → [LLM] anomaly detection
fetch_analogies          → historical precedent lookup
run_watchlist_analyst    → [LLM] synthesize watchlist insights
evaluate_quality         → Tier-1 judge
narrative_writer         → [LLM] final narrative
```

**Confidence routing:**

| Confidence | Route | Outcome |
|------------|-------|---------|
| High | `dispatch` | Brief stored + emailed |
| Medium | `hil_enqueue` | HIL queue (deadline 17:45 UTC) |
| Low | `block_and_notify` | Audit entry only |

**Cost ceiling:** $1.00 per workflow (lowest of all workflows)
**Typical latency:** 45–60 seconds

---

### Cost Controls & Budget Hierarchy

Cost enforcement operates at three independent tiers:

```
Tier 1: Per-agent ExecutionLimiter
  Hard cap per individual LLM agent ($1.00–$2.00 depending on agent)
  Raises CostLimitExceeded if agent's cumulative spend exceeds limit

Tier 2: Per-workflow WorkflowCostGuard
  Hard cap per workflow run ($1.00–$5.00 depending on workflow type)
  Checked before dispatch and after each node

Tier 3: Per-user daily UserBudgetEnforcer
  Soft budget enforced at workflow entry
  Configurable via admin; defaults vary per deployment
```

All cost records are written to the `cost_record` table with `workflow_run_id`,
`agent_name`, `model`, `input_tokens`, `output_tokens`, `cost_usd`. The admin
Cost Monitor tab aggregates these monthly.

---

### Human-in-the-Loop (HIL)

When a workflow's confidence score falls in the "medium" range, the workflow pauses and
inserts a record into the `hil_action` table. The workflow state is checkpointed via
LangGraph's `AsyncPostgresSaver` so it can resume exactly where it left off.

**HIL deadline:** 17:45 UTC (configurable via `EARNINGS_BRIEF_HIL_DEADLINE_TIME`). If
no action is taken by the deadline, the workflow is automatically blocked.

**Reviewer actions:**

| Action | Effect |
|--------|--------|
| `approve` | Resumes workflow at `narrative_writer` node |
| `edit_approve` | Replaces the recommendation text, then resumes |
| `reject` | Blocks the brief; audit entry only |
| `reject_with_feedback` | Blocks + stores feedback text for memory training |

Reviewers access the HIL queue at **Admin → HIL Queue** in the UI, or via
`GET /api/v1/admin/hil`.

---

## Admin Console

The Admin Console is accessible only to users with `role=admin`.

### Data Sources Tab

**All Sources sub-tab:** Lists every `SourceConfig` with live health stats:
- API calls today
- Error count today
- Rate-limit usage percentage
- Estimated cost today

Toggle a source on/off with the enable switch. The registry refreshes immediately.

**Social Sources sub-tab:** Twitter/X and other social providers. All social sources
start disabled by default (Architecture Decision D8). Enable individually with caution —
social data has higher cost and noise.

**Bindings sub-tab:** Visual table of `market_id × interface_type → source_id (role)`
mappings. Use the form to add or remove bindings. Changes are instant.

### System Ops Tab

Five sub-tabs:

**Ingestion Jobs** — Lists all registered cold-start and scheduled data-fetch jobs with
last-run time, next-run time, status, and error count. "Trigger" button manually fires
a job.

**Cost Monitor** — Monthly AI spend breakdown by service (Anthropic, OpenAI) and by
workflow type. "Update Budget Threshold" sets the monthly ceiling that triggers an email
to `ADMIN_ALERT_EMAIL`.

**Company Universe** — Searchable list of all companies indexed in the database.
"Track" / "Untrack" controls whether a company is included in exposure mapping and
scoring. Paginated (50 per page, 200 max).

**Cache Inspection** — Redis cache statistics: memory used, hit rate, key count per
data type. "Force Refresh" button invalidates a specific data type (optionally scoped
to a single company).

**Feature Flags** — Runtime toggles stored in the `feature_flag` table. Toggling takes
effect immediately without restart. Key flags:

| Flag | Default | Effect |
|------|---------|--------|
| `TWITTER_ENABLED` | `false` | Enable Twitter/X social source |

### AI Audit Console

Four tabs — admin-only (`/admin/ai-audit`):

**Decision Log tab** — Every LLM decision persisted as an `AgentInvocation` row.
Columns: agent name, model, prompt role, confidence, input/output tokens, cost, timestamp.
Filter by date range, agent, and confidence band. Click a row to open `DecisionDetailDrawer`
which shows the full prompt, response, and Langfuse trace link.

**Prompt History tab** — All `PromptPublication` rows showing which git SHA is live for
each of the 15 prompt roles. Columns: role, SHA, environment (staging / canary /
production), promoted_at, promoted_by. `OverrideModal` lets admins force-set a
specific SHA. `RollbackConfirmModal` confirms rollbacks.

**Calibration tab** — `CalibrationDashboard` showing:
- Rolling Pearson correlation between AI confidence scores and actual next-day price
  direction (`CALIBRATION_CORR_THRESHOLD` threshold, default 0.3).
- Pass / Fail indicator (requires minimum `CALIBRATION_MIN_SAMPLE=30` recommendations).
- Tier-3 calibration review log with action taken and notes.

**Workflow History tab** — Every `WorkflowRun` row. Columns: workflow type, status,
user, cost_usd, duration, created_at. Click a row to open `WorkflowDetailDrawer`
showing the full node execution trace and each agent's cost.

### HIL Queue

Accessible to `admin` and `operator` roles at `/admin/hil`.

Lists pending HIL items sorted by `scheduled_send_at` ascending (most urgent first).
Badge on the navigation shows the count, polled every 30 seconds via
`GET /api/v1/admin/hil/count`.

Clicking an item opens the review pane showing the draft brief, the confidence score
that triggered HIL, and action buttons. See [Human-in-the-Loop](#human-in-the-loop-hil)
for action descriptions.

---

## Prompt Management

Prompts are Markdown files in the `prompts/` directory. At runtime, the
`PromptVersionResolver` first checks Langfuse for a promoted version; if none exists
it falls back to the file on disk. This allows prompt updates in production without
redeploying.

**Promotion pipeline:** `Draft (file) → Staging (Langfuse label) → Canary → Production`

**CLI commands:**

```bash
# Check current production labels for all 15 prompts
python -m src.cli.prompts_cli status

# Promote a specific git SHA to production for one role
python -m src.cli.prompts_cli promote --role exposure_analyst --sha abc1234

# Roll back to a prior version
python -m src.cli.prompts_cli rollback --role exposure_analyst
```

**Canary traffic:** `CANARY_TRAFFIC_PCT` (default 10) routes that percentage of LLM
calls to the canary prompt version. Monitor canary metrics at
`GET /api/v1/admin/prompts/{role_id}/canary-metrics` or in the AI Audit Console →
Prompt History tab.

**15 canonical prompt roles:**

`exposure_analyst` · `historical_context` · `anomaly_detector` · `recommendation_synthesizer` ·
`narrative_writer` · `morning_brief_analyst` · `watchlist_analyst` · `earnings_analyst` ·
`qa_analyst` · `recommendation_judge` · `factuality_judge` · `calibration_judge` ·
`event_classifier` · `ticker_extractor` · `sentiment_analyzer`

---

## Database Migrations

Migrations are managed with Alembic. Run after any deployment that includes schema changes.

```bash
# Apply all pending migrations
make migrate
# or
docker compose exec api alembic upgrade head

# Create a new migration after changing SQLAlchemy models
docker compose exec api alembic revision --autogenerate -m "add_column_x_to_table_y"

# Roll back one step
docker compose exec api alembic downgrade -1

# Show current migration version
docker compose exec api alembic current
```

---

## Seeding Historical Data

**Admin account seed (required on first run):**

```bash
make shell-api
python scripts/seed.py
```

Uses `SEED_ADMIN_EMAIL`, `SEED_ADMIN_PASSWORD`, `SEED_TENANT_ID` from `.env`.

**Historical event seeding (optional but recommended):**

```bash
# Configure in .env:
#   SEEDING_PROVIDER=gdelt       (or acled)
#   GDELT_START_DATE=2020-01-01  (start narrower for a quick first run)
#   SEEDING_BATCH_SIZE=500
#   EMBEDDING_CONCURRENCY=5

make shell-api
python scripts/seed_events.py
```

This fetches events in batches, embeds them with OpenAI, and builds the HNSW vector index
for the analogy search. A full GDELT run from 1979 can take several hours. Start with
a 2–3 year window to verify the pipeline, then extend.

**Checkpoint resume:** The seeding orchestrator persists progress to
`seeding_checkpoint`. If interrupted, re-running picks up from the last committed batch.

---

## Observability

**Langfuse** is bundled in the Docker stack at **http://localhost:3000**.

| Signal | What's captured |
|--------|----------------|
| Traces | Every Mode A pipeline run and Mode B workflow with full node timings |
| Spans | Per-agent LLM call with model, tokens, latency, cost |
| Prompt versions | Each SHA promoted to production with its evaluation scores |
| Evaluations | Tier-1 LLM-as-Judge scores attached to every generation |
| Cost tracking | Per-trace token spend and USD cost |

Log in with the credentials set in `LANGFUSE_DB_*` and the generated
`LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY`.

**Application logs** are structured JSON. Control level with `LOG_LEVEL` (default `INFO`).

```bash
make logs                           # all services
docker compose logs -f api          # API process only
docker compose logs -f worker       # Celery worker
docker compose logs -f beat         # Celery beat scheduler
```

**Health check** (no auth required):

```bash
curl http://localhost:8000/health
```

---

## Testing

```bash
# Unit tests (no external services required)
make test
pytest tests/ -v --ignore=tests/integration

# Integration tests (requires postgres + redis running)
make test-integration
pytest tests/integration/ -v -m integration

# Check for forbidden Azure SDK imports
make scan-azure

# Frontend component tests
npm test
npm run test:watch   # watch mode

# Load tests (Locust or similar — run separately)
# tests/load/ contains load test scripts
```

---

## Service URLs & Ports

| Service | URL | Notes |
|---------|-----|-------|
| React SPA | http://localhost:8000 | Main application |
| FastAPI REST | http://localhost:8000/api/v1 | API root |
| Swagger UI | http://localhost:8000/docs | Interactive API docs |
| ReDoc | http://localhost:8000/redoc | Alternative API docs |
| Health check | http://localhost:8000/health | No auth required |
| Langfuse UI | http://localhost:3000 | AI traces, prompt versions |
| PostgreSQL | localhost:5432 | Direct DB (local dev only) |
| Redis | localhost:6379 | Cache / broker (local dev only) |

---

## Environment Variables Reference

All variables are documented in `.env.example`. Here is the grouped reference:

### Core Application

| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| `ENVIRONMENT` | `local` | No | local / test / staging / production |
| `DEBUG` | `false` | No | Enable debug logging |
| `LOG_LEVEL` | `INFO` | No | DEBUG / INFO / WARNING / ERROR |
| `PORT` | `8000` | No | Internal API port |

### Database

| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| `DATABASE_URL` | — | **Yes** | asyncpg DSN, e.g. `postgresql+asyncpg://user:pass@host:5432/db` |
| `POSTGRES_USER` | — | Yes (Docker) | PostgreSQL username |
| `POSTGRES_PASSWORD` | — | **Yes** | PostgreSQL password |
| `POSTGRES_DB` | — | Yes (Docker) | Database name |
| `DATABASE_POOL_SIZE` | `10` | No | SQLAlchemy connection pool size |
| `DATABASE_MAX_OVERFLOW` | `5` | No | Extra connections above pool_size |

### Redis & Celery

| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| `REDIS_URL` | — | **Yes** | Redis DSN, e.g. `redis://redis:6379/0` |
| `CELERY_BROKER_URL` | `REDIS_URL` | No | Defaults to REDIS_URL |
| `CELERY_RESULT_BACKEND` | `REDIS_URL` | No | Defaults to REDIS_URL |

### AI Providers

| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| `ANTHROPIC_API_KEY` | — | **Yes** | Claude Sonnet 4.6 + Opus |
| `OPENAI_API_KEY` | — | **Yes** | text-embedding-3-small |
| `AGENTS_DIR` | `agents` | No | Path to agent YAML definitions |
| `PROMPTS_DIR` | `prompts` | No | Path to prompt templates |
| `LANGFUSE_PROMPTS_ENABLED` | `true` | No | Publish prompts to Langfuse on deploy |
| `CANARY_TRAFFIC_PCT` | `10` | No | Canary prompt traffic percentage (0–100) |

### Langfuse Observability

| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| `LANGFUSE_SECRET_KEY` | — | **Yes** | Langfuse server secret |
| `LANGFUSE_PUBLIC_KEY` | — | **Yes** | Langfuse SDK public key |
| `LANGFUSE_HOST` | `http://langfuse-server:3000` | No | Self-hosted Langfuse URL |
| `LANGFUSE_DB_USER` | `langfuse` | Yes (Docker) | Langfuse DB username |
| `LANGFUSE_DB_PASSWORD` | — | **Yes** | Langfuse DB password |
| `LANGFUSE_DB_NAME` | `langfuse` | Yes (Docker) | Langfuse DB name |

### JWT Authentication

| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| `JWT_SECRET_KEY` | — | **Yes** | Signs access tokens (min 32 chars) |
| `JWT_REFRESH_SECRET_KEY` | — | **Yes** | Signs refresh tokens (different from above) |
| `JWT_ALGORITHM` | `HS256` | No | Signing algorithm |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | `15` | No | Access token TTL in minutes |
| `JWT_REFRESH_TOKEN_EXPIRE_DAYS` | `7` | No | Refresh token TTL in days |
| `BCRYPT_ROUNDS` | `12` | No | Password hashing cost factor |

### External Data Sources

| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| `FINNHUB_API_KEY` | `""` | No | Live stock prices |
| `FMP_API_KEY` | `""` | No | Fundamentals, earnings |
| `FRED_API_KEY` | `""` | No | Macro indicators |
| `ACLED_API_KEY` | `""` | No (required if SEEDING_PROVIDER=acled) | Conflict events |

### Email

| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| `SENDGRID_API_KEY` | `""` | No | Alerts disabled if blank |
| `SENDGRID_FROM_EMAIL` | `""` | No | Verified sender address |
| `SENDGRID_MORNING_BRIEF_TEMPLATE_ID` | `""` | No | SendGrid dynamic template ID |
| `MORNING_BRIEF_DEFAULT_SEND_TIME` | `06:00` | No | Default dispatch time (UTC, HH:MM) |

### Seeding & Cold Start

| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| `SEED_ADMIN_EMAIL` | — | First run | Initial admin email |
| `SEED_ADMIN_PASSWORD` | — | First run | Initial admin password (min 12 chars) |
| `SEED_TENANT_ID` | — | First run | Tenant UUID for the seeded admin |
| `SEEDING_PROVIDER` | `gdelt` | No | gdelt or acled |
| `GDELT_START_DATE` | `1979-01-01` | No | Historical range start |
| `SEEDING_BATCH_SIZE` | `500` | No | Events per seeding batch |
| `EMBEDDING_CONCURRENCY` | `5` | No | Parallel OpenAI embedding calls |

### Workflow Tuning

| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| `ANALOGY_K` | `5` | No | Historical analogies per event (1–50) |
| `EARNINGS_BRIEF_COST_CEILING_USD` | `1.50` | No | Per-earnings-brief cost cap |
| `EARNINGS_BRIEF_HIL_DEADLINE_TIME` | `17:45` | No | HIL review deadline (UTC) |
| `EARNINGS_BRIEF_HARD_TIMEOUT_SECONDS` | `600` | No | Workflow max wall time |

### AI Memory

| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| `EVIDENCE_GATE_MIN_COUNT` | `3` | No | Evidence observations before fact commitment |
| `SEMANTIC_DECAY_MONTHS` | `6` | No | Months before unconfirmed facts decay |

### Compliance & Calibration

| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| `COMPLIANCE_CHECK_LOOKBACK_DAYS` | `90` | No | Rolling window for episodic check |
| `CALIBRATION_CORR_THRESHOLD` | `0.3` | No | Min Pearson CORR for Healthy status |
| `CALIBRATION_MIN_SAMPLE` | `30` | No | Min recommendations before threshold enforced |
| `DISCLAIMER_SAMPLE_SIZE_THRESHOLD` | `5` | No | Inject disclaimer when sample_size < this |
| `ADMIN_ALERT_EMAIL` | `""` | No | Budget alert recipient |

### Prompt SHA Fallback

| Variable | Default | Description |
|----------|---------|-------------|
| `PROMPT_SHA_FALLBACK` | `""` | Git SHA baked in at CI build time for containers without .git |

---

## Makefile Cheat-Sheet

```
make up               Build images and start all services (detached)
make down             Stop and remove containers
make logs             Stream logs from all services
make ps               Show container status
make migrate          Run Alembic migrations inside the api container
make shell-api        Open bash inside the api container
make test             Run unit tests (excludes integration)
make test-integration Run integration tests only
make scan-azure       Check for forbidden Azure SDK imports
make help             Print this list
```

---

## Backend Module Reference

All modules live under `src/`. Every module uses constructor-based dependency injection
and reads configuration exclusively from `src/config/settings.py` (pydantic `BaseSettings`).
No module reads `os.environ` directly.

---

### `admin` — Administrative Operations

Manages data source configuration, runtime health counters, monthly budget tracking, feature
flags, and cache management.

Key sub-packages: `data_sources/`, `health/`, `system/`, `tasks/`.

| Configurable | Default | Notes |
|---|---|---|
| `ADMIN_ALERT_EMAIL` | `""` | Recipient for budget threshold alerts; empty = skip |
| Feature flags | DB-driven | Stored in `feature_flag` table; toggled at runtime without restart |

---

### `ai` — AI Orchestration Hub

Owns everything AI-related: agent YAML registry, 16 tool families, five LangGraph workflows,
four-layer memory system, prompt management pipeline, evaluation harness, and Langfuse
observability integration.

Key sub-packages: `registry/`, `tools/`, `workflows/`, `memory/`, `prompts/`, `evaluation/`,
`guards/`, `qa/`, `embedding/`, `observability/`, `cost/`.

| Configurable | Default | Notes |
|---|---|---|
| `AGENTS_DIR` | `"agents"` | Path to agent YAML definitions |
| `PROMPTS_DIR` | `"prompts"` | Path to prompt templates |
| `ANTHROPIC_API_KEY` | — | Required; Claude Sonnet 4.6 / Opus |
| `OPENAI_API_KEY` | — | Required; `text-embedding-3-small` |
| `LANGFUSE_PROMPTS_ENABLED` | `True` | Publish prompt versions to Langfuse on deploy |
| `CANARY_TRAFFIC_PCT` | `10` | Canary prompt traffic percentage (0–100) |
| `EVIDENCE_GATE_MIN_COUNT` | `3` | Min evidence before semantic fact commitment |
| `SEMANTIC_DECAY_MONTHS` | `6` | Months before unconfirmed semantic facts decay |

---

### `alerts` — Alert Rules & Dispatch

Evaluates pipeline events against user-defined rules, applies anti-fatigue filters,
enforces budget ceilings, generates LLM-written alert narratives, and delivers via SendGrid.

| Configurable | Default | Notes |
|---|---|---|
| `SENDGRID_API_KEY` | `""` | Email delivery; alerts disabled when blank |
| `SENDGRID_FROM_EMAIL` | `""` | Sender address |
| `_DEFAULT_DAILY_PUSH_LIMIT` | `20` | Max push alerts per user per day |
| `_DEFAULT_DEDUP_WINDOW_MINUTES` | `60` | Same-event dedup window |

---

### `api` — HTTP Transport Layer

FastAPI app factory: wires all domain routers, JWT middleware, rate limiting (slowapi),
and disclaimer injection middleware. Exposes REST + WebSocket.

| Configurable | Default | Notes |
|---|---|---|
| `JWT_SECRET_KEY` | — | Required |
| `JWT_REFRESH_SECRET_KEY` | — | Required |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | `15` | Access token TTL |
| `JWT_REFRESH_TOKEN_EXPIRE_DAYS` | `7` | Refresh token TTL |
| `BCRYPT_ROUNDS` | `12` | Password hashing cost |
| `DISCLAIMER_SAMPLE_SIZE_THRESHOLD` | `5` | Inject disclaimer when sample_size < this |

---

### `briefs` — Brief Content Management

Read/filter/feedback service for morning briefs and earnings risk briefs.

| Configurable | Default | Notes |
|---|---|---|
| `MORNING_BRIEF_DEFAULT_SEND_TIME` | `"06:00"` | Default dispatch time (UTC) |
| `SENDGRID_MORNING_BRIEF_TEMPLATE_ID` | `""` | SendGrid dynamic template ID |
| `EARNINGS_BRIEF_COST_CEILING_USD` | `1.50` | Per-brief cost cap |
| `EARNINGS_BRIEF_HIL_DEADLINE_TIME` | `"17:45"` | HIL review deadline (UTC) |
| `EARNINGS_BRIEF_HARD_TIMEOUT_SECONDS` | `600` | Workflow max wall time |

---

### `cli` — Prompt Operations CLI

Manages prompt labels: inspect, promote, roll back.
Commands: `cmd_status`, `cmd_promote`, `cmd_rollback`.

| Configurable | Default | Notes |
|---|---|---|
| `PROMPTS_ROOT` | `<repo_root>/prompts` | Override by running CLI from repo root |

---

### `compliance` — Audit & Auditability

Hourly Celery beat task checks episodic completeness over a rolling window.

| Configurable | Default | Notes |
|---|---|---|
| `COMPLIANCE_CHECK_LOOKBACK_DAYS` | `90` | Rolling window for episodic coverage check |

---

### `config` — Centralized Settings

Single pydantic `BaseSettings` class. All other modules import from here.
Key file: `config/settings.py`.

---

### `data_providers` — External Event Adapters

Protocol-based adapters for GDELT, ACLED, and other event sources.

| Configurable | Default | Notes |
|---|---|---|
| `SEEDING_PROVIDER` | `"gdelt"` | `"gdelt"` or `"acled"` |
| `GDELT_START_DATE` | `1979-01-01` | Historical range start |
| `ACLED_API_KEY` | `""` | Required when `SEEDING_PROVIDER=acled` |

---

### `db` — Migrations & Seeds

Alembic migration files (41+ revisions) and seed scripts. No application logic.

---

### `events` — Mode A Reactive Pipeline

12-step pipeline: `persist_raw_event` → `classify_event` → `extract_tickers` →
`embed_event` → `compute_exposure_map` → `persist_event_record` →
`find_historical_analogies` → `generate_alert_text` → `evaluate_alert_rules` →
`dispatch_or_log_silent` → `enqueue_deep_dive` → `return_pipeline_result`.

| Configurable | Default | Notes |
|---|---|---|
| `ANALOGY_K` | `5` | Historical analogies per event (1–50) |

---

### `ingestion` — Three-Tier Cache Cascade

Cache-or-fetch: Redis hot → PostgreSQL persistent → external provider.
Manages TTLs, rate limiting, invalidation, and cold-start seeding.

| Configurable | Default | Notes |
|---|---|---|
| `PRICE_BAR_TTL_SECONDS` | `900` | Delayed price data (15 min) |
| `PRICE_BAR_REALTIME_TTL_S` | `5` | Real-time price feed |
| `FUNDAMENTALS_TTL_S` | `86400` | Company fundamentals (24 h) |
| `NEWS_EVENT_TTL_S` | `3600` | News events (1 h) |
| `MACRO_TTL_S` | `86400` | Macro indicators (24 h) |
| `HISTORICAL_PRICE_BAR_TTL_S` | `None` | Immutable; never evicted |
| `SEEDING_BATCH_SIZE` | `500` | Events per cold-start seeding batch |
| `EMBEDDING_CONCURRENCY` | `5` | Parallel OpenAI embedding calls |

---

### `markets` — Source Routing Registry

In-process singleton that maps `(market_id, interface_type, role)` → source.
Supports atomic hot-reload. Entirely DB-driven — change routing via admin API.

---

### `portfolio` — Portfolio & Watchlist

Domain services for portfolio CRUD, position management, watchlist, onboarding,
and CSV import.

---

### `scoring` — Company Scoring Pipeline

Nine-step pipeline: load indicators → parse DSL → evaluate AST → normalize → apply geo
modifier → peer benchmarks → persist → detect changes → emit invalidation.

| Configurable | Notes |
|---|---|
| Indicator DSL expressions | Stored in DB; edited via Indicator Builder UI |
| Normalization strategy | Per-indicator: `min_max` / `percentile` / `z_score` |
| Peer cohort | Per scoring profile in DB |
| Geo modifier weights | Updated by `geo_modifier_worker` Celery task |

---

### `storage` — Repository Layer

Repository pattern over 30+ DB entities. SQLAlchemy 2.0 async.

| Configurable | Default | Notes |
|---|---|---|
| `DATABASE_URL` | — | Required asyncpg DSN |
| `DATABASE_POOL_SIZE` | `10` | Connection pool size |
| `DATABASE_MAX_OVERFLOW` | `5` | Extra connections above pool_size |
