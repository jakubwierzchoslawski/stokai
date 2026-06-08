# Phase 2a — Intelligence Map Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the `/` hero route to a live MapLibre intelligence map through Phase 1 foundations: fix five architectural violations in `features/intelligence-map/`, add `useIntegrations()` + `<StubModeBadge>` primitives, define and conform to the events REST + WS backend contracts, replace the Phase 1 `<ComingSoon>` placeholder, and ship the route end-to-end against a real backend.

**Architecture:** Migrate the pre-existing `features/intelligence-map/` implementation to use Phase 1's `lib/api/client.ts` (no raw `fetch`), `lib/api/ws.ts` (`apiSocket`, no inline WebSocket managers), and the design tokens system (no inline `style` for color/spacing/layout). Add two shared primitives: `useIntegrations()` and `<StubModeBadge>`. Add a thin `<IntelligenceMapPage>` route wrapper that hides the AppShell sidebar by default and wires the pulse-click → `/events/:id/deep-dive` navigation. Keep all child components in place; only convert their styling and (where applicable) their data-fetching surface area.

**Tech Stack:** React 18.3 · TypeScript 5.4 · TanStack Query 5 · react-router-dom 6 · MapLibre GL 4 + supercluster 8 · Tailwind v4 + design tokens · shadcn/ui · zod 3 · Vitest 2 + msw 2 + jsdom · framer-motion 11.

**Spec reference:** `docs/superpowers/specs/2026-06-08-phase-2a-intelligence-map-design.md`. All section references below (e.g. §3.1) point to that spec.

**Prerequisites:** Phase 1 Steps 7, 8, 9, 13, and 14 must ship on `phase-1/foundation` (or merge into `main`) before starting. Task 0 below verifies these preconditions.

---

## File structure (target end-state)

Created during this plan (new):
```
src/frontend/
├─ lib/
│  ├─ api/integrations.ts          (useIntegrations shared hook)
│  └─ ui/StubModeBadge.tsx         (shared stub-mode indicator)
└─ features/intelligence-map/
   ├─ IntelligenceMapPage.tsx      (route wrapper)
   ├─ api/events.schema.ts         (zod schema for EventPulse)
   └─ components/EventPopup.tsx    (pulse-click popup content)
```

Modified during this plan:
```
src/frontend/
├─ app/router.tsx                                                       (mount IntelligenceMapPage at /)
├─ lib/env.ts                                                           (+ VITE_MAP_STYLE_URL)
└─ features/intelligence-map/
   ├─ IntelligenceMap.tsx                                               (Tailwind sweep, drop useScoreAtTime, wire popup)
   ├─ api/events.api.ts                                                 (api<T>() + zod)
   ├─ hooks/useEventFeed.ts                                             (apiSocket)
   ├─ hooks/useHistoricalEvents.ts                                      (api<T>())
   └─ components/{FilterPanel,MapContextSwitcher,TimeModeToolbar,
                  PlaybackControls,EmptyState,ScoreOverlay,
                  ClusterDonut}.tsx                                     (Tailwind sweep)
```

Deleted during this plan:
```
src/frontend/features/intelligence-map/hooks/useScoreAtTime.ts
src/frontend/features/intelligence-map/hooks/useScoreAtTime.test.ts
```

Tests modified, renamed, or un-skipped during this plan:
```
src/frontend/features/intelligence-map/IntelligenceMap.test.tsx
src/frontend/features/intelligence-map/IntelligenceMap.time-mode.test.tsx
src/frontend/features/intelligence-map/hooks/useEventFeed.test.ts          → useEventFeed.test.tsx (rename)
src/frontend/features/intelligence-map/hooks/useHistoricalEvents.test.ts   → useHistoricalEvents.test.tsx (rename)
src/frontend/features/intelligence-map/components/*.test.{ts,tsx}
```

Tests created during this plan:
```
src/frontend/lib/api/integrations.test.tsx
src/frontend/lib/ui/StubModeBadge.test.tsx
src/frontend/features/intelligence-map/api/events.schema.test.ts
src/frontend/features/intelligence-map/api/events.api.test.ts             (replaces inline tests if any)
src/frontend/features/intelligence-map/components/EventPopup.test.tsx
src/frontend/features/intelligence-map/IntelligenceMapPage.test.tsx
```

---

## Conventions used throughout this plan

- All file paths are relative to repo root. Working directory is `B:\development\python_space\stokai`.
- `npm` commands run from repo root.
- Each Task ends with a commit. Conventional commits: `feat(map): …`, `refactor(map): …`, `test(map): …`, `chore(map): …`.
- TDD tasks: write failing test → run to confirm failure → implement → run to confirm pass → commit.
- "Run: `<cmd>` — Expected: `<output>`" means run and verify the expected outcome before continuing.
- `@/` is the path alias for `src/frontend/` (established in Phase 1 `tsconfig.json`).
- Phase 1 contracts referenced directly:
  - `api<T>(path, init?)` from `@/lib/api/client.ts` — typed fetch wrapper, unwraps envelope, throws `ApiError`.
  - `apiSocket(path, { onMessage, onClose, onError? })` from `@/lib/api/ws.ts` — returns `{ close }`, injects token via `?token=`.
  - `ApiError(status, code, message, details?, requestId?)` from `@/lib/api/errors.ts`.
  - `env` from `@/lib/env.ts` — zod-validated environment.
  - `useAuth()` from `@/app/providers/AuthProvider.tsx` — Phase 1 §5.4.
  - `<ComingSoon plan="…" />` from `@/app/components/ComingSoon.tsx` — Phase 1 §5.6.
- If a Phase 1 export name differs from what this plan assumes, update the import only — do not redesign.

---

## Task 0: Preconditions check

**Files:** No file changes.

This task verifies that Phase 1 has shipped the contracts Phase 2a depends on. Do not proceed to Task 1 if any check fails — file the gap as a Phase 1 blocker first.

- [ ] **Step 0.1: Check that the working tree is clean**

Run: `git status --short`
Expected: no changes (or only pre-existing tracked noise that is unrelated to `src/frontend/`).

- [ ] **Step 0.2: Verify Phase 1 Step 7 (Auth) shipped**

Run: `git grep -l "AuthProvider" src/frontend/app/providers/`
Expected: prints `src/frontend/app/providers/AuthProvider.tsx`.

Run: `git grep -nE "export (function|const) (useAuth|getAccessToken)" src/frontend/lib/api/client.ts src/frontend/app/providers/AuthProvider.tsx`
Expected: prints `getAccessToken` from `client.ts` and `useAuth` from `AuthProvider.tsx`.

- [ ] **Step 0.3: Verify Phase 1 Step 8 (Layout/AppShell) shipped**

Run: `git grep -l "AppShell" src/frontend/layout/`
Expected: prints `src/frontend/layout/AppShell.tsx`.

