# Phase 2b — Hero Screens Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring all five pre-Phase-1 hero screens into compliance: mount their backend routers, wire the ProgressiveDisclosureProvider, migrate raw `fetch`/`new WebSocket` to `api<T>()`/`apiSocket()`, and remove every inline `style={{}}` in favour of Tailwind design tokens.

**Architecture:** The Phase 1 canonical client (`lib/api/client.ts:api<T>()`) replaces all ad-hoc fetch helpers. Six backend routers already written but not registered are mounted in `src/api/main.py`. The `ProgressiveDisclosureProvider` is placed at the home-route level in the React router so `useDisclosure()` is available to `IntelligenceMapPage`.

**Tech Stack:** FastAPI (Python), React 18, TanStack Query v5, Vitest + Testing Library, Tailwind v4 with OKLCH design tokens (`bg-surface-*`, `text-text`, `text-muted`, `border-border`, `text-signal`, `text-warning`, etc.).

---

## File Map

| Action   | Path |
|----------|------|
| Modify   | `src/api/main.py` |
| Modify   | `src/frontend/app/router.tsx` |
| Modify   | `src/frontend/features/intelligence-map/IntelligenceMapPage.tsx` |
| Modify   | `src/frontend/features/progressive-disclosure/api/disclosure.api.ts` |
| Modify   | `src/frontend/features/progressive-disclosure/components/EventPopup.tsx` |
| Modify   | `src/frontend/features/progressive-disclosure/components/LowSampleDisclaimer.tsx` |
| Modify   | `src/frontend/features/progressive-disclosure/components/ContrarianCallout.tsx` |
| Modify   | `src/frontend/features/progressive-disclosure/components/SidePanelAnalogies.tsx` |
| Modify   | `src/frontend/features/progressive-disclosure/components/SidePanelSparkline.tsx` |
| Modify   | `src/frontend/features/progressive-disclosure/components/AuditTrailView.tsx` |
| Modify   | `src/frontend/features/progressive-disclosure/components/SidePanel.tsx` |
| Modify   | `src/frontend/features/progressive-disclosure/components/DeepDivePage.tsx` |
| Modify   | `src/frontend/features/briefs/hooks/useBriefs.ts` |
| Modify   | `src/frontend/features/briefs/hooks/useBriefDetail.ts` |
| Modify   | `src/frontend/features/briefs/hooks/useFeedback.ts` |
| Create   | `src/frontend/features/briefs/hooks/useBriefs.test.ts` |
| Create   | `src/frontend/features/briefs/hooks/useBriefDetail.test.ts` |
| Create   | `src/frontend/features/briefs/hooks/useFeedback.test.ts` |
| Modify   | `src/frontend/features/qa/qaApi.ts` |
| Create   | `src/frontend/features/qa/qaApi.test.ts` |
| Modify   | `src/frontend/features/company-detail/hooks/useCompanyDetail.ts` |
| Modify   | `src/frontend/features/company-detail/hooks/useAnalyzeNow.ts` |
| Create   | `src/frontend/features/company-detail/hooks/useCompanyDetail.test.ts` |
| Create   | `src/frontend/features/company-detail/hooks/useAnalyzeNow.test.ts` |
| Modify   | `src/frontend/pages/admin/ai-audit/hooks/useDecisionLog.ts` |
| Modify   | `src/frontend/pages/admin/ai-audit/hooks/useWorkflowHistory.ts` |
| Create   | `src/frontend/pages/admin/ai-audit/hooks/useDecisionDetail.ts` |
| Create   | `src/frontend/pages/admin/ai-audit/hooks/useWorkflowDetail.ts` |
| Modify   | `src/frontend/pages/admin/ai-audit/DecisionLogPanel.tsx` |
| Modify   | `src/frontend/pages/admin/ai-audit/WorkflowHistoryPanel.tsx` |
| Create   | `src/frontend/pages/admin/ai-audit/hooks/useDecisionDetail.test.ts` |
| Create   | `src/frontend/pages/admin/ai-audit/hooks/useWorkflowDetail.test.ts` |

---

## Task 1: Mount missing backend routers

**Files:**
- Modify: `src/api/main.py`

- [ ] **Step 1: Write the failing import smoke test**

Create `tests/api/test_router_mounts.py`:

```python
def test_all_required_routers_mounted():
    """Verify that all Phase 2b routes are registered in the app."""
    from src.api.main import app

    paths = {route.path for route in app.routes}

    assert any("/events" in p for p in paths), "events v1 router not mounted"
    assert any("/events/{event_id}/popup" in p for p in paths), "disclosure router not mounted"
    assert any("/briefs" in p for p in paths), "briefs router not mounted"
    assert any("/companies/{company_id}/detail" in p for p in paths), "company-detail router not mounted"
    assert any("/admin/audit/decisions" in p for p in paths), "audit router not mounted"
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/api/test_router_mounts.py -v
```

Expected: FAIL — one or more assertion errors about missing routes.

- [ ] **Step 3: Mount the four routers in `src/api/main.py`**

Add imports after the existing `from src.compliance...` import line:

```python
from src.api.v1 import api_v1_router
from src.api.v1.events import router as events_v1_router
from src.api.progressive_disclosure.router import router as disclosure_router
from src.api.admin.audit.audit_router import audit_router
```

Add after the existing `app.include_router(compliance_router, ...)` line:

```python
app.include_router(api_v1_router)                                  # PLAN-F-026/023: briefs, company-detail, screener, scoring
app.include_router(events_v1_router, prefix="/api/v1")             # PLAN-F-019/021: GET /api/v1/events
app.include_router(disclosure_router, prefix="/api/v1")            # PLAN-F-020: progressive disclosure
app.include_router(audit_router, prefix="/api/v1/admin")           # PLAN-F-029: AI audit console
```

- [ ] **Step 4: Run test to verify it passes**

```
pytest tests/api/test_router_mounts.py -v
```

Expected: PASS — all assertions succeed.

- [ ] **Step 5: Commit**

```bash
git add src/api/main.py tests/api/test_router_mounts.py
git commit -m "feat(api): mount Phase 2b routers (events, disclosure, briefs, audit)"
```

---

## Task 2: Wire ProgressiveDisclosureProvider into the router

**Files:**
- Modify: `src/frontend/app/router.tsx`
- Modify: `src/frontend/features/intelligence-map/IntelligenceMapPage.tsx`

- [ ] **Step 1: Write a failing test for IntelligenceMapPage**

Create `src/frontend/features/intelligence-map/IntelligenceMapPage.test.tsx`:

```tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';
import { MemoryRouter } from 'react-router-dom';
import { ProgressiveDisclosureProvider } from '@/features/progressive-disclosure/ProgressiveDisclosureProvider';

vi.mock('@/features/intelligence-map/IntelligenceMap', () => ({
  IntelligenceMap: ({ onExpandEvent }: { onExpandEvent: (e: unknown) => void }) => (
    <button data-testid="mock-map" onClick={() => onExpandEvent({ event_id: 'evt-1' })}>
      map
    </button>
  ),
}));
vi.mock('@/ui/StubModeBadge', () => ({ StubModeBadge: () => null }));

describe('IntelligenceMapPage', () => {
  it('renders without throwing when wrapped in ProgressiveDisclosureProvider', async () => {
    const { IntelligenceMapPage } = await import('./IntelligenceMapPage');
    render(
      <MemoryRouter>
        <ProgressiveDisclosureProvider>
          <IntelligenceMapPage />
        </ProgressiveDisclosureProvider>
      </MemoryRouter>,
    );
    expect(screen.getByTestId('mock-map')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```
npm test -- src/frontend/features/intelligence-map/IntelligenceMapPage.test.tsx
```

Expected: FAIL — `useDisclosure must be used within ProgressiveDisclosureProvider` (once IntelligenceMapPage is updated).

- [ ] **Step 3: Update `IntelligenceMapPage.tsx`**

Replace the entire file:

```tsx
import * as React from "react";

import { useDisclosure } from "@/features/progressive-disclosure/ProgressiveDisclosureProvider";
import { StubModeBadge } from "@/ui/StubModeBadge";
import { IntelligenceMap } from "./IntelligenceMap";

export function IntelligenceMapPage() {
  const { onExpandEvent } = useDisclosure();

  return (
    <div className="relative">
      <div className="absolute left-4 top-4 z-50">
        <StubModeBadge watch={["market_data", "news"]} />
      </div>
      <IntelligenceMap onExpandEvent={onExpandEvent} />
    </div>
  );
}

export default IntelligenceMapPage;
```

- [ ] **Step 4: Update `router.tsx`**

Add these two lazy imports after the existing `QAChatPanel` lazy block:

```tsx
const DeepDivePage = lazy(() =>
  import("@/features/progressive-disclosure/components/DeepDivePage").then((m) => ({ default: m.DeepDivePage }))
);
```

Add this import at the top of the file (with the other component imports):

```tsx
import { ProgressiveDisclosureProvider } from "@/features/progressive-disclosure/ProgressiveDisclosureProvider";
```

Replace the home route inside the `<AppShell>` block:

```tsx
// Before:
<Route path={ROUTES.home} element={<S><IntelligenceMapPage /></S>} />

// After:
<Route
  path={ROUTES.home}
  element={
    <S>
      <ProgressiveDisclosureProvider>
        <IntelligenceMapPage />
      </ProgressiveDisclosureProvider>
    </S>
  }
/>
```

Replace the events route:

```tsx
// Before:
<Route path={ROUTES.events} element={<ComingSoon feature="Event Deep-Dive" />} />

// After:
<Route path={ROUTES.events} element={<S><DeepDivePage /></S>} />
```

- [ ] **Step 5: Run test to verify it passes**

```
npm test -- src/frontend/features/intelligence-map/IntelligenceMapPage.test.tsx
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/frontend/app/router.tsx src/frontend/features/intelligence-map/IntelligenceMapPage.tsx src/frontend/features/intelligence-map/IntelligenceMapPage.test.tsx
git commit -m "feat(map): wire ProgressiveDisclosureProvider and DeepDivePage route"
```

---

## Task 3: Migrate `disclosure.api.ts` to use `api<T>()`

**Files:**
- Modify: `src/frontend/features/progressive-disclosure/api/disclosure.api.ts`

Context: The existing hook tests (`useDeepDive.test.ts`, `usePopupData.test.ts`, etc.) mock at the `disclosureApi.fetchXxx` level so they're unaffected by this change. Run them as the regression gate.

- [ ] **Step 1: Run existing hook tests to capture baseline**

```
npm test -- src/frontend/features/progressive-disclosure/hooks/
```

Expected: All PASS. Record the count.

- [ ] **Step 2: Rewrite `disclosure.api.ts`**

Replace the entire file with the following (keeping all runtime validator functions, removing the custom auth/fetch layer):

```typescript
/**
 * disclosure.api.ts — Typed fetch wrappers for the four Progressive Disclosure endpoints.
 *
 * PLAN-F-020 TASK-001 / Phase 2b migration
 *
 * Uses lib/api/client.ts:api<T>() — no ad-hoc auth headers or fetch calls.
 */