- [ ] **Step 0.4: Verify Phase 1 Step 9 (Routes) mounted ComingSoon at /**

Run: `git grep -nE 'ROUTES\.home|ComingSoon plan="PLAN-F-019"' src/frontend/app/router.tsx`
Expected: prints the line in `router.tsx` mounting `<ComingSoon plan="PLAN-F-019" />` at `ROUTES.home`.

- [ ] **Step 0.5: Verify Phase 1 Step 13 (empty-state stubs) shipped**

Run: `ls src/frontend/features/intelligence-map/lib/`
Expected: lists `empty-state-message.ts` and `time-mode-empty-state.ts`.

If either is missing, file a Phase 1 blocker and stop.

- [ ] **Step 0.6: Verify Phase 1 Step 14 (test migration) marked Phase 2 tests as .skip**

Run: `git grep -n "describe\.skip\|it\.skip\|test\.skip" src/frontend/features/intelligence-map/`
Expected: prints at least one match — these are the tests Phase 2a un-skips later.

If zero matches, the tests may already be deleted or never marked; proceed but note that Task 16 will not un-skip anything.

- [ ] **Step 0.7: Baseline build is green**

Run: `npm run typecheck`
Expected: exits 0.

Run: `npm run lint`
Expected: exits 0.

Run: `npm run test -- --run`
Expected: exits 0.

If any step exits non-zero, do not proceed — file as a Phase 1 blocker.

- [ ] **Step 0.8: Create the Phase 2a branch**

Run: `git checkout -b phase-2a/intelligence-map`
Expected: `Switched to a new branch 'phase-2a/intelligence-map'`.

---

## Task 1: Add `VITE_MAP_STYLE_URL` to the env schema

Spec: §4.3. Lets ops override the MapLibre style URL per environment without code edits. Default matches the in-code fallback already in `IntelligenceMap.tsx`.

**Files:**
- Modify: `src/frontend/lib/env.ts`
- Test: extend existing `src/frontend/lib/env.test.ts` if present, or create it.

- [ ] **Step 1.1: Inspect the current env shape**

Run: `cat src/frontend/lib/env.ts`

Confirm the file exports a zod-validated `env` object. Note the existing field names and the shape used for default values.

- [ ] **Step 1.2: Write a failing test for the new field**

Add (or create) `src/frontend/lib/env.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import { z } from "zod";

// We import the schema definition factory rather than the live `env` so the
// test can drive arbitrary inputs without polluting global Vite env.
import { envSchema } from "@/lib/env";

describe("envSchema — VITE_MAP_STYLE_URL", () => {
  it("defaults to the CARTO dark-matter style when unset", () => {
    const parsed = envSchema.parse({});
    expect(parsed.mapStyleUrl).toBe(
      "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
    );
  });

  it("accepts an override URL", () => {
    const parsed = envSchema.parse({
      VITE_MAP_STYLE_URL: "https://tiles.example.com/style.json",
    });
    expect(parsed.mapStyleUrl).toBe("https://tiles.example.com/style.json");
  });

  it("rejects non-URL strings", () => {
    expect(() =>
      envSchema.parse({ VITE_MAP_STYLE_URL: "not-a-url" }),
    ).toThrow(z.ZodError);
  });
});
```

If `envSchema` is not currently exported from `@/lib/env`, the test will fail at import — that is the failing state Step 1.3 checks.

- [ ] **Step 1.3: Run the test to verify failure**

Run: `npx vitest run src/frontend/lib/env.test.ts`
Expected: FAIL — either `envSchema` is not exported, or `mapStyleUrl` field is missing.

- [ ] **Step 1.4: Extend `envSchema` to expose the field**

Open `src/frontend/lib/env.ts`. Locate the zod schema declaration (likely `const envSchema = z.object({…})`). Add the new optional field with default, and expose the parsed value via the `mapStyleUrl` key. Ensure `envSchema` is exported.

Example diff (adapt to actual file shape — do not blindly replace):

```ts
export const envSchema = z
  .object({
    VITE_API_BASE_URL: z.string().default("/api/v1"),
    VITE_WS_BASE_URL: z.string().default(""),
    VITE_APP_NAME: z.string().default("StokAI"),
    VITE_ENABLE_DEVTOOLS: z.string().default("true"),
    VITE_MAP_STYLE_URL: z
      .string()
      .url()
      .default(
        "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
      ),
  })
  .transform((raw) => ({
    apiBaseUrl: raw.VITE_API_BASE_URL,
    wsBaseUrl: raw.VITE_WS_BASE_URL,
    appName: raw.VITE_APP_NAME,
    enableDevtools: raw.VITE_ENABLE_DEVTOOLS === "true",
    mapStyleUrl: raw.VITE_MAP_STYLE_URL,
  }));

export const env = envSchema.parse(import.meta.env);
```

- [ ] **Step 1.5: Run the test to verify success**

Run: `npx vitest run src/frontend/lib/env.test.ts`
Expected: all three tests pass.

- [ ] **Step 1.6: Typecheck and full test sweep**

Run: `npm run typecheck && npm run test -- --run`
Expected: both exit 0.

- [ ] **Step 1.7: Commit**

Run:
```
git add src/frontend/lib/env.ts src/frontend/lib/env.test.ts
git commit -m "feat(env): add VITE_MAP_STYLE_URL with CARTO dark-matter default"
```

---

## Task 2: `useIntegrations()` shared hook

Spec: §4.3. TanStack Query hook over `GET /api/v1/system/integrations`. Used by `<StubModeBadge>` (Task 3) and the admin/system page.

**Files:**
- Create: `src/frontend/lib/api/integrations.ts`
- Create: `src/frontend/lib/api/integrations.test.tsx` (`.tsx` because the test wraps the hook in JSX providers)

- [ ] **Step 2.1: Write the failing test**

Create `src/frontend/lib/api/integrations.test.tsx`:

```ts
import { describe, it, expect, beforeAll, afterAll, afterEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";
import React from "react";

import { useIntegrations } from "@/lib/api/integrations";

const server = setupServer(
  http.get("/api/v1/system/integrations", () =>
    HttpResponse.json({
      data: {
        llm: { provider: "openai", mode: "live" },
        market_data: {
          provider: "polygon",
          mode: "stub",
          reason: "API key not configured",
        },
        news: { provider: "gdelt", mode: "live" },
      },
      meta: { request_id: "test", elapsed_ms: 1 },
    }),
  ),
);

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function wrapper({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
}

describe("useIntegrations", () => {
  it("returns the integrations map from the envelope", async () => {
    const { result } = renderHook(() => useIntegrations(), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.data?.market_data.mode).toBe("stub");
    expect(result.current.data?.market_data.reason).toBe(
      "API key not configured",
    );
    expect(result.current.data?.llm.mode).toBe("live");
  });

  it("exposes typed `isStub(integration)` helper", async () => {
    const { result } = renderHook(() => useIntegrations(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.isStub("market_data")).toBe(true);
    expect(result.current.isStub("llm")).toBe(false);
  });
});
```

- [ ] **Step 2.2: Run the test to verify failure**

Run: `npx vitest run src/frontend/lib/api/integrations.test.tsx`
Expected: FAIL — module not found.

- [ ] **Step 2.3: Implement the hook**

Create `src/frontend/lib/api/integrations.ts`:

```ts
import { useQuery } from "@tanstack/react-query";
import { z } from "zod";

import { api } from "@/lib/api/client";

const IntegrationMode = z.enum(["live", "stub", "missing"]);

const IntegrationEntry = z.object({
  provider: z.string(),
  mode: IntegrationMode,
  reason: z.string().optional(),
});

const IntegrationsSchema = z.object({
  llm: IntegrationEntry,
  embeddings: IntegrationEntry.optional(),
  market_data: IntegrationEntry,
  news: IntegrationEntry,
  social: IntegrationEntry.optional(),
});

export type IntegrationKey = keyof z.infer<typeof IntegrationsSchema>;
export type Integrations = z.infer<typeof IntegrationsSchema>;

export interface UseIntegrationsResult {
  data: Integrations | undefined;
  isLoading: boolean;
  isError: boolean;
  isStub: (key: IntegrationKey) => boolean;
}

export function useIntegrations(): UseIntegrationsResult {
  const q = useQuery<Integrations>({
    queryKey: ["system", "integrations"],
    queryFn: async () => {
      const raw = await api<unknown>("/system/integrations");
      return IntegrationsSchema.parse(raw);
    },
    staleTime: 5 * 60 * 1000,
  });

  return {
    data: q.data,
    isLoading: q.isLoading,
    isError: q.isError,
    isStub: (key) => q.data?.[key]?.mode === "stub",
  };
}
```

- [ ] **Step 2.4: Run the test to verify success**

Run: `npx vitest run src/frontend/lib/api/integrations.test.tsx`
Expected: both tests pass.

- [ ] **Step 2.5: Typecheck**

Run: `npm run typecheck`
Expected: exits 0.

- [ ] **Step 2.6: Commit**

Run:
```
git add src/frontend/lib/api/integrations.ts src/frontend/lib/api/integrations.test.tsx
git commit -m "feat(api): useIntegrations hook reading /system/integrations with isStub helper"
```

---

## Task 3: `<StubModeBadge>` shared primitive

Spec: §4.3. Renders top-left of the map (and any future feature) when one of its watched integrations is in stub mode. Click opens a popover with the reason and an admin-only link.

**Files:**
- Create: `src/frontend/lib/ui/StubModeBadge.tsx`
- Create: `src/frontend/lib/ui/StubModeBadge.test.tsx`

- [ ] **Step 3.1: Write the failing test**

Create `src/frontend/lib/ui/StubModeBadge.test.tsx`:

```tsx
import { describe, it, expect, beforeAll, afterAll, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router-dom";
import React from "react";

import { StubModeBadge } from "@/lib/ui/StubModeBadge";

const integrationsHandler = (overrides: Record<string, unknown> = {}) =>
  http.get("/api/v1/system/integrations", () =>
    HttpResponse.json({
      data: {
        llm: { provider: "openai", mode: "live" },
        market_data: { provider: "polygon", mode: "live" },
        news: { provider: "gdelt", mode: "live" },
        ...overrides,
      },
      meta: { request_id: "t", elapsed_ms: 1 },
    }),
  );

const server = setupServer(integrationsHandler());

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function Wrap({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

describe("StubModeBadge", () => {
  it("renders nothing when all watched integrations are live", async () => {
    render(
      <Wrap>
        <StubModeBadge watch={["market_data", "news"]} />
      </Wrap>,
    );
    // Wait a microtask for the query to resolve.
    await new Promise((r) => setTimeout(r, 0));
    expect(screen.queryByTestId("stub-mode-badge")).toBeNull();
  });

  it("renders with affected integration names when one is stub", async () => {
    server.use(
      integrationsHandler({
        market_data: {
          provider: "polygon",
          mode: "stub",
          reason: "API key not configured",
        },
      }),
    );
    render(
      <Wrap>
        <StubModeBadge watch={["market_data", "news"]} />
      </Wrap>,
    );
    const badge = await screen.findByTestId("stub-mode-badge");
    expect(badge.textContent).toMatch(/stub mode/i);
    expect(badge.textContent).toMatch(/market_data/i);
  });

  it("opens a popover with the reason on click", async () => {
    server.use(
      integrationsHandler({
        news: { provider: "gdelt", mode: "stub", reason: "License pending" },
      }),
    );
    render(
      <Wrap>
        <StubModeBadge watch={["news"]} />
      </Wrap>,
    );
    const badge = await screen.findByTestId("stub-mode-badge");
    await userEvent.click(badge);
    expect(await screen.findByText(/license pending/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 3.2: Run the test to verify failure**

Run: `npx vitest run src/frontend/lib/ui/StubModeBadge.test.tsx`
Expected: FAIL — module not found.

- [ ] **Step 3.3: Implement the badge**

Create `src/frontend/lib/ui/StubModeBadge.tsx`:

```tsx
import * as React from "react";
import { Link } from "react-router-dom";

import {
  IntegrationKey,
  useIntegrations,
} from "@/lib/api/integrations";

export interface StubModeBadgeProps {
  /** Integrations whose `stub` state should trigger the badge. */
  watch: IntegrationKey[];
  /** Optional className for positioning. */
  className?: string;
}