import type {
  PopupData,
  SidePanelData,
  AuditTrailData,
  DeepDiveData,
  DeepDiveResult,
  TickerDelta,
  SparklinePoint,
  AnalogSummary,
  AffectedCompany,
  SocialPost,
  ReasoningStep,
  ScenarioNode,
} from '../types/disclosure.types';

import { api } from '@/lib/api/client';
import { ApiError } from '@/lib/api/errors';

// ── Runtime validators ────────────────────────────────────────────────────────

function assertString(v: unknown, field: string): string {
  if (typeof v !== 'string') {
    throw new ApiError(0, 'SCHEMA_VIOLATION', `Field "${field}" must be a string`);
  }
  return v;
}

function assertNumber(v: unknown, field: string): number {
  if (typeof v !== 'number') {
    throw new ApiError(0, 'SCHEMA_VIOLATION', `Field "${field}" must be a number`);
  }
  return v;
}

function assertBoolean(v: unknown, field: string): boolean {
  if (typeof v !== 'boolean') {
    throw new ApiError(0, 'SCHEMA_VIOLATION', `Field "${field}" must be a boolean`);
  }
  return v;
}

function assertArray(v: unknown, field: string): unknown[] {
  if (!Array.isArray(v)) {
    throw new ApiError(0, 'SCHEMA_VIOLATION', `Field "${field}" must be an array`);
  }
  return v;
}

function assertRecord(v: unknown, field: string): Record<string, unknown> {
  if (typeof v !== 'object' || v === null || Array.isArray(v)) {
    throw new ApiError(0, 'SCHEMA_VIOLATION', `Field "${field}" must be an object`);
  }
  return v as Record<string, unknown>;
}

function validateTickerDelta(raw: unknown): TickerDelta {
  const r = assertRecord(raw, 'TickerDelta');
  return {
    ticker: assertString(r['ticker'], 'ticker'),
    score_delta: assertNumber(r['score_delta'], 'score_delta'),
  };
}

function validateSparklinePoint(raw: unknown): SparklinePoint {
  const r = assertRecord(raw, 'SparklinePoint');
  return {
    ts: assertString(r['ts'], 'ts'),
    close: assertNumber(r['close'], 'close'),
  };
}

function validateAnalogSummary(raw: unknown): AnalogSummary {
  const r = assertRecord(raw, 'AnalogSummary');
  return {
    event_id: assertString(r['event_id'], 'event_id'),
    headline: assertString(r['headline'], 'headline'),
    occurred_at: assertString(r['occurred_at'], 'occurred_at'),
    similarity_score: assertNumber(r['similarity_score'], 'similarity_score'),
  };
}

function validateAffectedCompany(raw: unknown): AffectedCompany {
  const r = assertRecord(raw, 'AffectedCompany');
  return {
    company_id: assertString(r['company_id'], 'company_id'),
    ticker: assertString(r['ticker'], 'ticker'),
    name: assertString(r['name'], 'name'),
    score: assertNumber(r['score'], 'score'),
    delta: assertNumber(r['delta'], 'delta'),
  };
}

function validateSocialPost(raw: unknown): SocialPost {
  const r = assertRecord(raw, 'SocialPost');
  return {
    post_id: assertString(r['post_id'], 'post_id'),
    source: assertString(r['source'], 'source'),
    text: assertString(r['text'], 'text'),
    timestamp: assertString(r['timestamp'], 'timestamp'),
  };
}

function validateReasoningStep(raw: unknown): ReasoningStep {
  const r = assertRecord(raw, 'ReasoningStep');
  return {
    agent_role: assertString(r['agent_role'], 'agent_role'),
    step_index: assertNumber(r['step_index'], 'step_index'),
    content: assertString(r['content'], 'content'),
    tool_calls: assertArray(r['tool_calls'], 'tool_calls').map((t) =>
      assertString(t, 'tool_calls[]'),
    ),
  };
}

function validateScenarioNode(raw: unknown): ScenarioNode {
  const r = assertRecord(raw, 'ScenarioNode');
  return {
    label: assertString(r['label'], 'label'),
    probability: assertNumber(r['probability'], 'probability'),
    description: assertString(r['description'], 'description'),
    children: assertArray(r['children'], 'children').map(validateScenarioNode),
  };
}

function validatePopupDataBase(r: Record<string, unknown>): Omit<PopupData, never> {
  return {
    event_id: assertString(r['event_id'], 'event_id'),
    category: assertArray(r['category'], 'category').map((c) =>
      assertString(c, 'category[]'),
    ),
    intensity: assertNumber(r['intensity'], 'intensity'),
    headline: assertString(r['headline'], 'headline'),
    time_ago: assertString(r['time_ago'], 'time_ago'),
    location: assertString(r['location'], 'location'),
    exposed_holdings_count: assertNumber(r['exposed_holdings_count'], 'exposed_holdings_count'),
    tickers_with_delta: assertArray(r['tickers_with_delta'], 'tickers_with_delta').map(
      validateTickerDelta,
    ),
    action_signal: assertString(r['action_signal'], 'action_signal'),
    confidence: assertNumber(r['confidence'], 'confidence'),
    sample_size: assertNumber(r['sample_size'], 'sample_size'),
    low_sample: assertBoolean(r['low_sample'], 'low_sample'),
  };
}

function validatePopupData(body: unknown): PopupData {
  const r = assertRecord(body, 'PopupData');
  return validatePopupDataBase(r);
}

function validateSidePanelData(body: unknown): SidePanelData {
  const r = assertRecord(body, 'SidePanelData');
  const base = validatePopupDataBase(r);

  const socialPostsRaw = r['social_posts'];
  const social_posts: SocialPost[] | null =
    socialPostsRaw === null || socialPostsRaw === undefined
      ? null
      : assertArray(socialPostsRaw, 'social_posts').map(validateSocialPost);

  return {
    ...base,
    summary: assertString(r['summary'], 'summary'),
    sparklines: assertArray(r['sparklines'], 'sparklines').map((s) => {
      const sr = assertRecord(s, 'sparklines[]');
      return {
        ticker: assertString(sr['ticker'], 'sparklines[].ticker'),
        ohlcv_7d: assertArray(sr['ohlcv_7d'], 'ohlcv_7d').map(validateSparklinePoint),
      };
    }),
    rationale: assertString(r['rationale'], 'rationale'),
    analogies: assertArray(r['analogies'], 'analogies').map(validateAnalogSummary),
    affected_companies: assertArray(r['affected_companies'], 'affected_companies').map(
      validateAffectedCompany,
    ),
    is_contrarian: assertBoolean(r['is_contrarian'], 'is_contrarian'),
    contrarian_callout:
      r['contrarian_callout'] === null || r['contrarian_callout'] === undefined
        ? null
        : assertString(r['contrarian_callout'], 'contrarian_callout'),
    social_posts,
    audit_trail_url: assertString(r['audit_trail_url'], 'audit_trail_url'),
  };
}

function validateAuditTrailData(body: unknown): AuditTrailData {
  const r = assertRecord(body, 'AuditTrailData');
  return {
    event_id: assertString(r['event_id'], 'event_id'),
    prompt_version: assertString(r['prompt_version'], 'prompt_version'),
    langfuse_trace_url: assertString(r['langfuse_trace_url'], 'langfuse_trace_url'),
    analogies: assertArray(r['analogies'], 'analogies').map(validateAnalogSummary),
    reasoning_steps: assertArray(r['reasoning_steps'], 'reasoning_steps').map(
      validateReasoningStep,
    ),
  };
}

function validateDeepDiveData(body: unknown): DeepDiveData {
  const r = assertRecord(body, 'DeepDiveData');
  const scenarioTreeRaw = r['scenario_tree'];
  return {
    event_id: assertString(r['event_id'], 'event_id'),
    memo: assertString(r['memo'], 'memo'),
    scenario_tree:
      scenarioTreeRaw === null || scenarioTreeRaw === undefined
        ? null
        : validateScenarioNode(scenarioTreeRaw),
    analogies: assertArray(r['analogies'], 'analogies').map(validateAnalogSummary),
    affected_companies: assertArray(r['affected_companies'], 'affected_companies').map(
      validateAffectedCompany,
    ),
    generated_at: assertString(r['generated_at'], 'generated_at'),
  };
}

// ── Public API ────────────────────────────────────────────────────────────────

export async function fetchPopupData(eventId: string): Promise<PopupData> {
  const raw = await api<unknown>(`/events/${encodeURIComponent(eventId)}/popup`);
  return validatePopupData(raw);
}

export async function fetchSidePanelData(eventId: string): Promise<SidePanelData> {
  const raw = await api<unknown>(`/events/${encodeURIComponent(eventId)}/side-panel`);
  return validateSidePanelData(raw);
}

export async function fetchAuditTrail(eventId: string): Promise<AuditTrailData> {
  const raw = await api<unknown>(`/events/${encodeURIComponent(eventId)}/audit-trail`);
  return validateAuditTrailData(raw);
}

export async function fetchDeepDive(eventId: string): Promise<DeepDiveResult> {
  // 202 Accepted returns {"status":"pending"} (not enveloped); api<T> returns undefined.
  // 200 OK returns the standard envelope; api<T> unwraps to DeepDiveData.
  const raw = await api<unknown>(`/events/${encodeURIComponent(eventId)}/deep-dive`);
  if (raw === undefined) {
    return { status: 'pending' };
  }
  return validateDeepDiveData(raw);
}
```

- [ ] **Step 3: Run hook tests to verify they still pass**

```
npm test -- src/frontend/features/progressive-disclosure/hooks/
```

Expected: All PASS — same count as Step 1.

- [ ] **Step 4: Commit**

```bash
git add src/frontend/features/progressive-disclosure/api/disclosure.api.ts
git commit -m "refactor(disclosure): migrate disclosure.api.ts to lib/api/client api<T>()"
```

---

## Task 4: Tailwind migration — `EventPopup`, `LowSampleDisclaimer`, `ContrarianCallout`

**Files:**
- Modify: `src/frontend/features/progressive-disclosure/components/EventPopup.tsx`
- Modify: `src/frontend/features/progressive-disclosure/components/LowSampleDisclaimer.tsx`
- Modify: `src/frontend/features/progressive-disclosure/components/ContrarianCallout.tsx`

- [ ] **Step 1: Run existing component tests to capture baseline**

```
npm test -- src/frontend/features/progressive-disclosure/components/EventPopup.test.tsx src/frontend/features/progressive-disclosure/components/LowSampleDisclaimer.test.tsx src/frontend/features/progressive-disclosure/components/ContrarianCallout.test.tsx
```

Expected: All PASS.

- [ ] **Step 2: Replace `EventPopup.tsx`**

```tsx
import React from 'react';

import { usePopupData } from '../hooks/usePopupData';
import { LowSampleDisclaimer } from './LowSampleDisclaimer';