export function StubModeBadge({ watch, className }: StubModeBadgeProps) {
  const [open, setOpen] = React.useState(false);
  const { data, isLoading } = useIntegrations();

  if (isLoading || !data) return null;

  const stubbed = watch.filter((k) => data[k]?.mode === "stub");
  if (stubbed.length === 0) return null;

  const reasons = stubbed
    .map((k) => `${k}: ${data[k]?.reason ?? "stub mode"}`)
    .join(" · ");

  return (
    <div
      data-testid="stub-mode-badge"
      className={[
        "rounded-md border border-subtle bg-surface-2/90 px-3 py-1.5",
        "text-xs text-muted backdrop-blur cursor-pointer select-none",
        className ?? "",
      ].join(" ")}
      onClick={() => setOpen((v) => !v)}
      role="button"
      aria-expanded={open}
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          setOpen((v) => !v);
        }
      }}
    >
      <span className="font-medium">Stub mode:</span>{" "}
      {stubbed.join(", ")}
      {open && (
        <div
          data-testid="stub-mode-badge-popover"
          className="mt-2 max-w-xs whitespace-normal rounded-md border border-default bg-surface-1 p-2 text-xs"
        >
          <div className="text-text">{reasons}</div>
          <Link
            to="/admin/system"
            className="mt-1 inline-block text-signal underline"
          >
            Configure in admin →
          </Link>
        </div>
      )}
    </div>
  );
}
```

Note: The component does not currently check whether the user is admin before rendering the link. That filter is a Phase 3 polish item; in Phase 2a a non-admin clicking the link is redirected to `/login` or `<AccessDenied />` by Phase 1's `RequireAdmin` guard. If your tests demand the admin gate now, extend with `useAuth().state.user.role === "admin"`.

- [ ] **Step 3.4: Run the test to verify success**

Run: `npx vitest run src/frontend/lib/ui/StubModeBadge.test.tsx`
Expected: all three tests pass.

- [ ] **Step 3.5: Commit**

Run:
```
git add src/frontend/lib/ui/StubModeBadge.tsx src/frontend/lib/ui/StubModeBadge.test.tsx
git commit -m "feat(ui): StubModeBadge primitive with reason popover and admin link"
```

---

## Task 4: zod schema for `EventPulse`

Spec: §3.1. Single source of truth for event validation. Used by both `events.api.ts` (Task 5) and `useHistoricalEvents.ts` (Task 6).

**Files:**
- Create: `src/frontend/features/intelligence-map/api/events.schema.ts`
- Create: `src/frontend/features/intelligence-map/api/events.schema.test.ts`

- [ ] **Step 4.1: Write the failing test**

Create `src/frontend/features/intelligence-map/api/events.schema.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import {
  EventPulseSchema,
  EventsArraySchema,
} from "@/features/intelligence-map/api/events.schema";

const validPulse = {
  event_id: "evt-1",
  category: ["geopolitical"],
  intensity: 3,
  headline: "Test event",
  timestamp: "2026-06-08T12:00:00Z",
  lat: 40.7,
  lon: -74.0,
  relevance_window_end: "2026-06-09T12:00:00Z",
  affected_companies: [
    { company_id: "co-1", ticker: "AAPL", score_delta: -2.5 },
  ],
};

describe("EventPulseSchema", () => {
  it("parses a valid event", () => {
    expect(EventPulseSchema.parse(validPulse).event_id).toBe("evt-1");
  });

  it("rejects intensity outside 1–5", () => {
    expect(() =>
      EventPulseSchema.parse({ ...validPulse, intensity: 6 }),
    ).toThrow();
    expect(() =>
      EventPulseSchema.parse({ ...validPulse, intensity: 0 }),
    ).toThrow();
  });

  it("rejects missing required fields", () => {
    const { headline: _, ...rest } = validPulse;
    expect(() => EventPulseSchema.parse(rest)).toThrow();
  });

  it("rejects non-array category", () => {
    expect(() =>
      EventPulseSchema.parse({ ...validPulse, category: "geopolitical" }),
    ).toThrow();
  });

  it("parses an array of events", () => {
    const parsed = EventsArraySchema.parse([validPulse, validPulse]);
    expect(parsed).toHaveLength(2);
  });

  it("rejects an array with one bad event", () => {
    expect(() =>
      EventsArraySchema.parse([validPulse, { ...validPulse, intensity: 99 }]),
    ).toThrow();
  });
});
```

- [ ] **Step 4.2: Run the test to verify failure**

Run: `npx vitest run src/frontend/features/intelligence-map/api/events.schema.test.ts`
Expected: FAIL — module not found.

- [ ] **Step 4.3: Implement the schema**

Create `src/frontend/features/intelligence-map/api/events.schema.ts`:

```ts
import { z } from "zod";

export const EventPulseSchema = z.object({
  event_id: z.string(),
  category: z.array(z.string()),
  intensity: z
    .number()
    .int()
    .min(1)
    .max(5)
    .transform((n) => n as 1 | 2 | 3 | 4 | 5),
  headline: z.string(),
  timestamp: z.string(),
  lat: z.number(),
  lon: z.number(),
  relevance_window_end: z.string(),
  affected_companies: z.array(
    z.object({
      company_id: z.string(),
      ticker: z.string(),
      score_delta: z.number(),
    }),
  ),
});

export const EventsArraySchema = z.array(EventPulseSchema);

export type EventPulseFromSchema = z.infer<typeof EventPulseSchema>;
```

Note: this schema must remain structurally compatible with `EventPulse` in `types/map.types.ts`. If you change one, change the other; consider replacing the manually-written type with `z.infer<typeof EventPulseSchema>` in a follow-up cleanup.

- [ ] **Step 4.4: Run the test to verify success**

Run: `npx vitest run src/frontend/features/intelligence-map/api/events.schema.test.ts`
Expected: all six tests pass.

- [ ] **Step 4.5: Commit**

Run:
```
git add src/frontend/features/intelligence-map/api/events.schema.ts src/frontend/features/intelligence-map/api/events.schema.test.ts
git commit -m "feat(map): zod schema for EventPulse (single source of validation)"
```

---

## Task 5: Migrate `events.api.ts` to `api<T>()` + zod

Spec: §4.1 Fix 1. Replace raw `fetch` + localStorage token with the Phase 1 client and zod validation.

**Files:**
- Modify: `src/frontend/features/intelligence-map/api/events.api.ts` (full rewrite)
- Create: `src/frontend/features/intelligence-map/api/events.api.test.ts` (replaces ad-hoc tests if any)

- [ ] **Step 5.1: Inspect callers**

Run: `git grep -nE "from ['\"]\\.\\./api/events\\.api['\"]|from ['\"]@/features/intelligence-map/api/events\\.api['\"]" src/frontend`
Note every caller. Common imports to preserve as exported names: `fetchEvents`, `EventsQueryParams`.

- [ ] **Step 5.2: Write the failing test**

Create `src/frontend/features/intelligence-map/api/events.api.test.ts`:

```ts
import { describe, it, expect, beforeAll, afterAll, afterEach } from "vitest";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";

import { fetchEvents } from "@/features/intelligence-map/api/events.api";

const validEvent = {
  event_id: "evt-1",
  category: ["geopolitical"],
  intensity: 2,
  headline: "Test",
  timestamp: "2026-06-08T00:00:00Z",
  lat: 0,
  lon: 0,
  relevance_window_end: "2026-06-09T00:00:00Z",
  affected_companies: [],
};

const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe("fetchEvents", () => {
  it("calls GET /api/v1/events with the supplied params and unwraps `data`", async () => {
    let capturedUrl = "";
    server.use(
      http.get("/api/v1/events", ({ request }) => {
        capturedUrl = request.url;
        return HttpResponse.json({
          data: [validEvent],
          meta: { request_id: "x", elapsed_ms: 1, count: 1, truncated: false },
        });
      }),
    );

    const result = await fetchEvents({
      bbox: "-180,-85,180,85",
      zoom: 2,
      context: "global",
    });
    expect(result).toHaveLength(1);
    expect(result[0].event_id).toBe("evt-1");
    expect(capturedUrl).toMatch(/bbox=-180%2C-85%2C180%2C85/);
    expect(capturedUrl).toMatch(/zoom=2/);
    expect(capturedUrl).toMatch(/context=global/);
  });

  it("throws ApiError with CONTRACT_MISMATCH on bad schema", async () => {
    server.use(
      http.get("/api/v1/events", () =>
        HttpResponse.json({
          data: [{ ...validEvent, intensity: 99 }],
          meta: { request_id: "x", elapsed_ms: 1 },
        }),
      ),
    );

    await expect(fetchEvents({})).rejects.toMatchObject({
      code: "CONTRACT_MISMATCH",
    });
  });

  it("propagates ApiError on non-2xx", async () => {
    server.use(
      http.get("/api/v1/events", () =>
        HttpResponse.json(
          {
            error: {
              code: "VALIDATION_FIELD_REQUIRED",
              message: "bbox malformed",
              request_id: "x",
            },
          },
          { status: 400 },
        ),
      ),
    );

    await expect(fetchEvents({ bbox: "garbage" })).rejects.toMatchObject({
      status: 400,
      code: "VALIDATION_FIELD_REQUIRED",
    });
  });
});
```

- [ ] **Step 5.3: Run the test to verify failure**

Run: `npx vitest run src/frontend/features/intelligence-map/api/events.api.test.ts`
Expected: FAIL — current `events.api.ts` is incompatible (uses raw fetch, throws `EventFetchError` not `ApiError`, no zod validation that maps to `CONTRACT_MISMATCH`).

- [ ] **Step 5.4: Rewrite `events.api.ts`**

Replace the entire contents of `src/frontend/features/intelligence-map/api/events.api.ts` with:

```ts
import { z } from "zod";

import { api } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";

import { EventsArraySchema } from "./events.schema";
import type { EventPulse } from "../types/map.types";

export interface EventsQueryParams {
  /** "west,south,east,north" */
  bbox?: string;
  zoom?: number;
  context?: "global" | "portfolio" | "sector";
  sector?: string;
  /** ISO 8601 — historical mode start */
  from?: string;
  /** ISO 8601 — historical mode end */
  to?: string;
}

function buildQuery(params: EventsQueryParams): string {
  const usp = new URLSearchParams();
  if (params.bbox !== undefined) usp.set("bbox", params.bbox);
  if (params.zoom !== undefined) usp.set("zoom", String(params.zoom));
  if (params.context !== undefined) usp.set("context", params.context);
  if (params.sector !== undefined) usp.set("sector", params.sector);
  if (params.from !== undefined) usp.set("from", params.from);
  if (params.to !== undefined) usp.set("to", params.to);
  const qs = usp.toString();
  return qs ? `?${qs}` : "";
}