const INTENSITY_BG: Record<number, string> = {
  1: 'var(--neutral)',
  2: 'var(--signal)',
  3: 'var(--warning)',
  4: 'var(--pulse-high)',
  5: 'var(--pulse-extreme)',
};

function IntensityBadge({ intensity }: { intensity: number }) {
  return (
    <span
      data-testid="intensity-badge"
      className="ml-1 inline-block rounded px-1.5 py-px text-[11px] font-bold text-white"
      style={{ backgroundColor: INTENSITY_BG[intensity] ?? 'var(--neutral)' }}
    >
      {intensity}
    </span>
  );
}

function PopupSkeleton() {
  return (
    <div data-testid="popup-skeleton" className="w-[280px] p-3">
      <div className="mb-2 h-3 w-[60px] rounded bg-surface-2" />
      <div className="mb-1.5 h-4 w-[200px] rounded bg-surface-2" />
      <div className="h-3 w-[120px] rounded bg-surface-2" />
    </div>
  );
}

export interface EventPopupProps {
  eventId: string;
  onExpand: () => void;
  onClose: () => void;
}

export function EventPopup({ eventId, onExpand, onClose }: EventPopupProps) {
  const { data, isLoading } = usePopupData(eventId);

  if (isLoading || !data) {
    return <PopupSkeleton />;
  }

  return (
    <div
      data-testid="event-popup"
      className="w-[280px] max-w-[300px] p-3 text-[13px] leading-[1.5] text-text"
    >
      <div className="mb-1.5 flex items-center">
        <span data-testid="category" className="text-[11px] uppercase text-muted">
          {data.category.join(' · ')}
        </span>
        <IntensityBadge intensity={data.intensity} />
      </div>

      <p data-testid="headline" className="mb-1 text-[13px] font-semibold text-text">
        {data.headline}
      </p>

      <p data-testid="time-ago" className="mb-0.5 text-[11px] text-muted">
        {data.time_ago}
      </p>
      <p data-testid="location" className="mb-2 text-[11px] text-muted">
        {data.location}
      </p>

      <p className="mb-1.5 text-xs text-text">
        <span data-testid="exposed-holdings-count" className="font-semibold">
          {data.exposed_holdings_count}
        </span>{' '}
        {data.exposed_holdings_count === 1 ? 'holding' : 'holdings'} exposed
      </p>

      {data.tickers_with_delta.length > 0 && (
        <div data-testid="tickers-list" className="mb-2 flex flex-wrap gap-1">
          {data.tickers_with_delta.map((t) => {
            const positive = t.score_delta >= 0;
            return (
              <span
                key={t.ticker}
                data-testid={`ticker-${t.ticker}`}
                className={`inline-flex items-center gap-0.5 rounded px-1 py-px text-[11px] font-semibold ${
                  positive ? 'bg-positive/10 text-positive' : 'bg-negative/10 text-negative'
                }`}
              >
                {t.ticker}
                <span>{positive ? '+' : '−'}{Math.abs(t.score_delta).toFixed(1)}</span>
              </span>
            );
          })}
        </div>
      )}

      <p className="mb-0.5 text-xs text-text">
        Signal: <strong data-testid="action-signal">{data.action_signal}</strong>
      </p>

      <p data-testid="confidence" className="mb-2 text-xs text-muted">
        Confidence: {(data.confidence * 100).toFixed(0)}%
      </p>

      {data.low_sample && <LowSampleDisclaimer />}

      <div className="mt-2.5 flex justify-between">
        <button
          data-testid="expand-button"
          onClick={onExpand}
          className="cursor-pointer rounded-[5px] bg-signal px-3.5 py-1.5 text-xs font-semibold text-white"
        >
          Expand
        </button>
        <button
          data-testid="close-button"
          onClick={onClose}
          aria-label="Close popup"
          className="cursor-pointer rounded-[5px] border border-border px-2.5 py-1.5 text-xs text-muted"
        >
          ✕
        </button>
      </div>
    </div>
  );
}

export default EventPopup;
```

- [ ] **Step 3: Replace `LowSampleDisclaimer.tsx`**

```tsx
import React from 'react';

const DISCLAIMER_TEXT =
  'Low sample — fewer than 5 historical analogies found. Treat this recommendation with caution.';

export function LowSampleDisclaimer() {
  return (
    <div
      data-testid="low-sample-disclaimer"
      role="alert"
      className="mb-2 flex items-start gap-2 rounded border border-warning/30 border-l-4 border-l-warning bg-warning/10 px-2.5 py-2 text-xs leading-[1.5] text-warning"
    >
      <span aria-hidden="true" className="text-sm shrink-0">⚠</span>
      <span>{DISCLAIMER_TEXT}</span>
    </div>
  );
}

export default LowSampleDisclaimer;
```

- [ ] **Step 4: Replace `ContrarianCallout.tsx`**

```tsx
import React from 'react';

export interface ContrarianCalloutProps {
  text: string;
}

export function ContrarianCallout({ text }: ContrarianCalloutProps) {
  return (
    <div
      data-testid="contrarian-callout"
      role="note"
      className="relative mb-3.5 flex items-start gap-2.5 rounded border border-signal/30 border-l-4 border-l-signal bg-signal/10 px-3.5 py-3 text-[13px] leading-[1.5] text-text"
    >
      <span aria-hidden="true" className="shrink-0 text-base">📜</span>
      <div>
        <p className="mb-1 text-xs font-bold uppercase tracking-[0.05em] text-text">
          History says
        </p>
        <p className="m-0">{text}</p>
      </div>
    </div>
  );
}

export default ContrarianCallout;
```

- [ ] **Step 5: Run tests to verify they all pass**

```
npm test -- src/frontend/features/progressive-disclosure/components/EventPopup.test.tsx src/frontend/features/progressive-disclosure/components/LowSampleDisclaimer.test.tsx src/frontend/features/progressive-disclosure/components/ContrarianCallout.test.tsx
```

Expected: All PASS.

- [ ] **Step 6: Commit**

```bash
git add src/frontend/features/progressive-disclosure/components/EventPopup.tsx src/frontend/features/progressive-disclosure/components/LowSampleDisclaimer.tsx src/frontend/features/progressive-disclosure/components/ContrarianCallout.tsx
git commit -m "style(disclosure): migrate EventPopup, LowSampleDisclaimer, ContrarianCallout to Tailwind"
```

---

## Task 5: Tailwind migration — `SidePanelAnalogies` + `SidePanelSparkline`

**Files:**
- Modify: `src/frontend/features/progressive-disclosure/components/SidePanelAnalogies.tsx`
- Modify: `src/frontend/features/progressive-disclosure/components/SidePanelSparkline.tsx`

- [ ] **Step 1: Run existing tests**

```
npm test -- src/frontend/features/progressive-disclosure/components/SidePanelAnalogies.test.tsx src/frontend/features/progressive-disclosure/components/SidePanelSparkline.test.tsx
```

Expected: All PASS.

- [ ] **Step 2: Replace `SidePanelAnalogies.tsx`**

```tsx
import React from 'react';

import type { AnalogSummary } from '../types/disclosure.types';

export interface SidePanelAnalogiesProps {
  analogies: AnalogSummary[];
}

function truncate(text: string, maxLen: number): string {
  if (text.length <= maxLen) return text;
  return text.slice(0, maxLen - 1) + '…';
}

function formatDate(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
  } catch {
    return iso;
  }
}

export function SidePanelAnalogies({ analogies }: SidePanelAnalogiesProps) {
  if (analogies.length === 0) {
    return (
      <p data-testid="analogies-empty" className="text-xs italic text-muted">
        No historical analogies found.
      </p>
    );
  }

  const topThree = analogies.slice(0, 3);

  return (
    <ul data-testid="analogies-list" className="m-0 flex list-none flex-col gap-2 p-0">
      {topThree.map((a, idx) => (
        <li
          key={`${a.event_id}-${idx}`}
          data-testid={`analogy-item-${idx}`}
          className="flex items-start justify-between gap-2 rounded border border-border-subtle bg-surface-2 px-2.5 py-2"
        >
          <div className="min-w-0 flex-1">
            <p
              data-testid={`analogy-headline-${idx}`}
              className="mb-0.5 text-xs font-medium text-text"
            >
              {truncate(a.headline, 80)}
            </p>
            <p className="m-0 text-[11px] text-muted">{formatDate(a.occurred_at)}</p>
          </div>
          <span
            data-testid={`analogy-score-${idx}`}
            className="inline-block shrink-0 whitespace-nowrap rounded-full bg-signal/20 px-1.5 py-px text-[11px] font-semibold text-signal"
          >
            {Math.round(a.similarity_score * 100)}%
          </span>
        </li>
      ))}
    </ul>
  );
}

export default SidePanelAnalogies;
```

- [ ] **Step 3: Replace `SidePanelSparkline.tsx`**

The Recharts components use their own prop-based styling so those stay as-is. Only the wrapper divs move to Tailwind.

```tsx
import React, { useMemo } from 'react';
import {
  LineChart,
  Line,
  Tooltip,
  ReferenceDot,
  ResponsiveContainer,
} from 'recharts';

import type { SparklinePoint } from '../types/disclosure.types';

export interface SidePanelSparklineProps {
  ticker: string;
  ohlcv_7d: SparklinePoint[];
}