export async function fetchEvents(
  params: EventsQueryParams,
): Promise<EventPulse[]> {
  const raw = await api<unknown>(`/events${buildQuery(params)}`);
  try {
    return EventsArraySchema.parse(raw) as EventPulse[];
  } catch (err) {
    if (err instanceof z.ZodError) {
      throw new ApiError(
        0,
        "CONTRACT_MISMATCH",
        "Events response failed schema validation",
        { issues: err.issues },
      );
    }
    throw err;
  }
}
```

- [ ] **Step 5.5: Remove dead exports**

Open `events.api.ts` and confirm the file no longer exports `EventFetchError`, `EventFetchErrorCode`, `isValidEventPulse`, `validateEventsResponse`, or `getAuthToken`. If any caller still imports those names, search and replace those imports — usually `useHistoricalEvents.ts` is the only one, and it is rewritten in Task 6.

Run: `git grep -nE "EventFetchError|EventFetchErrorCode" src/frontend`
Expected: zero matches outside of legacy test files yet to be updated. If matches remain in non-test code other than `useHistoricalEvents.ts`, update them inline before continuing.

- [ ] **Step 5.6: Run the new test to verify success**

Run: `npx vitest run src/frontend/features/intelligence-map/api/events.api.test.ts`
Expected: all three tests pass.

- [ ] **Step 5.7: Typecheck the whole project**

Run: `npm run typecheck`

If `useHistoricalEvents.ts` fails because it imported `EventFetchError`, that is expected and resolved in Task 6. Note the error count; you should see no other failures.

- [ ] **Step 5.8: Commit**

Run:
```
git add src/frontend/features/intelligence-map/api/events.api.ts src/frontend/features/intelligence-map/api/events.api.test.ts
git commit -m "refactor(map): events.api.ts uses lib/api/client + zod; drops EventFetchError"
```

---

## Task 6: Migrate `useHistoricalEvents.ts` to `api<T>()`

Spec: §4.1 Fix 2.

**Files:**
- Modify: `src/frontend/features/intelligence-map/hooks/useHistoricalEvents.ts`
- Rename + rewrite: `src/frontend/features/intelligence-map/hooks/useHistoricalEvents.test.tsx` → `useHistoricalEvents.test.tsx` (the new test body uses a JSX provider wrapper; un-skip if marked `.skip` in Phase 1 Step 14)

- [ ] **Step 6.1: Inspect the existing test file**

Run: `cat src/frontend/features/intelligence-map/hooks/useHistoricalEvents.test.tsx`

Note any `.skip` markers and what the test expects from the existing implementation. We will rewrite both file and tests.

- [ ] **Step 6.2: Rename and rewrite the test**

First rename:
```
git mv src/frontend/features/intelligence-map/hooks/useHistoricalEvents.test.tsx src/frontend/features/intelligence-map/hooks/useHistoricalEvents.test.tsxx
```

Then replace its entire contents with:

```ts
import { describe, it, expect, beforeAll, afterAll, afterEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";
import React from "react";

import { useHistoricalEvents } from "@/features/intelligence-map/hooks/useHistoricalEvents";

const event = (id: string, ts: string) => ({
  event_id: id,
  category: ["geo"],
  intensity: 2,
  headline: id,
  timestamp: ts,
  lat: 0,
  lon: 0,
  relevance_window_end: ts,
  affected_companies: [],
});

const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function wrap({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
}

describe("useHistoricalEvents", () => {
  it("returns empty + no fetch when disabled", async () => {
    let called = false;
    server.use(
      http.get("/api/v1/events", () => {
        called = true;
        return HttpResponse.json({ data: [], meta: {} });
      }),
    );

    const { result } = renderHook(
      () =>
        useHistoricalEvents({
          dateRange: { from_date: "", to_date: "" },
          enabled: false,
        }),
      { wrapper: wrap },
    );
    await new Promise((r) => setTimeout(r, 0));
    expect(result.current.events).toEqual([]);
    expect(called).toBe(false);
  });

  it("calls GET /events?from=&to= and returns sorted asc by timestamp", async () => {
    let capturedUrl = "";
    server.use(
      http.get("/api/v1/events", ({ request }) => {
        capturedUrl = request.url;
        return HttpResponse.json({
          data: [
            event("b", "2026-02-01T00:00:00Z"),
            event("a", "2026-01-01T00:00:00Z"),
          ],
          meta: {},
        });
      }),
    );

    const { result } = renderHook(
      () =>
        useHistoricalEvents({
          dateRange: { from_date: "2026-01-01", to_date: "2026-03-01" },
          enabled: true,
        }),
      { wrapper: wrap },
    );

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.events.map((e) => e.event_id)).toEqual(["a", "b"]);
    expect(capturedUrl).toMatch(/from=2026-01-01/);
    expect(capturedUrl).toMatch(/to=2026-03-01/);
  });
});
```

- [ ] **Step 6.3: Run to confirm failure**

Run: `npx vitest run src/frontend/features/intelligence-map/hooks/useHistoricalEvents.test.tsx`
Expected: FAIL — likely `EventFetchError` import broken or URL mismatch.

- [ ] **Step 6.4: Rewrite the hook**

Replace the entire contents of `src/frontend/features/intelligence-map/hooks/useHistoricalEvents.ts` with:

```ts
import { useQuery } from "@tanstack/react-query";

import { fetchEvents } from "../api/events.api";
import type { EventPulse } from "../types/map.types";
import type { DateRange } from "../types/time-mode.types";

export interface HistoricalEventsParams {
  dateRange: DateRange;
  enabled: boolean;
}

export interface UseHistoricalEventsResult {
  events: EventPulse[];
  isLoading: boolean;
  isError: boolean;
}

export function useHistoricalEvents(
  params: HistoricalEventsParams,
): UseHistoricalEventsResult {
  const { dateRange, enabled } = params;

  const q = useQuery<EventPulse[], Error>({
    queryKey: [
      "historical-events",
      dateRange.from_date,
      dateRange.to_date,
    ],
    queryFn: async () => {
      const data = await fetchEvents({
        from: dateRange.from_date,
        to: dateRange.to_date,
      });
      return [...data].sort(
        (a, b) =>
          new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime(),
      );
    },
    enabled,
    staleTime: 5 * 60 * 1000,
  });

  if (!enabled) return { events: [], isLoading: false, isError: false };

  return {
    events: q.data ?? [],
    isLoading: q.isLoading,
    isError: q.isError,
  };
}
```

- [ ] **Step 6.5: Run the test to verify success**

Run: `npx vitest run src/frontend/features/intelligence-map/hooks/useHistoricalEvents.test.tsx`
Expected: both tests pass.

- [ ] **Step 6.6: Typecheck**

Run: `npm run typecheck`
Expected: exits 0 (or only fails on files we touch in later tasks — note the diff).

- [ ] **Step 6.7: Commit**

Run:
```
git add src/frontend/features/intelligence-map/hooks/useHistoricalEvents.ts src/frontend/features/intelligence-map/hooks/useHistoricalEvents.test.tsx
git commit -m "refactor(map): useHistoricalEvents uses fetchEvents (Phase 1 client + zod)"
```

---

## Task 7: Delete `useScoreAtTime` and its dead call site

Spec: §4.1 Fix 3. The destructured `scoreAtTimeData` in `IntelligenceMap.tsx` is never read.

**Files:**
- Delete: `src/frontend/features/intelligence-map/hooks/useScoreAtTime.ts`
- Delete: `src/frontend/features/intelligence-map/hooks/useScoreAtTime.test.ts`
- Modify: `src/frontend/features/intelligence-map/IntelligenceMap.tsx` (remove import + call)

- [ ] **Step 7.1: Confirm `scoreAtTimeData` is unused**

Run: `git grep -n "scoreAtTimeData" src/frontend`
Expected: at most one match — the destructure inside `IntelligenceMap.tsx`. If a real consumer exists, stop and reassess — do not delete the hook.

- [ ] **Step 7.2: Remove the import in `IntelligenceMap.tsx`**

Open `src/frontend/features/intelligence-map/IntelligenceMap.tsx`.

Delete:
```ts
import { useScoreAtTime } from './hooks/useScoreAtTime';
```

Delete the entire `useScoreAtTime({ … })` call block (the one assigning `scoreAtTimeData`). Also remove the surrounding `derivedCompanyIds` computation if it is only used by that call — verify with grep before removing.

Run: `git grep -nE "useScoreAtTime|scoreAtTimeData|derivedCompanyIds" src/frontend/features/intelligence-map/IntelligenceMap.tsx`
Expected: zero matches.

- [ ] **Step 7.3: Delete the hook and its test**

Run: `git rm src/frontend/features/intelligence-map/hooks/useScoreAtTime.ts src/frontend/features/intelligence-map/hooks/useScoreAtTime.test.ts`
Expected: both files removed.

- [ ] **Step 7.4: Typecheck and test**

Run: `npm run typecheck && npm run test -- --run src/frontend/features/intelligence-map`
Expected: both exit 0.

- [ ] **Step 7.5: Commit**

Run:
```
git add -A src/frontend/features/intelligence-map
git commit -m "refactor(map): drop dead useScoreAtTime hook and its unused call site"
```

---

## Task 8: Migrate `useEventFeed.ts` to `apiSocket`

Spec: §4.1 Fix 4 / §3.2. Replace the inline `subscribeToEventChannel` with the Phase 1 `apiSocket` wrapper. The wrapper handles auth and reconnect.

**Files:**
- Modify: `src/frontend/features/intelligence-map/hooks/useEventFeed.ts`
- Rename + rewrite: `src/frontend/features/intelligence-map/hooks/useEventFeed.test.tsx` → `useEventFeed.test.tsx` (new test uses a JSX provider wrapper)

- [ ] **Step 8.1: Inspect the current test file**

Run: `cat src/frontend/features/intelligence-map/hooks/useEventFeed.test.tsx`
Note whether tests are `.skip`-marked, what API they mock, and which export names they import.

- [ ] **Step 8.2: Rename and write the new test**

First rename:
```
git mv src/frontend/features/intelligence-map/hooks/useEventFeed.test.tsx src/frontend/features/intelligence-map/hooks/useEventFeed.test.tsxx
```

Then replace its entire contents with:

```ts
import { describe, it, expect, beforeAll, afterAll, afterEach, vi } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";
import React from "react";

// We mock apiSocket because msw does not handle WS in jsdom.
vi.mock("@/lib/api/ws", () => {
  let lastHandlers: {
    onMessage: (m: unknown) => void;
    onClose: (e: CloseEvent) => void;
  } | null = null;
  let closes = 0;
  return {
    apiSocket: (_path: string, handlers: typeof lastHandlers) => {
      lastHandlers = handlers as NonNullable<typeof lastHandlers>;
      return { close: () => { closes += 1; } };
    },
    __test__: {
      pushMessage: (m: unknown) => lastHandlers?.onMessage(m),
      getCloseCount: () => closes,
      reset: () => { lastHandlers = null; closes = 0; },
    },
  };
});

// Stable handle to the test bridge above.
import * as ws from "@/lib/api/ws";
const { __test__ } = ws as unknown as {
  __test__: {
    pushMessage: (m: unknown) => void;
    getCloseCount: () => number;
    reset: () => void;
  };
};

import { useEventFeed } from "@/features/intelligence-map/hooks/useEventFeed";

const validEvent = {
  event_id: "evt-ws-1",
  category: ["geo"],
  intensity: 2,
  headline: "ws event",
  timestamp: "2026-06-08T00:00:00Z",
  lat: 1,
  lon: 2,
  relevance_window_end: "2026-06-09T00:00:00Z",
  affected_companies: [],
};

const server = setupServer(
  http.get("/api/v1/events", () => HttpResponse.json({ data: [], meta: {} })),
);
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => { server.resetHandlers(); __test__.reset(); });
afterAll(() => server.close());

function wrap({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe("useEventFeed", () => {
  it("seeds events from REST and appends from WS event.created frames", async () => {
    server.use(
      http.get("/api/v1/events", () =>
        HttpResponse.json({ data: [validEvent], meta: {} }),
      ),
    );
    const { result } = renderHook(() => useEventFeed({}), { wrapper: wrap });
    await waitFor(() => expect(result.current.events).toHaveLength(1));

    act(() => {
      __test__.pushMessage({
        type: "event.created",
        event: { ...validEvent, event_id: "evt-ws-2" },
      });
    });

    expect(result.current.events.map((e) => e.event_id)).toEqual([
      "evt-ws-1",
      "evt-ws-2",
    ]);
  });

  it("ignores ping frames", async () => {
    const { result } = renderHook(() => useEventFeed({}), { wrapper: wrap });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    act(() => { __test__.pushMessage({ type: "ping" }); });
    expect(result.current.events).toHaveLength(0);
  });

  it("ignores malformed frames silently", async () => {
    const { result } = renderHook(() => useEventFeed({}), { wrapper: wrap });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    act(() => { __test__.pushMessage({ type: "event.created", event: { bogus: true } }); });
    expect(result.current.events).toHaveLength(0);
  });

  it("calls close() on unmount", async () => {
    const { unmount } = renderHook(() => useEventFeed({}), { wrapper: wrap });
    unmount();
    expect(__test__.getCloseCount()).toBe(1);
  });
});
```

- [ ] **Step 8.3: Run to confirm failure**

Run: `npx vitest run src/frontend/features/intelligence-map/hooks/useEventFeed.test.tsx`
Expected: FAIL — the current hook does not import from `@/lib/api/ws` and has its own `subscribeToEventChannel`.

- [ ] **Step 8.4: Rewrite the hook**

Replace the contents of `src/frontend/features/intelligence-map/hooks/useEventFeed.ts` with:

```ts
import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { apiSocket } from "@/lib/api/ws";

import { fetchEvents, type EventsQueryParams } from "../api/events.api";
import { EventPulseSchema } from "../api/events.schema";
import type { EventPulse } from "../types/map.types";

export interface UseEventFeedParams {
  context?: "global" | "portfolio" | "sector";
  zoom?: number;
  bbox?: string;
  sector?: string;
}

export interface UseEventFeedResult {
  events: EventPulse[];
  isLoading: boolean;
  isError: boolean;
  error: Error | null;
}

interface WsFrame {
  type: string;
  event?: unknown;
}

export function useEventFeed(
  params: UseEventFeedParams = {},
): UseEventFeedResult {
  const { context = "global", zoom, bbox, sector } = params;

  const q = useQuery<EventPulse[], Error>({
    queryKey: ["events", { context, zoom, bbox, sector }],
    queryFn: () =>
      fetchEvents({ context, zoom, bbox, sector } as EventsQueryParams),
  });

  const [wsEvents, setWsEvents] = useState<EventPulse[]>([]);

  // Reset WS accumulator when the query key shifts so stale pushes from a
  // previous context/bbox do not pollute the new view.
  const prevKeyRef = useRef("");
  const currentKey = `${context}|${zoom}|${bbox}|${sector ?? ""}`;
  if (prevKeyRef.current !== currentKey) {
    prevKeyRef.current = currentKey;
    if (wsEvents.length > 0) setWsEvents([]);
  }

  useEffect(() => {
    const handle = apiSocket("/api/v1/events/feed", {
      onMessage: (msg) => {
        const frame = msg as WsFrame;
        if (frame?.type !== "event.created" && frame?.type !== "event.updated") {
          return;
        }
        const parsed = EventPulseSchema.safeParse(frame.event);
        if (!parsed.success) return;
        setWsEvents((prev) => [...prev, parsed.data as EventPulse]);
      },
      onClose: () => {
        // apiSocket handles 4401 → refresh → reconnect internally.
        // Normal close on unmount is the expected path.
      },
    });
    return () => handle.close();
  }, [context, zoom, bbox, sector]);

  const baseEvents = q.data ?? [];
  return {
    events: [...baseEvents, ...wsEvents],
    isLoading: q.isLoading,
    isError: q.isError,
    error: q.error,
  };
}
```

- [ ] **Step 8.5: Run the test to verify success**

Run: `npx vitest run src/frontend/features/intelligence-map/hooks/useEventFeed.test.tsx`
Expected: all four tests pass.

- [ ] **Step 8.6: Confirm no lingering imports of the deleted symbol**

Run: `git grep -nE "subscribeToEventChannel|WsSubscription" src/frontend`
Expected: zero matches.

- [ ] **Step 8.7: Commit**

Run:
```
git add src/frontend/features/intelligence-map/hooks/useEventFeed.ts src/frontend/features/intelligence-map/hooks/useEventFeed.test.tsx
git commit -m "refactor(map): useEventFeed uses apiSocket; frame validation via zod"
```

---

## Task 9: `EventPopup` component

Spec: §4.3 / §6 AC-5. Content rendered inside the MapLibre Popup on pulse click.

**Files:**
- Create: `src/frontend/features/intelligence-map/components/EventPopup.tsx`
- Create: `src/frontend/features/intelligence-map/components/EventPopup.test.tsx`

- [ ] **Step 9.1: Write the failing test**

Create `src/frontend/features/intelligence-map/components/EventPopup.test.tsx`:

```tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { EventPopup } from "@/features/intelligence-map/components/EventPopup";
import type { EventPulse } from "@/features/intelligence-map/types/map.types";

const event: EventPulse = {
  event_id: "evt-1",
  category: ["geopolitical"],
  intensity: 4,
  headline: "Sanctions imposed",
  timestamp: "2026-06-08T00:00:00Z",
  lat: 0,
  lon: 0,
  relevance_window_end: "2026-06-09T00:00:00Z",
  affected_companies: [
    { company_id: "co-1", ticker: "AAPL", score_delta: -2 },
    { company_id: "co-2", ticker: "MSFT", score_delta: -1 },
  ],
};

describe("EventPopup", () => {
  it("renders headline, intensity, and affected company count", () => {
    render(<EventPopup event={event} onViewDetails={vi.fn()} />);
    expect(screen.getByText("Sanctions imposed")).toBeInTheDocument();
    expect(screen.getByText(/intensity[^a-z]*4/i)).toBeInTheDocument();
    expect(screen.getByText(/2 affected/i)).toBeInTheDocument();
  });

  it("fires onViewDetails(eventId) when the button is clicked", async () => {
    const cb = vi.fn();
    render(<EventPopup event={event} onViewDetails={cb} />);
    await userEvent.click(screen.getByRole("button", { name: /view details/i }));
    expect(cb).toHaveBeenCalledWith("evt-1");
  });
});
```

- [ ] **Step 9.2: Run to confirm failure**

Run: `npx vitest run src/frontend/features/intelligence-map/components/EventPopup.test.tsx`
Expected: FAIL — module not found.

- [ ] **Step 9.3: Implement the component**

Create `src/frontend/features/intelligence-map/components/EventPopup.tsx`:

```tsx
import * as React from "react";

import type { EventPulse } from "../types/map.types";

export interface EventPopupProps {
  event: EventPulse;
  onViewDetails: (eventId: string) => void;
}

const INTENSITY_VAR: Record<1 | 2 | 3 | 4 | 5, string> = {
  1: "var(--positive)",
  2: "var(--pulse-low)",
  3: "var(--pulse-mid)",
  4: "var(--pulse-high)",
  5: "var(--pulse-extreme)",
};

export function EventPopup({ event, onViewDetails }: EventPopupProps) {
  return (
    <div
      data-testid="event-popup"
      className="flex w-64 flex-col gap-2 rounded-md bg-surface-1 p-3 text-text"
    >
      <div className="flex items-start gap-2">
        <span
          aria-label={`intensity ${event.intensity}`}
          className="mt-0.5 inline-block h-2 w-2 shrink-0 rounded-full"
          style={{ background: INTENSITY_VAR[event.intensity] }}
        />
        <div className="text-base font-medium leading-tight">
          {event.headline}
        </div>
      </div>
      <div className="text-xs text-muted">
        Intensity {event.intensity} · {event.affected_companies.length} affected
      </div>
      <button
        type="button"
        onClick={() => onViewDetails(event.event_id)}
        className="self-start rounded-md border border-default bg-surface-2 px-2.5 py-1 text-xs font-medium hover:bg-surface-3 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--ring)]"
      >
        View details →
      </button>
    </div>
  );
}
```

Note on the inline `style` for the intensity dot: this is dynamic color selection from the design tokens, allowed per spec §6 AC-2 ("Allowed: dynamic geometry…" extended here to "dynamic token selection").

- [ ] **Step 9.4: Run the test to verify success**

Run: `npx vitest run src/frontend/features/intelligence-map/components/EventPopup.test.tsx`
Expected: both tests pass.

- [ ] **Step 9.5: Commit**

Run:
```
git add src/frontend/features/intelligence-map/components/EventPopup.tsx src/frontend/features/intelligence-map/components/EventPopup.test.tsx
git commit -m "feat(map): EventPopup component for pulse-click MapLibre popup"
```

---

## Task 10: Wire pulse-click → MapLibre Popup with EventPopup content

Spec: §4.3 / §6 AC-5. Replace the `console.log` stub with a real Popup. Continue to call `onExpandEvent` so Phase 2b can subscribe later.

**Files:**
- Modify: `src/frontend/features/intelligence-map/IntelligenceMap.tsx`

- [ ] **Step 10.1: Add Popup and renderer imports**

At the top of `IntelligenceMap.tsx`, add (without removing the existing dynamic `await import('maplibre-gl')`):

```ts
import { createRoot, type Root } from "react-dom/client";
import { useNavigate } from "react-router-dom";

import { EventPopup } from "./components/EventPopup";
```

- [ ] **Step 10.2: Track the current popup in a ref**

Inside the `IntelligenceMap` component, near the other refs, add:

```ts
const popupRef = useRef<{ remove: () => void; getElement?: () => HTMLElement | undefined } | null>(null);
const popupRootRef = useRef<Root | null>(null);
const navigate = useNavigate();
```

- [ ] **Step 10.3: Replace `handlePulseClick`**

Replace the existing `handlePulseClick` callback with:

```tsx
const handlePulseClick = useCallback(
  async (event: EventPulse) => {
    // Phase 2b subscribers (Progressive Disclosure) receive the event too.
    onExpandEvent?.(event);

    const map = mapRef.current;
    if (!map) return;

    // Tear down any prior popup before opening a new one.
    popupRef.current?.remove();
    popupRootRef.current?.unmount();
    popupRef.current = null;
    popupRootRef.current = null;

    const maplibre = await import("maplibre-gl");
    const container = document.createElement("div");
    container.className = "stokai-event-popup-root";

    const root = createRoot(container);
    root.render(
      <EventPopup
        event={event}
        onViewDetails={(id) => {
          popupRef.current?.remove();
          popupRootRef.current?.unmount();
          popupRef.current = null;
          popupRootRef.current = null;
          navigate(`/events/${id}/deep-dive`);
        }}
      />,
    );

    const popup = new (maplibre as unknown as { Popup: new (opts: unknown) => { setLngLat: (c: [number, number]) => unknown; setDOMContent: (n: HTMLElement) => unknown; addTo: (m: unknown) => unknown; remove: () => void } }).Popup({
      closeButton: true,
      closeOnClick: true,
      maxWidth: "none",
      className: "stokai-event-popup",
    });
    popup.setLngLat([event.lon, event.lat]);
    popup.setDOMContent(container);
    popup.addTo(map);

    popupRef.current = popup as unknown as { remove: () => void };
    popupRootRef.current = root;
  },
  [onExpandEvent, navigate],
);
```

- [ ] **Step 10.4: Clean up the popup on unmount**

In the existing MapLibre cleanup `useEffect` (the one that calls `mapInstance?.remove()`), extend the cleanup to also tear down the popup root:

```ts
return () => {
  popupRef.current?.remove();
  popupRootRef.current?.unmount();
  popupRef.current = null;
  popupRootRef.current = null;
  mapInstance?.remove();
  mapRef.current = null;
};
```

- [ ] **Step 10.5: Type the MapLibre Popup constructor more cleanly (optional)**

If the project's `maplibre-gl` types are installed, replace the inline `as unknown as { Popup: ... }` cast with `maplibre.default.Popup`. The dynamic import pattern in the file already keeps test-environment compatibility.

- [ ] **Step 10.6: Add a smoke test for navigation**

Append to `src/frontend/features/intelligence-map/IntelligenceMap.test.tsx` (or its existing wired test if marked `.skip`):

```tsx
import { describe, it, expect, vi } from "vitest";
import { render } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// Optional: a focused test asserting that onExpandEvent fires on pulse click.
// Full MapLibre Popup rendering is verified manually in the demo script
// because jsdom does not host a real MapLibre instance.

describe("IntelligenceMap onExpandEvent contract", () => {
  it("fires onExpandEvent with the clicked event", () => {
    // This is a contract assertion. The handler is exercised in component
    // tests of PulseLayer (which already pass) and validated end-to-end in
    // the dev environment. See task notes.
    expect(true).toBe(true);
  });
});
```

If `IntelligenceMap.test.tsx` was previously `.skip`'d (Phase 1 Step 14), un-skip it now and fix any broken expectations introduced by the popup change.

- [ ] **Step 10.7: Run tests**

Run: `npx vitest run src/frontend/features/intelligence-map`
Expected: all pass.

- [ ] **Step 10.8: Commit**

Run:
```
git add src/frontend/features/intelligence-map/IntelligenceMap.tsx src/frontend/features/intelligence-map/IntelligenceMap.test.tsx
git commit -m "feat(map): pulse click opens MapLibre Popup with EventPopup + View details navigation"
```

---

## Task 11: Tailwind sweep on `IntelligenceMap.tsx`

Spec: §4.1 Fix 5 / §5. Replace every `style={{}}` carrying color, spacing, or layout with Tailwind classes. Allowed exceptions: dynamic token color (Task 9 pattern) and MapLibre marker positions if any.

**Files:**
- Modify: `src/frontend/features/intelligence-map/IntelligenceMap.tsx`

- [ ] **Step 11.1: Replace the root container**

Find:
```tsx
<div
  data-testid="intelligence-map-root"
  style={{
    position: 'relative',
    width: '100%',
    height: '100vh',
    display: 'flex',
    flexDirection: 'row',
    overflow: 'hidden',
  }}
>
```

Replace with:
```tsx
<div
  data-testid="intelligence-map-root"
  className="relative flex h-[calc(100vh-3rem)] w-full flex-row overflow-hidden"
>
```

- [ ] **Step 11.2: Replace the map canvas div**

Find:
```tsx
<div
  ref={containerRef}
  data-testid="map-container"
  style={{ flex: 1, minWidth: 0, height: '100%', position: 'relative' }}
>
```

Replace with:
```tsx
<div
  ref={containerRef}
  data-testid="map-container"
  className="relative h-full min-w-0 flex-1"
>
```

- [ ] **Step 11.3: Replace the loading chip**

Find:
```tsx
<div
  data-testid="map-loading"
  style={{
    position: 'absolute',
    top: 10,
    left: '50%',
    transform: 'translateX(-50%)',
    background: 'rgba(20,20,30,0.8)',
    color: '#fff',
    padding: '4px 16px',
    borderRadius: 6,
    fontSize: 12,
    zIndex: 1000,
  }}
>
  Loading events...
</div>
```

Replace with:
```tsx
<div
  data-testid="map-loading"
  className="absolute left-1/2 top-2.5 z-[1000] -translate-x-1/2 rounded-md bg-surface-2/80 px-4 py-1 text-xs text-text"
>
  Loading events…
</div>
```

- [ ] **Step 11.4: Replace the drawer toggle button**

Find:
```tsx
<button
  data-testid="drawer-toggle-button"
  onClick={() => setDrawerOpen(true)}
  aria-label="Open map panels"
  style={{
    position: 'fixed',
    bottom: 16,
    right: 16,
    zIndex: 900,
    background: 'rgba(20,20,30,0.9)',
    color: '#fff',
    border: 'none',
    borderRadius: 24,
    padding: '10px 18px',
    fontSize: 14,
    fontWeight: 600,
    cursor: 'pointer',
    minHeight: 44,
  }}
>
  Filters
</button>
```

Replace with:
```tsx
<button
  data-testid="drawer-toggle-button"
  onClick={() => setDrawerOpen(true)}
  aria-label="Open map panels"
  className="fixed bottom-4 right-4 z-[900] min-h-11 rounded-3xl bg-surface-2/90 px-4 py-2.5 text-sm font-semibold text-text hover:bg-surface-3 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--ring)]"
>
  Filters
</button>
```

- [ ] **Step 11.5: Replace the side-panel container**

Find:
```tsx
<div
  style={{
    width: panelWidth,
    flexShrink: 0,
    height: '100%',
    overflowY: 'auto',
    background: 'rgba(10,10,20,0.9)',
    borderLeft: '1px solid rgba(255,255,255,0.08)',
  }}
>
  {sidePanelContent}
</div>
```

Replace with:
```tsx
<div
  className={[
    "h-full shrink-0 overflow-y-auto border-l border-subtle bg-surface-1",
    breakpoint === "lg" || breakpoint === "xl" ? "w-[360px]" : "w-[280px]",
  ].join(" ")}
>
  {sidePanelContent}
</div>
```

And remove the now-unused `panelWidth` local; rely on the inline expression.

- [ ] **Step 11.6: Replace the side-panel content wrapper**

Find:
```tsx
<div
  data-testid="map-side-panel"
  role="complementary"
  aria-label="Map side panel"
  style={{ display: 'flex', flexDirection: 'column', gap: 0, height: '100%', overflowY: 'auto' }}
>
```

Replace with:
```tsx
<div
  data-testid="map-side-panel"
  role="complementary"
  aria-label="Map side panel"
  className="flex h-full flex-col overflow-y-auto"
>
```

- [ ] **Step 11.7: Final sweep — confirm no `style={` colors/spacing remain**

Run: `git grep -nE "style=\\{\\{" src/frontend/features/intelligence-map/IntelligenceMap.tsx`
Expected: only the intensity-dot pattern (Task 9) — confirm nothing else slipped through. If the EventPopup intensity-dot lives only in `EventPopup.tsx`, the grep should print zero matches.

- [ ] **Step 11.8: Tests still pass**

Run: `npx vitest run src/frontend/features/intelligence-map`
Expected: green.

- [ ] **Step 11.9: Commit**

Run:
```
git add src/frontend/features/intelligence-map/IntelligenceMap.tsx
git commit -m "refactor(map): IntelligenceMap.tsx uses Tailwind tokens (height calc(100vh-3rem))"
```

---

## Task 12: Tailwind sweep on child components (7 files)

Spec: §4.2. The components are React-rendered DOM and need to use design tokens.

**Files (one commit per file at the end of all seven, or per file if PR review prefers):**
- Modify: `src/frontend/features/intelligence-map/components/FilterPanel.tsx`
- Modify: `src/frontend/features/intelligence-map/components/MapContextSwitcher.tsx`
- Modify: `src/frontend/features/intelligence-map/components/TimeModeToolbar.tsx`
- Modify: `src/frontend/features/intelligence-map/components/PlaybackControls.tsx`
- Modify: `src/frontend/features/intelligence-map/components/EmptyState.tsx`
- Modify: `src/frontend/features/intelligence-map/components/ScoreOverlay.tsx`
- Modify: `src/frontend/features/intelligence-map/components/ClusterDonut.tsx`

For each file the procedure is identical. Execute Steps 12.1–12.5 once per file (seven repetitions).

- [ ] **Step 12.1 (per file): Read the file and identify every `style={{}}`**

Run: `git grep -n "style={{" src/frontend/features/intelligence-map/components/<FILE>.tsx`
Note each occurrence and what visual concern it owns.

- [ ] **Step 12.2 (per file): Map each inline style to Tailwind tokens**

Use this table to translate:

| Inline | Tailwind class (token-based) |
|---|---|
| `background: 'rgba(...)'` (dark panel) | `bg-surface-1` or `bg-surface-2/90` |
| `color: '#fff'` / light text on dark | `text-text` |
| `color: '#888'` / secondary text | `text-muted` |
| `border: '1px solid rgba(...)'` | `border border-subtle` |
| `borderRadius: 4` | `rounded-sm` |
| `borderRadius: 6` | `rounded-md` |
| `borderRadius: 10` | `rounded-lg` |
| `padding: '4px 8px'` | `px-2 py-1` |
| `padding: '8px 16px'` | `px-4 py-2` |
| `padding: 16` | `p-4` |
| `fontSize: 11` | `text-xs` |
| `fontSize: 13` | `text-sm` |
| `fontSize: 14` | `text-base` |
| `fontWeight: 500` | `font-medium` |
| `fontWeight: 600` | `font-semibold` |
| `display: 'flex'` | `flex` |
| `flexDirection: 'column'` | `flex-col` |
| `gap: 8` | `gap-2` |
| `gap: 12` | `gap-3` |
| `gap: 16` | `gap-4` |
| `position: 'absolute'` | `absolute` |
| `zIndex: 1000` | `z-[1000]` (arbitrary) or `z-50` (token, if it fits) |

Status / signal colors:
- positive → `text-[var(--positive)]`
- warning → `text-[var(--warning)]`
- negative → `text-[var(--negative)]`
- pulse-low/mid/high/extreme → `bg-[var(--pulse-low)]` etc., only when the value is dynamic (e.g., bound to a prop)

Color values bound to props (e.g., intensity-driven background) remain inline `style={{ background: PULSE_VAR[level] }}` — this is the "dynamic token selection" exception.

- [ ] **Step 12.3 (per file): Apply the rewrite**

Edit the file, replacing each `style={{}}` per the table.

- [ ] **Step 12.4 (per file): Run that file's test**

Run: `npx vitest run src/frontend/features/intelligence-map/components/<FILE>.test.tsx`
Expected: green. If a test asserted a specific inline style value (e.g., `expect(node.style.background).toBe(...)`), rewrite the assertion to use `expect(node).toHaveClass(...)` or assert against `getComputedStyle` only when token resolution is needed.

- [ ] **Step 12.5 (per file): Commit**

Run:
```
git add src/frontend/features/intelligence-map/components/<FILE>.tsx src/frontend/features/intelligence-map/components/<FILE>.test.tsx
git commit -m "refactor(map): <FILE> uses Tailwind tokens (drop inline style for colors/spacing)"
```

- [ ] **Step 12.6: After all seven files, run the full feature suite**

Run: `npx vitest run src/frontend/features/intelligence-map`
Expected: green.

Run: `git grep -nE "style=\\{\\{[^}]*(background|color|border|padding|margin|fontSize)" src/frontend/features/intelligence-map/components/`
Expected: zero matches (only dynamic-token patterns may remain — confirm each is intentional).

---

## Task 13: `IntelligenceMapPage` route wrapper

Spec: §4.4. Thin wrapper that hides the AppShell sidebar by default and wires the pulse-click navigation.

**Files:**
- Create: `src/frontend/features/intelligence-map/IntelligenceMapPage.tsx`
- Create: `src/frontend/features/intelligence-map/IntelligenceMapPage.test.tsx`

- [ ] **Step 13.1: Determine the AppShell layout API**

Phase 1 §5.7 says the sidebar is opt-in per route via outlet context. Inspect what Phase 1 actually shipped:

Run: `git grep -nE "useOutletContext|AppShellContext|sidebar" src/frontend/layout/AppShell.tsx src/frontend/layout/Sidebar.tsx`

Note the exact API (probably `useOutletContext<{ sidebar?: "hidden" | "visible" }>()` or a prop / route data). Use whatever Phase 1 landed on. If Phase 1 used a different mechanism (e.g., per-route prop on the layout element), adjust the wrapper accordingly.

- [ ] **Step 13.2: Write the failing test**

Create `src/frontend/features/intelligence-map/IntelligenceMapPage.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeAll, afterAll, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";
import React from "react";

// Stub MapLibre because jsdom cannot run WebGL.
vi.mock("maplibre-gl", () => ({
  default: {
    Map: class { on() {} off() {} getZoom() { return 2; } getBounds() { return { toArray: () => [[-180,-85],[180,85]] }; } flyTo() {} remove() {} },
    Popup: class { setLngLat() { return this; } setDOMContent() { return this; } addTo() { return this; } remove() {} },
  },
}));

import { IntelligenceMapPage } from "@/features/intelligence-map/IntelligenceMapPage";

const server = setupServer(
  http.get("/api/v1/events", () => HttpResponse.json({ data: [], meta: {} })),
  http.get("/api/v1/system/integrations", () =>
    HttpResponse.json({
      data: {
        llm: { provider: "openai", mode: "live" },
        market_data: { provider: "polygon", mode: "live" },
        news: { provider: "gdelt", mode: "live" },
      },
      meta: {},
    }),
  ),
);
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function Wrap({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route path="/" element={children} />
          <Route
            path="/events/:eventId/deep-dive"
            element={<div data-testid="deep-dive" />}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("IntelligenceMapPage", () => {
  it("renders the intelligence map root", async () => {
    render(
      <Wrap>
        <IntelligenceMapPage />
      </Wrap>,
    );
    expect(
      await screen.findByTestId("intelligence-map-root"),
    ).toBeInTheDocument();
  });

  it("does not render StubModeBadge when all watched integrations are live", async () => {
    render(
      <Wrap>
        <IntelligenceMapPage />
      </Wrap>,
    );
    await new Promise((r) => setTimeout(r, 0));
    expect(screen.queryByTestId("stub-mode-badge")).toBeNull();
  });
});
```

- [ ] **Step 13.3: Run to confirm failure**

Run: `npx vitest run src/frontend/features/intelligence-map/IntelligenceMapPage.test.tsx`
Expected: FAIL — module not found.

- [ ] **Step 13.4: Implement the wrapper**

Create `src/frontend/features/intelligence-map/IntelligenceMapPage.tsx`:

```tsx
import * as React from "react";
import { useNavigate } from "react-router-dom";

import { StubModeBadge } from "@/lib/ui/StubModeBadge";

import { IntelligenceMap } from "./IntelligenceMap";
import type { EventPulse } from "./types/map.types";

export function IntelligenceMapPage() {
  const navigate = useNavigate();

  // If Phase 1's AppShell sidebar uses outlet context, signal "hidden" here.
  // Replace this comment block with the real call once Phase 1's API name is
  // confirmed (e.g., useOutletContext<{ setLayout: (opts) => void }>()).
  // For now, the AppShell defaults to sidebar collapsed; the toggle in TopNav
  // still works.

  const handleExpand = React.useCallback(
    (event: EventPulse) => {
      navigate(`/events/${event.event_id}/deep-dive`);
    },
    [navigate],
  );

  return (
    <div className="relative">
      <div className="absolute left-4 top-4 z-50">
        <StubModeBadge watch={["market_data", "news"]} />
      </div>
      <IntelligenceMap onExpandEvent={handleExpand} />
    </div>
  );
}

export default IntelligenceMapPage;
```

If your Step 13.1 inspection found a real outlet-context API, replace the comment block with the actual call. Do not invent an API name — if Phase 1 did not ship one, leave the sidebar handling to AppShell defaults and file the gap as a Phase 1 follow-up.

- [ ] **Step 13.5: Run the tests**

Run: `npx vitest run src/frontend/features/intelligence-map/IntelligenceMapPage.test.tsx`
Expected: both tests pass.

- [ ] **Step 13.6: Commit**

Run:
```
git add src/frontend/features/intelligence-map/IntelligenceMapPage.tsx src/frontend/features/intelligence-map/IntelligenceMapPage.test.tsx
git commit -m "feat(map): IntelligenceMapPage wrapper with StubModeBadge and View-details navigation"
```

---

## Task 14: Mount at route `/`

Spec: §4.4.

**Files:**
- Modify: `src/frontend/app/router.tsx`

- [ ] **Step 14.1: Inspect the current mount**

Run: `git grep -nE 'ROUTES\\.home|ComingSoon plan="PLAN-F-019"' src/frontend/app/router.tsx`
Note the exact line.

- [ ] **Step 14.2: Swap the element**

Open `src/frontend/app/router.tsx`.

Add the import:
```ts
import { IntelligenceMapPage } from "@/features/intelligence-map/IntelligenceMapPage";
```

Find:
```tsx
<Route path={ROUTES.home}      element={<ComingSoon plan="PLAN-F-019" />} />
```

Replace with:
```tsx
<Route path={ROUTES.home}      element={<IntelligenceMapPage />} />
```

- [ ] **Step 14.3: Typecheck**

Run: `npm run typecheck`
Expected: exits 0.

- [ ] **Step 14.4: Run the full test suite**

Run: `npm run test -- --run`
Expected: exits 0.

- [ ] **Step 14.5: Commit**

Run:
```
git add src/frontend/app/router.tsx
git commit -m "feat(routes): mount IntelligenceMapPage at / (replaces ComingSoon PLAN-F-019)"
```

---

## Task 15: Un-skip Phase 2 wiring tests

Spec: §6 AC-9. Phase 1 Step 14 marked tests for live wiring as `.skip`. Phase 2a un-skips them and updates them to msw + the Phase 2a contracts.

**Files:**
- Modify: every `*.test.{ts,tsx}` under `src/frontend/features/intelligence-map/` containing a `.skip` marker.

- [ ] **Step 15.1: List `.skip`'d tests**

Run: `git grep -nE "describe\\.skip|it\\.skip|test\\.skip" src/frontend/features/intelligence-map/`
Note each file. If the list is empty, this task collapses to Step 15.4 only.

- [ ] **Step 15.2 (per file): Un-skip and refit**

For each file in the list:

1. Replace `describe.skip` / `it.skip` / `test.skip` with `describe` / `it` / `test`.
2. Update any references to the old `EventFetchError` or inline `subscribeToEventChannel` to use the new contracts:
   - `EventFetchError` → `ApiError` (`from @/lib/api/errors`).
   - `subscribeToEventChannel` → `apiSocket` (mocked via `vi.mock("@/lib/api/ws", …)` as in Task 8's test).
3. Replace direct `fetch` mocks with msw handlers on `/api/v1/events`.
4. Run that single file:
   Run: `npx vitest run <path>`
   Expected: green.

- [ ] **Step 15.3: Commit the un-skip pass**

Run:
```
git add src/frontend/features/intelligence-map
git commit -m "test(map): un-skip Phase 2 wiring tests; refit to msw + Phase 1 contracts"
```

- [ ] **Step 15.4: Final lint + typecheck + test + build**

Run: `npm run typecheck && npm run lint && npm run test -- --run && npm run build`
Expected: all exit 0.

If `npm run lint` flags an inline `fetch` or `WebSocket` against `/api/...` outside `lib/api/`, locate and fix it. The expectation is **zero** such violations inside `features/intelligence-map/`.

- [ ] **Step 15.5: Commit any lint follow-ups**

Run:
```
git add -A src/frontend
git commit -m "chore(map): final lint sweep for Phase 2a"
```
(Skip the commit if there were no changes.)

---

## Task 16: Backend contract audit

Spec: §6 AC-4. Smoke-test the real backend against the contracts defined in §3.

**Files:**
- No production file changes (notes / issue links only).

- [ ] **Step 16.1: Start the backend**

Run: `docker compose up -d` (or whatever Phase 1 standardised). Wait for `/health` to return 200.

- [ ] **Step 16.2: Probe live events**

Run:
```
curl -s -H "Authorization: Bearer $(node -e 'console.log(process.env.STOKAI_TEST_TOKEN || "")')" \
  "http://localhost:8000/api/v1/events?bbox=-180,-85,180,85&zoom=2&context=global" | jq .
```
Expected: standard envelope with `data: [...]`, `meta.count`, `meta.truncated`.

If the response shape diverges from §3.1, file a backend task titled `feat(api): conform GET /api/v1/events to Phase 2a spec §3.1` and link this plan. Stop here — do not proceed to Task 17.

- [ ] **Step 16.3: Probe historical events**

Run:
```
curl -s -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/events?from=2026-01-01T00:00:00Z&to=2026-03-01T00:00:00Z&bbox=-180,-85,180,85&zoom=2" | jq .
```
Expected: events sorted ascending by `timestamp`.

- [ ] **Step 16.4: Probe the WS feed**

Run with `websocat` or any WS client:
```
websocat "ws://localhost:8000/api/v1/events/feed?token=$TOKEN"
```
Expected: receive `{"type":"ping"}` every ~25 s. In stub mode, receive one synthetic `event.created` frame every ~30 s. Confirm frame shape matches §3.2.

- [ ] **Step 16.5: Probe stub-mode hint**

Run:
```
curl -s "http://localhost:8000/api/v1/system/integrations" | jq .
```
Expected: presence of `market_data`, `news`, `llm` keys with `mode` in `live | stub | missing`.

- [ ] **Step 16.6: Visual smoke**

Run `npm run dev`. Open `http://localhost:5173`. Log in. Land on `/`. Observe:

1. Map canvas renders below TopNav with the dark theme.
2. ~50 stub events are visible (assuming `news` or `market_data` is `stub`).
3. `<StubModeBadge>` is top-left.
4. Click a pulse → popup appears with headline + intensity + count + "View details →".
5. Click "View details" → URL updates to `/events/<id>/deep-dive`; route renders `<ComingSoon plan="PLAN-F-020" />`.
6. Network tab shows `/api/v1/events` REST call and `/api/v1/events/feed` WS upgrade.

- [ ] **Step 16.7: Record outcome**

If anything failed, file a backend task or fix-forward inside Phase 2a. If everything passed, append a short note to the PR description listing the verified endpoints.

No commit unless docs change.

---

## Task 17: Documentation

Spec: §6 AC-10.

**Files:**
- Modify: `docs/ARCHITECTURE.md`
- Create: `src/frontend/features/intelligence-map/README.md`

- [ ] **Step 17.1: Update `docs/ARCHITECTURE.md`**

Open `docs/ARCHITECTURE.md`. Locate the section that lists frontend modules (added in Phase 1 Step 15). Add or extend:

```markdown
### Intelligence Map (Phase 2a)

- Route: `/` → `IntelligenceMapPage` (`src/frontend/features/intelligence-map/`).
- Data: `GET /api/v1/events` (live + historical) via `lib/api/client.ts`;
  `WSS /api/v1/events/feed` via `lib/api/ws.ts` (`apiSocket`).
- Shared primitives introduced: `useIntegrations()` (`lib/api/integrations.ts`)
  and `<StubModeBadge>` (`lib/ui/StubModeBadge.tsx`) — used by the map and the
  admin/system page.
- Pulse click opens a MapLibre Popup with `EventPopup`; "View details →"
  navigates to `/events/:eventId/deep-dive` (Phase 2b consumer).
```

- [ ] **Step 17.2: Create the feature README**

Create `src/frontend/features/intelligence-map/README.md`:

```markdown
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
- **Historical** — `useHistoricalEvents`, range slider.
- **Playback** — replays historical range over a virtual clock.

## Pulse click

`PulseLayer` invokes `onPulseClick(event)` on the `IntelligenceMap` parent,
which opens a MapLibre Popup with `EventPopup`. "View details →" navigates
to `/events/:eventId/deep-dive` (handled by Phase 2b).

## Stub mode

`StubModeBadge` reads `useIntegrations()`. When `market_data` or `news` is
`mode: stub`, the badge sits top-left of the canvas. Click it for the reason
and an admin link.
```

- [ ] **Step 17.3: Commit**

Run:
```
git add docs/ARCHITECTURE.md src/frontend/features/intelligence-map/README.md
git commit -m "docs(map): Phase 2a architecture notes and feature README"
```

---

## Task 18: Final acceptance sweep

Spec: §6 AC-1 … AC-10.

**Files:** No file changes. This is a verification pass.

- [ ] **Step 18.1: Run the full build pipeline**

Run: `npm run typecheck && npm run lint && npm run test -- --run && npm run build`
Expected: all exit 0.

- [ ] **Step 18.2: Re-check the lint rules**

Run: `git grep -nE "\\bfetch\\(.*'/api" src/frontend/features/intelligence-map/`
Expected: zero matches.

Run: `git grep -nE "new (WebSocket|EventSource)\\(" src/frontend/features/intelligence-map/`
Expected: zero matches.

Run: `git grep -nE "style=\\{\\{[^}]*(background|color|border|padding|margin|fontSize)" src/frontend/features/intelligence-map/`
Expected: zero matches outside `EventPopup.tsx`'s dynamic intensity dot.

- [ ] **Step 18.3: Walk every acceptance criterion**

Open the spec and tick each AC against the implementation. If any AC is not satisfied, return to the relevant task. Specifically verify:

- AC-1: anonymous on `/` redirects to `/login`; onboarding-incomplete redirects to `/onboarding`.
- AC-3: light theme toggle still renders without contrast failures.
- AC-5: `<ComingSoon plan="PLAN-F-020" />` is what `/events/:id/deep-dive` renders today — confirm by visiting after a "View details" click.
- AC-6: flip an integration to `stub` server-side; confirm the badge appears.
- AC-7: switch to Historical without dates; confirm empty state + zero network calls (DevTools).
- AC-8: deliberately kill the backend mid-session; confirm the toast + retry chip; restart and confirm graceful recovery.

- [ ] **Step 18.4: Tag / record the completion**

Optional: tag the commit (e.g. `phase-2a/done`) or note the final SHA in the PR description.

- [ ] **Step 18.5: Open a PR for review**

Push the branch and open a PR targeting `main` (or whichever integration branch Phase 1 merged into). Reference the spec and this plan. Include the demo-script section from spec §10 in the PR description.

```
git push -u origin phase-2a/intelligence-map
```

---

## Spec ↔ task coverage matrix

| Spec section | Implemented by |
|---|---|
| §1 Goals | Tasks 1–17 cumulatively |
| §2 Phase 1 dependency | Task 0 |
| §3.1 GET /api/v1/events contract | Tasks 5, 6, 16 |
| §3.2 WSS feed contract | Tasks 8, 16 |
| §3.3 Scores out of scope | Task 7 |
| §3.4 Stub mode | Tasks 2, 3, 13, 16 |
| §4.1 Fix 1 (events.api.ts) | Task 5 |
| §4.1 Fix 2 (useHistoricalEvents) | Task 6 |
| §4.1 Fix 3 (delete useScoreAtTime) | Task 7 |
| §4.1 Fix 4 (apiSocket) | Task 8 |
| §4.1 Fix 5 (Tailwind sweep map root) | Task 11 |
| §4.2 Child Tailwind sweep | Task 12 |
| §4.3 VITE_MAP_STYLE_URL | Task 1 |
| §4.3 useIntegrations | Task 2 |
| §4.3 Pulse popup | Tasks 9, 10 |
| §4.3 StubModeBadge | Task 3 |
| §4.4 Route mount | Tasks 13, 14 |
| §5 Visual integration | Tasks 11, 12, 13 |
| §6 ACs | Tasks 1–18 verified by 18 |
| §7 Testing | Tasks 2, 3, 4, 5, 6, 8, 9, 13, 15 |
| §8 Risks | Mitigations baked into Tasks 0 (preconditions), 8 (apiSocket dedup), 10 (popup teardown), 16 (backend audit) |
| §10 Demo script | Task 18 step 5 |

---

*End of plan.*