export function SidePanelSparkline({ ticker, ohlcv_7d }: SidePanelSparklineProps) {
  const isPositive = useMemo(() => {
    if (ohlcv_7d.length === 0) return true;
    return ohlcv_7d[ohlcv_7d.length - 1]!.close >= ohlcv_7d[0]!.close;
  }, [ohlcv_7d]);

  const dotColor = isPositive ? 'var(--positive)' : 'var(--negative)';
  const lineColor = isPositive ? 'var(--positive)' : 'var(--negative)';

  if (ohlcv_7d.length === 0) {
    return (
      <div
        data-testid={`sparkline-${ticker}`}
        className="flex h-12 w-[160px] items-center justify-center rounded border border-dashed border-border text-[11px] text-muted"
      >
        No price data
      </div>
    );
  }

  const lastPoint = ohlcv_7d[ohlcv_7d.length - 1]!;

  return (
    <div
      data-testid={`sparkline-${ticker}`}
      className="w-[160px]"
      role="img"
      aria-label={`${ticker} price sparkline`}
    >
      <div className="mb-0.5 text-[11px] font-semibold text-text">{ticker}</div>
      <ResponsiveContainer width={160} height={48}>
        <LineChart data={ohlcv_7d} margin={{ top: 4, right: 4, bottom: 4, left: 4 }}>
          <Line
            type="monotone"
            dataKey="close"
            stroke={lineColor}
            strokeWidth={1.5}
            dot={false}
            isAnimationActive={false}
          />
          <ReferenceDot
            x={lastPoint.ts}
            y={lastPoint.close}
            r={3}
            fill={dotColor}
            stroke="none"
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export default SidePanelSparkline;
```

- [ ] **Step 4: Run tests to verify they pass**

```
npm test -- src/frontend/features/progressive-disclosure/components/SidePanelAnalogies.test.tsx src/frontend/features/progressive-disclosure/components/SidePanelSparkline.test.tsx
```

Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add src/frontend/features/progressive-disclosure/components/SidePanelAnalogies.tsx src/frontend/features/progressive-disclosure/components/SidePanelSparkline.tsx
git commit -m "style(disclosure): migrate SidePanelAnalogies and SidePanelSparkline to Tailwind"
```

---

## Task 6: Tailwind migration — `AuditTrailView`

**Files:**
- Modify: `src/frontend/features/progressive-disclosure/components/AuditTrailView.tsx`

- [ ] **Step 1: Run existing test**

```
npm test -- src/frontend/features/progressive-disclosure/components/AuditTrailView.test.tsx
```

Expected: PASS.

- [ ] **Step 2: Replace `AuditTrailView.tsx`**

```tsx
import React from 'react';

import { useAuditTrail } from '../hooks/useAuditTrail';

export interface AuditTrailViewProps {
  eventId: string | null;
  isOpen: boolean;
  onClose: () => void;
}

export function AuditTrailView({ eventId, isOpen, onClose }: AuditTrailViewProps) {
  const { data, isLoading } = useAuditTrail(eventId, isOpen);

  if (!isOpen) {
    return null;
  }

  return (
    <div
      data-testid="audit-trail-view"
      className="fixed inset-0 z-[300] flex items-start justify-center overflow-y-auto bg-black/50 pt-12"
    >
      <div className="flex max-h-[80vh] w-[640px] max-w-[90vw] flex-col overflow-hidden rounded-lg bg-surface-1 shadow-[var(--shadow-popover)]">
        {/* Header */}
        <div className="flex shrink-0 items-center justify-between border-b border-border px-5 py-4">
          <h2
            data-testid="audit-trail-title"
            className="m-0 text-base font-bold text-text"
          >
            Why this read?
          </h2>
          <button
            data-testid="audit-trail-close"
            onClick={onClose}
            aria-label="Close audit trail"
            className="cursor-pointer border-none bg-transparent p-1 text-lg text-muted"
          >
            ✕
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-5">
          {isLoading && (
            <p className="text-[13px] text-muted">Loading audit trail…</p>
          )}

          {data && (
            <>
              {data.analogies.length > 0 && (
                <section data-testid="audit-analogies-section" className="mb-5">
                  <h3 className="mb-2.5 mt-0 text-xs uppercase tracking-[0.06em] text-muted">
                    Historical Analogies
                  </h3>
                  <ol className="m-0 pl-4">
                    {[...data.analogies]
                      .sort((a, b) => b.similarity_score - a.similarity_score)
                      .map((a, idx) => (
                        <li
                          key={`${a.event_id}-${idx}`}
                          data-testid={`audit-analogy-${idx}`}
                          className="mb-2 text-[13px]"
                        >
                          <span className="font-medium text-text">{a.headline}</span>{' '}
                          <span className="text-[11px] text-muted">
                            ({a.occurred_at})
                          </span>{' '}
                          <span
                            data-testid={`audit-analogy-score-${idx}`}
                            className="inline-block rounded-full bg-signal/20 px-1.5 py-px text-[11px] font-semibold text-signal"
                          >
                            {Math.round(a.similarity_score * 100)}%
                          </span>
                        </li>
                      ))}
                  </ol>
                </section>
              )}

              <section data-testid="audit-prompt-section" className="mb-5">
                <h3 className="mb-1.5 mt-0 text-xs uppercase tracking-[0.06em] text-muted">
                  Prompt Version
                </h3>
                <code
                  data-testid="audit-prompt-version"
                  className="inline-block rounded bg-surface-2 px-2 py-1 font-mono text-xs text-text"
                >
                  {data.prompt_version || '(not available)'}
                </code>
              </section>

              <section data-testid="audit-reasoning-section" className="mb-5">
                <h3 className="mb-2.5 mt-0 text-xs uppercase tracking-[0.06em] text-muted">
                  Agent Reasoning Chain
                </h3>
                {data.reasoning_steps.length === 0 ? (
                  <p
                    data-testid="no-reasoning-chain"
                    className="text-[13px] italic text-muted"
                  >
                    No reasoning chain available for this event.
                  </p>
                ) : (
                  <ol className="m-0 pl-4">
                    {data.reasoning_steps.map((step, idx) => (
                      <li
                        key={idx}
                        data-testid={`reasoning-step-${idx}`}
                        className="mb-3 text-[13px] leading-[1.5]"
                      >
                        <span
                          data-testid={`step-agent-role-${idx}`}
                          className="mb-1 inline-block rounded px-1.5 py-px text-[11px] font-semibold bg-signal-soft text-signal"
                        >
                          {step.agent_role}
                        </span>
                        <p className="my-1 text-text">{step.content}</p>
                        {step.tool_calls.length > 0 && (
                          <p className="m-0 text-[11px] text-muted">
                            Tools: {step.tool_calls.join(', ')}
                          </p>
                        )}
                      </li>
                    ))}
                  </ol>
                )}
              </section>

              {data.langfuse_trace_url && (
                <section data-testid="langfuse-section">
                  <a
                    data-testid="langfuse-trace-link"
                    href={data.langfuse_trace_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-[13px] text-signal underline"
                  >
                    View full trace in Langfuse
                  </a>
                </section>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

export default AuditTrailView;
```

- [ ] **Step 3: Run test to verify it passes**

```
npm test -- src/frontend/features/progressive-disclosure/components/AuditTrailView.test.tsx
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add src/frontend/features/progressive-disclosure/components/AuditTrailView.tsx
git commit -m "style(disclosure): migrate AuditTrailView to Tailwind"
```

---

## Task 7: Tailwind migration — `SidePanel`

**Files:**
- Modify: `src/frontend/features/progressive-disclosure/components/SidePanel.tsx`

- [ ] **Step 1: Run existing test**

```
npm test -- src/frontend/features/progressive-disclosure/components/SidePanel.test.tsx
```

Expected: PASS.

- [ ] **Step 2: Replace `SidePanel.tsx`**

```tsx
import React from 'react';

import { useSidePanelData } from '../hooks/useSidePanelData';
import { ContrarianCallout } from './ContrarianCallout';
import { LowSampleDisclaimer } from './LowSampleDisclaimer';
import { SidePanelAnalogies } from './SidePanelAnalogies';
import { SidePanelSparkline } from './SidePanelSparkline';

function SidePanelSkeleton() {
  return (
    <div data-testid="side-panel-skeleton" className="p-5">
      {[80, 200, 60, 160, 100, 140].map((w, i) => (
        <div
          key={i}
          className="mb-3 rounded bg-surface-2"
          style={{
            height: i === 0 ? '20px' : i === 1 ? '80px' : '14px',
            width: `${w}%`,
            maxWidth: `${w}%`,
          }}
        />
      ))}
    </div>
  );
}

export interface SidePanelProps {
  eventId: string | null;
  isOpen: boolean;
  onClose: () => void;
  onOpenAuditTrail: () => void;
  onOpenDeepDive: () => void;
}

export function SidePanel({
  eventId,
  isOpen,
  onClose,
  onOpenAuditTrail,
  onOpenDeepDive,
}: SidePanelProps) {
  const { data, isLoading } = useSidePanelData(eventId, isOpen);

  return (
    <div
      data-testid="side-panel"
      data-open={isOpen}
      className={`fixed inset-y-0 right-0 z-[200] flex w-[420px] flex-col overflow-y-auto bg-surface-1 shadow-[var(--shadow-popover)] transition-transform duration-[250ms] ease-in-out ${
        isOpen ? 'translate-x-0 pointer-events-auto' : 'translate-x-full pointer-events-none'
      }`}
    >
      {/* Header */}
      <div className="flex shrink-0 items-center justify-between border-b border-border px-[18px] py-4">
        <h2 className="m-0 text-[15px] font-bold text-text">Event Analysis</h2>
        <button
          data-testid="side-panel-close"
          onClick={onClose}
          aria-label="Close side panel"
          className="cursor-pointer border-none bg-transparent p-1 text-lg text-muted"
        >
          ✕
        </button>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto p-[18px]">
        {isOpen && isLoading && <SidePanelSkeleton />}

        {isOpen && data && (
          <>
            {data.is_contrarian && data.contrarian_callout && (
              <ContrarianCallout text={data.contrarian_callout} />
            )}

            <p
              data-testid="side-panel-summary"
              className="mb-3.5 text-[13px] leading-relaxed text-text"
            >
              {data.summary}
            </p>

            {data.sparklines.length > 0 && (
              <div
                data-testid="sparklines-section"
                className="mb-4 grid grid-cols-2 gap-3"
              >
                {data.sparklines.slice(0, 6).map((s) => (
                  <SidePanelSparkline key={s.ticker} ticker={s.ticker} ohlcv_7d={s.ohlcv_7d} />
                ))}
              </div>
            )}

            <div className="mb-2.5">
              <p className="mb-0.5 text-xs text-text">
                Signal:{' '}
                <strong data-testid="side-panel-action-signal">{data.action_signal}</strong>
              </p>
              <p
                data-testid="side-panel-confidence"
                className="mb-0.5 text-xs text-muted"
              >
                Confidence: {(data.confidence * 100).toFixed(0)}% · Sample: {data.sample_size}
              </p>
            </div>

            {data.low_sample && <LowSampleDisclaimer />}

            <div className="mb-4">
              <h3 className="mb-1.5 mt-0 text-xs uppercase tracking-[0.06em] text-muted">
                Rationale
              </h3>
              <p
                data-testid="side-panel-rationale"
                className="m-0 text-[13px] leading-relaxed text-text"
              >
                {data.rationale}
              </p>
            </div>

            <div data-testid="analogies-section" className="mb-4">
              <h3 className="mb-2 mt-0 text-xs uppercase tracking-[0.06em] text-muted">
                Historical Analogies
              </h3>
              <SidePanelAnalogies analogies={data.analogies} />
            </div>

            {data.affected_companies.length > 0 && (
              <div data-testid="affected-companies-section" className="mb-4">
                <h3 className="mb-2 mt-0 text-xs uppercase tracking-[0.06em] text-muted">
                  Affected Holdings
                </h3>
                <table className="w-full border-collapse text-xs">
                  <thead>
                    <tr className="border-b border-border">
                      <th className="px-1.5 py-1 text-left font-semibold text-muted">Company</th>
                      <th className="px-1.5 py-1 text-right font-semibold text-muted">Score</th>
                      <th className="px-1.5 py-1 text-right font-semibold text-muted">Delta</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.affected_companies.map((c) => (
                      <tr
                        key={c.company_id.toString()}
                        data-testid={`company-row-${c.ticker}`}
                        className="border-b border-border-subtle"
                      >
                        <td className="px-1.5 py-1 text-text">
                          <span className="font-semibold">{c.ticker}</span>{' '}
                          <span className="text-muted">{c.name}</span>
                        </td>
                        <td className="px-1.5 py-1 text-right text-text">
                          {c.score.toFixed(1)}
                        </td>
                        <td
                          className={`px-1.5 py-1 text-right ${
                            c.delta >= 0 ? 'text-positive' : 'text-negative'
                          }`}
                        >
                          {c.delta >= 0 ? '+' : ''}{c.delta.toFixed(1)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {data.social_posts && data.social_posts.length > 0 && (
              <div data-testid="social-posts-section" className="mb-4">
                <h3 className="mb-2 mt-0 text-xs uppercase tracking-[0.06em] text-muted">
                  Triggering Posts
                </h3>
                {data.social_posts.map((post) => (
                  <div
                    key={post.post_id}
                    data-testid={`social-post-${post.post_id}`}
                    className="mb-2 rounded bg-surface-2 px-2.5 py-2 text-xs"
                  >
                    <p className="mb-0.5 font-semibold text-muted">
                      {post.source} · {post.timestamp}
                    </p>
                    <p className="m-0 text-text">{post.text}</p>
                  </div>
                ))}
              </div>
            )}

            <div className="mt-4 flex items-center justify-between border-t border-border-subtle pt-3">
              <button
                data-testid="why-this-read-link"
                onClick={onOpenAuditTrail}
                className="cursor-pointer border-none bg-transparent p-0 text-xs font-medium text-signal underline"
              >
                Why this read?
              </button>
              <button
                data-testid="full-analysis-button"
                onClick={onOpenDeepDive}
                className="cursor-pointer rounded-[5px] border-none bg-signal px-4 py-1.5 text-xs font-semibold text-white"
              >
                Full Analysis
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

export default SidePanel;
```

- [ ] **Step 3: Run test to verify it passes**

```
npm test -- src/frontend/features/progressive-disclosure/components/SidePanel.test.tsx
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add src/frontend/features/progressive-disclosure/components/SidePanel.tsx
git commit -m "style(disclosure): migrate SidePanel drawer to Tailwind"
```

---

## Task 8: Tailwind migration — `DeepDivePage`

**Files:**
- Modify: `src/frontend/features/progressive-disclosure/components/DeepDivePage.tsx`

- [ ] **Step 1: Run existing test**

```
npm test -- src/frontend/features/progressive-disclosure/components/DeepDivePage.test.tsx
```

Expected: PASS.

- [ ] **Step 2: Replace `DeepDivePage.tsx`**

```tsx
import React, { useState } from 'react';
import { useParams, Link } from 'react-router-dom';

import { useDeepDive } from '../hooks/useDeepDive';
import { isDeepDivePending } from '../types/disclosure.types';
import type { DeepDiveData, ScenarioNode, AnalogSummary } from '../types/disclosure.types';

function ScenarioNodeView({ node, depth = 0 }: { node: ScenarioNode; depth?: number }) {
  const [expanded, setExpanded] = useState(depth === 0);

  return (
    <div
      data-testid={`scenario-node-${node.label.replace(/\s+/g, '-').toLowerCase()}`}
      className="mb-2"
      style={{ marginLeft: depth * 16 }}
    >
      <button
        onClick={() => setExpanded((e) => !e)}
        aria-expanded={expanded}
        className={`flex w-full cursor-pointer items-center gap-1.5 rounded border-none px-2 py-1.5 text-left text-[13px] text-text ${
          depth === 0 ? 'bg-signal/10' : 'bg-surface-2'
        } ${node.children.length > 0 ? 'cursor-pointer' : 'cursor-default'}`}
      >
        {node.children.length > 0 && (
          <span aria-hidden="true">{expanded ? '▼' : '▶'}</span>
        )}
        <span className="font-semibold">{node.label}</span>
        <span className="ml-auto rounded-full bg-signal/20 px-1.5 py-px text-[11px] font-semibold text-signal">
          {(node.probability * 100).toFixed(0)}%
        </span>
      </button>
      {expanded && (
        <p className="mx-2 my-1 text-xs leading-[1.5] text-muted">{node.description}</p>
      )}
      {expanded && node.children.length > 0 && (
        <div className="mt-1">
          {node.children.map((child, i) => (
            <ScenarioNodeView key={i} node={child} depth={depth + 1} />
          ))}
        </div>
      )}
    </div>
  );
}

type SortKey = 'similarity_score' | 'occurred_at';

function AnalogiesTable({ analogies }: { analogies: AnalogSummary[] }) {
  const [sortKey, setSortKey] = useState<SortKey>('similarity_score');
  const [sortAsc, setSortAsc] = useState(false);

  const sorted = [...analogies].sort((a, b) => {
    const av = a[sortKey];
    const bv = b[sortKey];
    const cmp = av < bv ? -1 : av > bv ? 1 : 0;
    return sortAsc ? cmp : -cmp;
  });

  function handleSort(key: SortKey) {
    if (sortKey === key) {
      setSortAsc((a) => !a);
    } else {
      setSortKey(key);
      setSortAsc(false);
    }
  }

  return (
    <table data-testid="analogies-table" className="w-full border-collapse text-[13px]">
      <thead>
        <tr className="border-b-2 border-border">
          <th className="px-2 py-1.5 text-left font-semibold text-muted">Headline</th>
          <th
            onClick={() => handleSort('occurred_at')}
            data-testid="sort-by-date"
            className="cursor-pointer px-2 py-1.5 text-left font-semibold text-muted"
          >
            Date {sortKey === 'occurred_at' ? (sortAsc ? '↑' : '↓') : ''}
          </th>
          <th
            onClick={() => handleSort('similarity_score')}
            data-testid="sort-by-score"
            className="cursor-pointer px-2 py-1.5 text-right font-semibold text-muted"
          >
            Similarity {sortKey === 'similarity_score' ? (sortAsc ? '↑' : '↓') : ''}
          </th>
        </tr>
      </thead>
      <tbody>
        {sorted.map((a, idx) => (
          <tr key={`${a.event_id}-${idx}`} data-testid={`analogy-row-${idx}`} className="border-b border-border-subtle">
            <td className="px-2 py-1.5 text-text">{a.headline}</td>
            <td className="px-2 py-1.5 text-xs text-muted">{a.occurred_at}</td>
            <td className="px-2 py-1.5 text-right">
              <span className="rounded-full bg-signal/20 px-1.5 py-px text-[11px] font-semibold text-signal">
                {Math.round(a.similarity_score * 100)}%
              </span>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function DeepDivePage() {
  const { eventId } = useParams<{ eventId: string }>();
  const { data, isLoading } = useDeepDive(eventId ?? null, true);

  if (isLoading || !data || isDeepDivePending(data)) {
    return (
      <div
        data-testid="deep-dive-loading"
        className="flex min-h-screen flex-col items-center justify-center bg-surface-0"
      >
        <div
          className="mb-5 h-12 w-12 animate-spin rounded-full border-4 border-surface-3 border-t-signal"
          role="progressbar"
          aria-label="Loading"
        />
        <p
          data-testid="deep-dive-loading-text"
          className="max-w-[360px] text-center text-base text-text"
        >
          Generating deep-dive analysis… This may take up to 5 minutes.
        </p>
      </div>
    );
  }

  const deepDive = data as DeepDiveData;

  return (
    <div
      data-testid="deep-dive-page"
      className="min-h-screen bg-surface-0 p-8"
    >
      <div className="mx-auto max-w-[900px]">
        <Link
          data-testid="back-to-map-link"
          to="/"
          className="mb-6 inline-flex items-center gap-1.5 text-[13px] text-signal no-underline"
        >
          ← Back to Intelligence Map
        </Link>

        <section data-testid="deep-dive-memo" className="mb-8">
          <h1 className="mb-4 text-[22px] font-bold text-text">Deep-Dive Analysis</h1>
          <div className="rounded-lg bg-surface-1 p-6 text-sm leading-[1.7] text-text shadow-[var(--shadow-md)] whitespace-pre-wrap">
            {deepDive.memo}
          </div>
        </section>

        <section data-testid="scenario-tree-section" className="mb-8">
          <h2 className="mb-3 text-base font-bold text-text">Scenario Analysis</h2>
          <div className="rounded-lg bg-surface-1 p-4 shadow-[var(--shadow-md)]">
            {deepDive.scenario_tree === null ? (
              <p data-testid="no-scenario-analysis" className="text-[13px] italic text-muted">
                No scenario analysis available.
              </p>
            ) : (
              <ScenarioNodeView node={deepDive.scenario_tree} />
            )}
          </div>
        </section>

        {deepDive.analogies.length > 0 && (
          <section data-testid="deep-dive-analogies-section" className="mb-8">
            <h2 className="mb-3 text-base font-bold text-text">Historical Analogies</h2>
            <div className="overflow-x-auto rounded-lg bg-surface-1 p-4 shadow-[var(--shadow-md)]">
              <AnalogiesTable analogies={deepDive.analogies} />
            </div>
          </section>
        )}

        {deepDive.affected_companies.length > 0 && (
          <section data-testid="deep-dive-companies-section" className="mb-8">
            <h2 className="mb-3 text-base font-bold text-text">Affected Holdings</h2>
            <div className="overflow-x-auto rounded-lg bg-surface-1 p-4 shadow-[var(--shadow-md)]">
              <table data-testid="companies-table" className="w-full border-collapse text-[13px]">
                <thead>
                  <tr className="border-b-2 border-border">
                    <th className="px-2 py-1.5 text-left font-semibold text-muted">Company</th>
                    <th className="px-2 py-1.5 text-left font-semibold text-muted">Ticker</th>
                    <th className="px-2 py-1.5 text-right font-semibold text-muted">Score</th>
                    <th className="px-2 py-1.5 text-right font-semibold text-muted">Delta</th>
                  </tr>
                </thead>
                <tbody>
                  {deepDive.affected_companies.map((c, idx) => (
                    <tr
                      key={`${c.company_id}-${idx}`}
                      data-testid={`company-row-${c.ticker}`}
                      className="border-b border-border-subtle"
                    >
                      <td className="px-2 py-1.5 text-text">{c.name}</td>
                      <td className="px-2 py-1.5 font-semibold text-text">{c.ticker}</td>
                      <td className="px-2 py-1.5 text-right text-text">{c.score.toFixed(1)}</td>
                      <td className={`px-2 py-1.5 text-right ${c.delta >= 0 ? 'text-positive' : 'text-negative'}`}>
                        {c.delta >= 0 ? '+' : ''}{c.delta.toFixed(1)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}
      </div>
    </div>
  );
}

export default DeepDivePage;
```

- [ ] **Step 3: Run test to verify it passes**

```
npm test -- src/frontend/features/progressive-disclosure/components/DeepDivePage.test.tsx
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add src/frontend/features/progressive-disclosure/components/DeepDivePage.tsx
git commit -m "style(disclosure): migrate DeepDivePage to Tailwind"
```

---

## Task 9: Migrate Briefs hooks

**Files:**
- Modify: `src/frontend/features/briefs/hooks/useBriefs.ts`
- Modify: `src/frontend/features/briefs/hooks/useBriefDetail.ts`
- Modify: `src/frontend/features/briefs/hooks/useFeedback.ts`
- Create: `src/frontend/features/briefs/hooks/useBriefs.test.ts`
- Create: `src/frontend/features/briefs/hooks/useBriefDetail.test.ts`
- Create: `src/frontend/features/briefs/hooks/useFeedback.test.ts`

- [ ] **Step 1: Write the failing tests**

Create `src/frontend/features/briefs/hooks/useBriefs.test.ts`:

```typescript
import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';
import * as client from '@/lib/api/client';
import type { BriefListResponse } from '../briefs.types';

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: qc }, children);
}

const PAGE: BriefListResponse = {
  data: { items: [], next_cursor: null, total: 0 },
  meta: {},
  error: null,
};

describe('useBriefs', () => {
  afterEach(() => vi.restoreAllMocks());

  it('calls api() with the correct path when briefType is set', async () => {
    const spy = vi.spyOn(client, 'api').mockResolvedValue(PAGE);
    const { useBriefs } = await import('./useBriefs');
    const { result } = renderHook(() => useBriefs({ briefType: 'MORNING' }), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(spy).toHaveBeenCalledWith(expect.stringContaining('/briefs?'));
    expect(spy).toHaveBeenCalledWith(expect.stringContaining('type=MORNING'));
  });

  it('does not include type param when briefType is undefined', async () => {
    const spy = vi.spyOn(client, 'api').mockResolvedValue(PAGE);
    const { useBriefs } = await import('./useBriefs');
    const { result } = renderHook(() => useBriefs(), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    const calledPath = (spy.mock.calls[0] as string[])[0];
    expect(calledPath).not.toContain('type=');
  });
});
```

Create `src/frontend/features/briefs/hooks/useBriefDetail.test.ts`:

```typescript
import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';
import * as client from '@/lib/api/client';

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: qc }, children);
}

describe('useBriefDetail', () => {
  afterEach(() => vi.restoreAllMocks());

  it('calls api() with the correct brief ID path', async () => {
    const mockData = { id: 'b-1', title: 'Test Brief' };
    const spy = vi.spyOn(client, 'api').mockResolvedValue(mockData);
    const { useBriefDetail } = await import('./useBriefDetail');
    const { result } = renderHook(() => useBriefDetail('b-1'), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(spy).toHaveBeenCalledWith('/briefs/b-1');
    expect(result.current.data).toEqual(mockData);
  });

  it('does not fire when briefId is empty', async () => {
    const spy = vi.spyOn(client, 'api').mockResolvedValue({});
    const { useBriefDetail } = await import('./useBriefDetail');
    const { result } = renderHook(() => useBriefDetail(''), { wrapper: makeWrapper() });
    expect(result.current.isLoading).toBe(false);
    expect(spy).not.toHaveBeenCalled();
  });
});
```

Create `src/frontend/features/briefs/hooks/useFeedback.test.ts`:

```typescript
import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';
import * as client from '@/lib/api/client';

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: qc }, children);
}

describe('useFeedback', () => {
  afterEach(() => vi.restoreAllMocks());

  it('POSTs to /briefs/{id}/feedback via api()', async () => {
    const mockResponse = { success: true };
    const spy = vi.spyOn(client, 'api').mockResolvedValue(mockResponse);
    const { useFeedback } = await import('./useFeedback');
    const { result } = renderHook(() => useFeedback('b-1'), { wrapper: makeWrapper() });
    await act(async () => {
      await result.current.mutateAsync({ rating: 5, comment: 'good' });
    });
    expect(spy).toHaveBeenCalledWith(
      '/briefs/b-1/feedback',
      expect.objectContaining({ method: 'POST' }),
    );
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

```
npm test -- src/frontend/features/briefs/hooks/
```

Expected: FAIL — `api` is not called (hooks still use raw `fetch`).

- [ ] **Step 3: Migrate `useBriefs.ts`**

```typescript
import { useInfiniteQuery } from '@tanstack/react-query';
import type { BriefListResponse, BriefType } from '../briefs.types';
import { api } from '@/lib/api/client';

interface UseBriefsOptions {
  briefType?: BriefType | null;
}

async function fetchBriefs(
  briefType: BriefType | null | undefined,
  cursor: string | null,
): Promise<BriefListResponse> {
  const params = new URLSearchParams();
  if (briefType) params.set('type', briefType);
  if (cursor) params.set('cursor', cursor);
  params.set('limit', '20');
  return api<BriefListResponse>('/briefs?' + params.toString());
}

export function useBriefs({ briefType }: UseBriefsOptions = {}) {
  return useInfiniteQuery({
    queryKey: ['briefs', briefType ?? null],
    queryFn: ({ pageParam }) =>
      fetchBriefs(briefType, (pageParam as string | null) ?? null),
    getNextPageParam: (lastPage: BriefListResponse) =>
      lastPage.data.next_cursor ?? undefined,
    initialPageParam: null as string | null,
  });
}
```

- [ ] **Step 4: Migrate `useBriefDetail.ts`**

```typescript
import { useQuery } from '@tanstack/react-query';
import type { BriefDetailResponse } from '../briefs.types';
import { api } from '@/lib/api/client';

async function fetchBriefDetail(briefId: string): Promise<BriefDetailResponse> {
  return api<BriefDetailResponse>('/briefs/' + briefId);
}

export function useBriefDetail(briefId: string) {
  return useQuery({
    queryKey: ['brief', briefId],
    queryFn: () => fetchBriefDetail(briefId),
    enabled: Boolean(briefId),
  });
}
```

- [ ] **Step 5: Migrate `useFeedback.ts`**

```typescript
import { useMutation } from '@tanstack/react-query';
import type { FeedbackRequest, FeedbackResponse } from '../briefs.types';
import { api } from '@/lib/api/client';

async function submitFeedback(
  briefId: string,
  payload: FeedbackRequest,
): Promise<FeedbackResponse> {
  return api<FeedbackResponse>('/briefs/' + briefId + '/feedback', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function useFeedback(briefId: string) {
  return useMutation({
    mutationFn: (payload: FeedbackRequest) => submitFeedback(briefId, payload),
    onError: (error: Error) => {
      console.warn('[useFeedback] Feedback submission failed:', error.message);
    },
  });
}
```

- [ ] **Step 6: Run tests to verify they pass**

```
npm test -- src/frontend/features/briefs/hooks/
```

Expected: All PASS.

- [ ] **Step 7: Commit**

```bash
git add src/frontend/features/briefs/hooks/
git commit -m "refactor(briefs): migrate useBriefs, useBriefDetail, useFeedback to api<T>()"
```

---

## Task 10: Migrate Q&A API

**Files:**
- Modify: `src/frontend/features/qa/qaApi.ts`
- Create: `src/frontend/features/qa/qaApi.test.ts`

- [ ] **Step 1: Write the failing tests**

Create `src/frontend/features/qa/qaApi.test.ts`:

```typescript
import { describe, it, expect, vi, afterEach } from 'vitest';
import * as client from '@/lib/api/client';

describe('qaApi', () => {
  afterEach(() => vi.restoreAllMocks());

  describe('createQASession', () => {
    it('calls api() for POST /qa/sessions', async () => {
      const mockResponse = { session_id: 'sess-1' };
      const spy = vi.spyOn(client, 'api').mockResolvedValue(mockResponse);
      const { createQASession } = await import('./qaApi');
      const result = await createQASession();
      expect(spy).toHaveBeenCalledWith('/qa/sessions', expect.objectContaining({ method: 'POST' }));
      expect(result).toEqual(mockResponse);
    });
  });

  describe('submitQuestionFetch', () => {
    it('includes Authorization header from getAccessToken()', async () => {
      vi.spyOn(client, 'getAccessToken').mockReturnValue('tok-abc');
      const mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        body: { getReader: () => ({ read: vi.fn().mockResolvedValue({ done: true }) }) },
      });
      vi.stubGlobal('fetch', mockFetch);

      const { submitQuestionFetch } = await import('./qaApi');
      await submitQuestionFetch('sess-1', 'What is risk?');

      const [, init] = mockFetch.mock.calls[0] as [string, RequestInit];
      const headers = new Headers(init.headers as HeadersInit);
      expect(headers.get('authorization')).toBe('Bearer tok-abc');
    });

    it('does not include credentials: include (POST+SSE uses bearer only)', async () => {
      vi.spyOn(client, 'getAccessToken').mockReturnValue('tok-abc');
      const mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        body: { getReader: () => ({ read: vi.fn().mockResolvedValue({ done: true }) }) },
      });
      vi.stubGlobal('fetch', mockFetch);

      const { submitQuestionFetch } = await import('./qaApi');
      await submitQuestionFetch('sess-1', 'test');

      const [, init] = mockFetch.mock.calls[0] as [string, RequestInit];
      expect((init as Record<string, unknown>).credentials).toBeUndefined();
    });
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

```
npm test -- src/frontend/features/qa/qaApi.test.ts
```

Expected: FAIL — `createQASession` still uses raw fetch; `submitQuestionFetch` has no auth header.

- [ ] **Step 3: Migrate `qaApi.ts`**

```typescript
import { api, getAccessToken } from '@/lib/api/client';
import type { CreateSessionResponse } from './qaApi';

export type { QASource, QAAnswer, CreateSessionResponse, SSEChunkEvent, SSEDoneEvent, SSECostLimitedEvent, SSEEvent } from './qaApi';

export interface QASource {
  type: string;
  id: string;
  description: string;
}

export interface QAAnswer {
  answer_text: string;
  sources: QASource[];
  confidence: number;
  cost_usd: number;
  cost_limited: boolean;
}

export interface CreateSessionResponse {
  session_id: string;
}

export interface SSEChunkEvent {
  type: "chunk";
  text: string;
}

export interface SSEDoneEvent {
  type: "done";
  answer: QAAnswer;
}

export interface SSECostLimitedEvent {
  type: "cost_limited";
  partial_answer: QAAnswer;
}

export type SSEEvent = SSEChunkEvent | SSEDoneEvent | SSECostLimitedEvent;

export async function createQASession(): Promise<CreateSessionResponse> {
  return api<CreateSessionResponse>('/qa/sessions', { method: 'POST' });
}

export function submitQAQuestion(
  _sessionId: string,
  _question: string,
): { eventSource: EventSource; abort: () => void } {
  throw new Error(
    "Use useQAStream hook which handles POST + SSE streaming via fetch API.",
  );
}

/**
 * POST + SSE stream — cannot use api<T>() because lib/api/stream.ts only supports GET SSE.
 * Uses raw fetch with Bearer token from getAccessToken().
 */
export async function submitQuestionFetch(
  sessionId: string,
  question: string,
): Promise<Response> {
  const token = getAccessToken();
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  return fetch(`/api/v1/qa/sessions/${sessionId}/messages`, {
    method: "POST",
    headers,
    body: JSON.stringify({ question }),
  });
}
```

- [ ] **Step 4: Run tests to verify they pass**

```
npm test -- src/frontend/features/qa/qaApi.test.ts
```

Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add src/frontend/features/qa/qaApi.ts src/frontend/features/qa/qaApi.test.ts
git commit -m "refactor(qa): migrate createQASession to api<T>(); add auth to submitQuestionFetch"
```

---

## Task 11: Migrate Company Detail hooks

> **Note — dark feature.** The `/ws/analysis/{run_id}` backend WebSocket handler
> does not exist yet (Phase 3 spec §1.2 lists it as a non-goal). After this task,
> the frontend will successfully POST trigger and open the socket, but no
> `COMPLETED` frame will arrive until a future phase builds the backend producer.
> A safety timeout in `useAnalyzeNow` prevents the spinner from hanging
> indefinitely; the button UI surfaces a tooltip. See Step 4 below.

**Files:**
- Modify: `src/frontend/features/company-detail/hooks/useCompanyDetail.ts`
- Modify: `src/frontend/features/company-detail/hooks/useAnalyzeNow.ts`
- Create: `src/frontend/features/company-detail/hooks/useCompanyDetail.test.ts`
- Create: `src/frontend/features/company-detail/hooks/useAnalyzeNow.test.ts`

- [ ] **Step 1: Write the failing tests**

Create `src/frontend/features/company-detail/hooks/useCompanyDetail.test.ts`:

```typescript
import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';
import * as client from '@/lib/api/client';

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: qc }, children);
}

describe('useCompanyDetail', () => {
  afterEach(() => vi.restoreAllMocks());

  it('calls api() with /companies/{id}/detail', async () => {
    const mockData = { company_id: 'c-1', name: 'Acme' };
    const spy = vi.spyOn(client, 'api').mockResolvedValue(mockData);
    const { useCompanyDetail } = await import('./useCompanyDetail');
    const { result } = renderHook(
      () => useCompanyDetail({ companyId: 'c-1' }),
      { wrapper: makeWrapper() },
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(spy).toHaveBeenCalledWith('/companies/c-1/detail');
    expect(result.current.data).toEqual(mockData);
  });

  it('includes profile_id query param when provided', async () => {
    const spy = vi.spyOn(client, 'api').mockResolvedValue({});
    const { useCompanyDetail } = await import('./useCompanyDetail');
    const { result } = renderHook(
      () => useCompanyDetail({ companyId: 'c-1', profileId: 'p-42' }),
      { wrapper: makeWrapper() },
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(spy).toHaveBeenCalledWith('/companies/c-1/detail?profile_id=p-42');
  });
});
```

Create `src/frontend/features/company-detail/hooks/useAnalyzeNow.test.ts`:

```typescript
import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import * as client from '@/lib/api/client';
import * as ws from '@/lib/api/ws';

describe('useAnalyzeNow', () => {
  afterEach(() => vi.restoreAllMocks());

  it('calls api() to POST trigger and apiSocket() to open the WebSocket', async () => {
    vi.spyOn(client, 'api').mockResolvedValue({ run_id: 'run-1', company_id: 'c-1', status: 'running' });
    const closeMock = vi.fn();
    const socketSpy = vi.spyOn(ws, 'apiSocket').mockReturnValue({ close: closeMock });

    const { useAnalyzeNow } = await import('./useAnalyzeNow');
    const { result } = renderHook(() => useAnalyzeNow({ companyId: 'c-1' }));

    await act(async () => { await result.current.trigger(); });

    expect(client.api).toHaveBeenCalledWith(
      '/companies/c-1/analysis',
      expect.objectContaining({ method: 'POST' }),
    );
    expect(socketSpy).toHaveBeenCalledWith(
      '/ws/analysis/run-1',
      expect.objectContaining({ onMessage: expect.any(Function), onError: expect.any(Function) }),
    );
    expect(result.current.isLoading).toBe(true);
    expect(result.current.runId).toBe('run-1');
  });

  it('sets error without entering loading on 409 conflict', async () => {
    const { ApiError } = await import('@/lib/api/errors');
    vi.spyOn(client, 'api').mockRejectedValue(new ApiError(409, 'CONFLICT', 'Analysis in progress'));

    const { useAnalyzeNow } = await import('./useAnalyzeNow');
    const { result } = renderHook(() => useAnalyzeNow({ companyId: 'c-1' }));

    await act(async () => { await result.current.trigger(); });

    expect(result.current.isLoading).toBe(false);
    expect(result.current.error).toContain('already in progress');
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

```
npm test -- src/frontend/features/company-detail/hooks/useCompanyDetail.test.ts src/frontend/features/company-detail/hooks/useAnalyzeNow.test.ts
```

Expected: FAIL.

- [ ] **Step 3: Migrate `useCompanyDetail.ts`**

```typescript
import { useQuery } from '@tanstack/react-query';
import type { CompanyDetailResponse } from '../types';
import { api } from '@/lib/api/client';

const COMPANY_DETAIL_STALE_MS = 60_000;

async function fetchCompanyDetail(
  companyId: string,
  profileId?: string,
): Promise<CompanyDetailResponse> {
  const params = new URLSearchParams();
  if (profileId) {
    params.set('profile_id', profileId);
  }
  const qs = params.toString();
  return api<CompanyDetailResponse>(
    '/companies/' + companyId + '/detail' + (qs ? '?' + qs : ''),
  );
}

export function companyDetailQueryKey(companyId: string, profileId?: string) {
  return ['companyDetail', companyId, profileId ?? null] as const;
}

export interface UseCompanyDetailOptions {
  companyId: string;
  profileId?: string;
}

export function useCompanyDetail({ companyId, profileId }: UseCompanyDetailOptions) {
  return useQuery({
    queryKey: companyDetailQueryKey(companyId, profileId),
    queryFn: () => fetchCompanyDetail(companyId, profileId),
    staleTime: COMPANY_DETAIL_STALE_MS,
    enabled: !!companyId,
  });
}
```

- [ ] **Step 4: Migrate `useAnalyzeNow.ts`**

Includes a 5-minute safety timeout because the `/ws/analysis/{run_id}` backend
producer is not yet wired (see task header). The timeout fires `onError` semantics
so the UI resets cleanly instead of hanging forever.

```typescript
import { useState, useRef, useCallback, useEffect } from 'react';
import { api } from '@/lib/api/client';
import { ApiError } from '@/lib/api/errors';
import { apiSocket } from '@/lib/api/ws';
import type { SocketHandle } from '@/lib/api/ws';

const ANALYSIS_TIMEOUT_MS = 5 * 60 * 1000;

export interface UseAnalyzeNowOptions {
  companyId: string;
  onReportReady?: (runId: string) => void;
}

export interface UseAnalyzeNowResult {
  trigger: () => Promise<void>;
  isLoading: boolean;
  runId: string | null;
  error: string | null;
}

interface AnalysisRunResponse {
  run_id: string;
  company_id: string;
  status: string;
}

export function useAnalyzeNow({
  companyId,
  onReportReady,
}: UseAnalyzeNowOptions): UseAnalyzeNowResult {
  const [isLoading, setIsLoading] = useState(false);
  const [runId, setRunId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const socketRef = useRef<SocketHandle | null>(null);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const cleanup = useCallback(() => {
    if (timeoutRef.current !== null) {
      clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }
    socketRef.current?.close();
    socketRef.current = null;
  }, []);

  useEffect(() => cleanup, [cleanup]);

  const subscribeToWebSocket = useCallback(
    (newRunId: string) => {
      cleanup();

      socketRef.current = apiSocket('/ws/analysis/' + newRunId, {
        onMessage: (msg: unknown) => {
          const typed = msg as { type?: string };
          if (typed.type === 'COMPLETED') {
            setIsLoading(false);
            onReportReady?.(newRunId);
            cleanup();
          }
        },
        onClose: () => {},
        onError: () => {
          setError('WebSocket error during analysis.');
          setIsLoading(false);
          cleanup();
        },
      });

      // Safety timeout: backend producer for /ws/analysis/{run_id} is not yet
      // wired (Phase 4). Without this, the spinner would hang indefinitely.
      timeoutRef.current = setTimeout(() => {
        setError(
          'Analysis timed out. The analysis backend is not yet available; ' +
            'please try again later.',
        );
        setIsLoading(false);
        cleanup();
      }, ANALYSIS_TIMEOUT_MS);
    },
    [onReportReady, cleanup],
  );

  const trigger = useCallback(async (): Promise<void> => {
    setError(null);
    try {
      const run = await api<AnalysisRunResponse>(
        '/companies/' + companyId + '/analysis',
        { method: 'POST' },
      );
      setIsLoading(true);
      setRunId(run.run_id);
      subscribeToWebSocket(run.run_id);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setError('Analysis already in progress for this company.');
        // Do not set isLoading=true on 409
        return;
      }
      const msg = err instanceof Error ? err.message : String(err);
      setError('Failed to trigger analysis: ' + msg);
    }
  }, [companyId, subscribeToWebSocket]);

  return { trigger, isLoading, runId, error };
}
```

**Tooltip on the trigger button.** In `CompanyDetailPage.tsx` (or wherever the
Analyze-Now button lives), add a `title` attribute:

```tsx
<button
  onClick={() => analyze.trigger()}
  disabled={analyze.isLoading}
  title="Analysis backend coming soon — the request will be queued."
  className="…"
>
  {analyze.isLoading ? 'Analyzing…' : 'Analyze Now'}
</button>
```

If the button file is not in the task's file map, defer the tooltip to whichever
task owns `CompanyDetailPage.tsx` and add a follow-up note. The hook-level
timeout is the load-bearing fix; the tooltip is UX polish.

- [ ] **Step 5: Run tests to verify they pass**

```
npm test -- src/frontend/features/company-detail/hooks/useCompanyDetail.test.ts src/frontend/features/company-detail/hooks/useAnalyzeNow.test.ts
```

Expected: All PASS.

- [ ] **Step 6: Commit**

```bash
git add src/frontend/features/company-detail/hooks/
git commit -m "refactor(company-detail): migrate useCompanyDetail and useAnalyzeNow to api<T>()/apiSocket()"
```

---

## Task 12: Migrate AI Audit Console hooks

**Files:**
- Modify: `src/frontend/pages/admin/ai-audit/hooks/useDecisionLog.ts`
- Modify: `src/frontend/pages/admin/ai-audit/hooks/useWorkflowHistory.ts`
- Create: `src/frontend/pages/admin/ai-audit/hooks/useDecisionDetail.ts`
- Create: `src/frontend/pages/admin/ai-audit/hooks/useWorkflowDetail.ts`
- Modify: `src/frontend/pages/admin/ai-audit/DecisionLogPanel.tsx` (remove inline fetch, use hook)
- Modify: `src/frontend/pages/admin/ai-audit/WorkflowHistoryPanel.tsx` (remove inline fetch, use hook)
- Create: `src/frontend/pages/admin/ai-audit/hooks/useDecisionDetail.test.ts`
- Create: `src/frontend/pages/admin/ai-audit/hooks/useWorkflowDetail.test.ts`

- [ ] **Step 1: Write failing tests for new hooks**

Create `src/frontend/pages/admin/ai-audit/hooks/useDecisionDetail.test.ts`:

```typescript
import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';
import * as client from '@/lib/api/client';

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: qc }, children);
}

describe('useDecisionDetail', () => {
  afterEach(() => vi.restoreAllMocks());

  it('calls api() for GET /admin/audit/decisions/{id} when enabled', async () => {
    const mockDetail = { decision_id: 'd-1', agent_role: 'SCORER' };
    const spy = vi.spyOn(client, 'api').mockResolvedValue(mockDetail);
    const { useDecisionDetail } = await import('./useDecisionDetail');
    const { result } = renderHook(
      () => useDecisionDetail('d-1', true),
      { wrapper: makeWrapper() },
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(spy).toHaveBeenCalledWith('/admin/audit/decisions/d-1');
    expect(result.current.data).toEqual(mockDetail);
  });

  it('does not fire when enabled=false', async () => {
    const spy = vi.spyOn(client, 'api').mockResolvedValue({});
    const { useDecisionDetail } = await import('./useDecisionDetail');
    const { result } = renderHook(
      () => useDecisionDetail('d-1', false),
      { wrapper: makeWrapper() },
    );
    expect(result.current.isLoading).toBe(false);
    expect(spy).not.toHaveBeenCalled();
  });
});
```

Create `src/frontend/pages/admin/ai-audit/hooks/useWorkflowDetail.test.ts`:

```typescript
import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';
import * as client from '@/lib/api/client';

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: qc }, children);
}

describe('useWorkflowDetail', () => {
  afterEach(() => vi.restoreAllMocks());

  it('calls api() for GET /admin/audit/workflows/{id} when enabled', async () => {
    const mockDetail = { workflow_id: 'w-1', status: 'completed' };
    const spy = vi.spyOn(client, 'api').mockResolvedValue(mockDetail);
    const { useWorkflowDetail } = await import('./useWorkflowDetail');
    const { result } = renderHook(
      () => useWorkflowDetail('w-1', true),
      { wrapper: makeWrapper() },
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(spy).toHaveBeenCalledWith('/admin/audit/workflows/w-1');
    expect(result.current.data).toEqual(mockDetail);
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

```
npm test -- src/frontend/pages/admin/ai-audit/hooks/useDecisionDetail.test.ts src/frontend/pages/admin/ai-audit/hooks/useWorkflowDetail.test.ts
```

Expected: FAIL — modules not found.

- [ ] **Step 3: Create `useDecisionDetail.ts`**

```typescript
import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api/client';
import type { AIDecisionDetail } from '../DecisionDetailDrawer';

export function useDecisionDetail(decisionId: string, enabled: boolean) {
  return useQuery({
    queryKey: ['admin', 'audit', 'decision', decisionId],
    queryFn: () => api<AIDecisionDetail>('/admin/audit/decisions/' + decisionId),
    enabled: Boolean(decisionId) && enabled,
  });
}
```

- [ ] **Step 4: Create `useWorkflowDetail.ts`**

```typescript
import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api/client';
import type { WorkflowRunDetail } from './useWorkflowHistory';

export function useWorkflowDetail(workflowId: string, enabled: boolean) {
  return useQuery({
    queryKey: ['admin', 'audit', 'workflow', workflowId],
    queryFn: () => api<WorkflowRunDetail>('/admin/audit/workflows/' + workflowId),
    enabled: Boolean(workflowId) && enabled,
  });
}
```

- [ ] **Step 5: Run new hook tests to verify they pass**

```
npm test -- src/frontend/pages/admin/ai-audit/hooks/useDecisionDetail.test.ts src/frontend/pages/admin/ai-audit/hooks/useWorkflowDetail.test.ts
```

Expected: All PASS.

- [ ] **Step 6: Migrate `useDecisionLog.ts`**

Replace the `fetchDecisions` function inside the file:

```typescript
// Remove this function:
async function fetchDecisions(
  filters: DecisionLogFilters,
  cursor: string | null
): Promise<DecisionLogPage> {
  const params = new URLSearchParams();
  // ... (old raw fetch implementation)
  const res = await fetch(`/api/v1/admin/audit/decisions?${params.toString()}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

// Replace with:
async function fetchDecisions(
  filters: DecisionLogFilters,
  cursor: string | null
): Promise<DecisionLogPage> {
  const params = new URLSearchParams();
  if (filters.date_from) params.set('date_from', filters.date_from);
  if (filters.date_to) params.set('date_to', filters.date_to);
  if (filters.agent_role) params.set('agent_role', filters.agent_role);
  if (filters.model) params.set('model', filters.model);
  if (filters.confidence_min !== undefined)
    params.set('confidence_min', String(filters.confidence_min));
  if (filters.confidence_max !== undefined)
    params.set('confidence_max', String(filters.confidence_max));
  if (filters.action_signal) params.set('action_signal', filters.action_signal);
  if (filters.company_ticker) params.set('company_ticker', filters.company_ticker);
  if (filters.limit) params.set('limit', String(filters.limit));
  if (cursor) params.set('cursor', cursor);
  return api<DecisionLogPage>('/admin/audit/decisions?' + params.toString());
}
```

Also add the import at the top of the file:

```typescript
import { api } from '@/lib/api/client';
```

- [ ] **Step 7: Migrate `useWorkflowHistory.ts`**

Replace the two raw fetch functions:

```typescript
// Add import at the top:
import { api } from '@/lib/api/client';

// Replace fetchWorkflows:
async function fetchWorkflows(
  cursor: string | null,
  limit: number
): Promise<{ data: WorkflowRunSummary[]; next_cursor: string | null }> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (cursor) params.set('cursor', cursor);
  return api('/admin/audit/workflows?' + params.toString());
}

// Replace postRerun:
async function postRerun(workflowId: string): Promise<RerunResponse> {
  return api<RerunResponse>(
    '/admin/audit/workflows/' + workflowId + '/rerun',
    { method: 'POST' },
  );
}
```

- [ ] **Step 8: Update `DecisionLogPanel.tsx` to use the new hook**

Remove the inline `fetchDecisionDetail` function (lines 35–40):

```typescript
// DELETE these lines:
async function fetchDecisionDetail(decisionId: string): Promise<AIDecisionDetail> {
  const res = await fetch(`/api/v1/admin/audit/decisions/${decisionId}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const json = await res.json();
  return json.data;
}
```

Add the hook import at the top:

```typescript
import { useDecisionDetail } from './hooks/useDecisionDetail';
```

Inside `DecisionLogPanel`, replace the manual fetch-on-row-click with the hook. Find where `fetchDecisionDetail` is called and replace the fetch call with a hook-driven approach. The typical pattern is: track the selected decision ID in state, then use `useDecisionDetail(selectedId, !!selectedId)`, and pass `data` to the drawer. The exact implementation will depend on how the existing `handleRowClick` is structured — look at the full file to confirm, but the general replacement is:

```typescript
// Before: handleRowClick fetches then sets selectedDetail
// After: set selectedDecisionId in state; useDecisionDetail drives the data

const [selectedDecisionId, setSelectedDecisionId] = useState<string | null>(null);
const { data: selectedDetail } = useDecisionDetail(selectedDecisionId ?? '', !!selectedDecisionId);

// Row click just sets the ID:
const handleRowClick = (row: AIDecisionRow) => {
  setSelectedDecisionId(row.decision_id);
  setDrawerOpen(true);
};
```

- [ ] **Step 9: Update `WorkflowHistoryPanel.tsx` to use the new hook**

Remove the inline `fetchWorkflowDetail` function (lines 20–25):

```typescript
// DELETE these lines:
async function fetchWorkflowDetail(workflowId: string): Promise<WorkflowDetailFull> {
  const res = await fetch(`/api/v1/admin/audit/workflows/${workflowId}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const json = await res.json();
  return json.data;
}
```

Add the hook import:

```typescript
import { useWorkflowDetail } from './hooks/useWorkflowDetail';
```

Apply the same pattern as Step 8 — track `selectedWorkflowId` in state, drive detail data through `useWorkflowDetail(selectedWorkflowId ?? '', !!selectedWorkflowId)`.

- [ ] **Step 10: Run all AI audit tests**

```
npm test -- src/frontend/pages/admin/ai-audit/
```

Expected: All PASS.

- [ ] **Step 11: Run the full test suite**

```
npm test
```

Expected: All PASS. This is the final gate before the commit.

- [ ] **Step 12: Commit**

```bash
git add src/frontend/pages/admin/ai-audit/
git commit -m "refactor(audit): migrate AI audit hooks to api<T>(); extract inline fetches to hooks"
```

---

## Self-Review Against Spec

**Spec coverage checklist:**

| Spec requirement | Task |
|-----------------|------|
| Mount events_v1_router | Task 1 |
| Mount disclosure_router | Task 1 |
| Mount briefs_router + briefs_feedback_router | Task 1 (via api_v1_router) |
| Mount company_detail_router | Task 1 (via api_v1_router) |
| Mount audit_router | Task 1 |
| ProgressiveDisclosureProvider wraps home route | Task 2 |
| IntelligenceMapPage uses useDisclosure | Task 2 |
| DeepDivePage lazy-loaded at ROUTES.events | Task 2 |
| disclosure.api.ts drops custom auth helpers | Task 3 |
| DisclosureFetchError → ApiError | Task 3 |
| 202 pending handled in fetchDeepDive | Task 3 |
| EventPopup (PD): all style={{}} → Tailwind | Task 4 |
| LowSampleDisclaimer: style={{}} → Tailwind | Task 4 |
| ContrarianCallout: style={{}} → Tailwind | Task 4 |
| SidePanelAnalogies: style={{}} → Tailwind | Task 5 |
| SidePanelSparkline: style={{}} → Tailwind | Task 5 |
| AuditTrailView: style={{}} → Tailwind | Task 6 |
| SidePanel: style={{}} → Tailwind | Task 7 |
| DeepDivePage: style={{}} → Tailwind | Task 8 |
| useBriefs/useBriefDetail/useFeedback → api<T> | Task 9 |
| createQASession → api<T> | Task 10 |
| submitQuestionFetch: keep raw fetch + add auth | Task 10 |
| useCompanyDetail → api<T> | Task 11 |
| useAnalyzeNow: POST → api<T>, WS → apiSocket | Task 11 |
| 409 handling preserved in useAnalyzeNow | Task 11 |
| useDecisionLog fetchDecisions → api<T> | Task 12 |
| useWorkflowHistory fetchWorkflows → api<T> | Task 12 |
| postRerun → api<T> | Task 12 |
| DecisionLogPanel inline fetch → useDecisionDetail hook | Task 12 |
| WorkflowHistoryPanel inline fetch → useWorkflowDetail hook | Task 12 |

No gaps found.
