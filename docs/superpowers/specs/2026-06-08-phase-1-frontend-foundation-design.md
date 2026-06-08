# Phase 1 — Frontend Foundation: Design Spec

**Date:** 2026-06-08
**Author:** brainstorming session (jakub + assistant)
**Status:** Approved for planning
**Branch target:** `phase-1/foundation`
**Phase 2/3 follow-ups:** separate specs, not in this document

---

## 0. Why this exists

The StokAI frontend has accumulated ~95% of the per-plan UI implementations
(intelligence map, screener, briefs, alerts, portfolio, company detail, AI
audit, indicator builder, onboarding, scoring, Q&A, admin AI-audit, progressive
disclosure) — but they were built into a parallel directory tree
(`src/frontend/`) that is **not connected** to the running application shell
(`frontend/src/`). The shell renders only three admin routes and a literal
`<div>Home</div>`. None of the user-facing features are reachable. Several
features also have broken local imports, missing dependencies, and no styling
system wired up at all (zero `.css` files; classes referenced but never
processed).

Plans-index marks 47/47 plans "done", but no plan integrated its output into a
working application. This spec corrects that: it consolidates the two trees,
installs a modern visual system, builds a real app shell with authentication,
and mounts every route — with Phases 2 and 3 reserved for wiring features to
live backend APIs.

**Scope rule, repeated throughout this spec:** the frontend never mocks
backend behaviour. Where an external integration (LLM, market data, news,
social) is not configured, the *backend* serves a deterministic stub and
declares it via `GET /api/v1/system/integrations`. The frontend surfaces
"stub mode" honestly via `<StubModeBadge>`.

---

## 1. Goals & non-goals

### 1.1 Goals

1. One canonical frontend tree under `src/frontend/` with a buildable, runnable
   shell.
2. Tailwind v4 + shadcn/ui design system; dual-theme (dark default), tokens in
   CSS, zero inline styling.
3. Working authentication: register, login, logout, silent refresh, route
   guards (auth, admin, onboarding), httpOnly refresh cookie + in-memory access
   token.
4. Every route in `ROUTES` is mounted and reachable; Phase-1 admin routes (HIL,
   Sources, System) render real content; all other routes render a tasteful
   `<ComingSoon plan="…" />` placeholder.
5. One API client (`lib/api/client.ts`) that all features must use; standard
   envelope; typed `ApiError`; SSE + WebSocket wrappers ready.
6. Vitest replaces Jest; tests for code we keep all pass; tests for code we
   delete are removed; tests for Phase 2/3 wiring are `.skip` with comments.
7. `npm run dev`, `npm run build`, `npm run test`, `npm run lint`,
   `npm run typecheck` all exit zero.
8. `docker compose up` reaches the app end-to-end through the Vite proxy.

### 1.2 Non-goals (explicitly Phase 2 / 3 or post-MVP)

- Wiring IntelligenceMap, Screener, Briefs, Q&A, CompanyDetail, Portfolio,
  Alerts, AI Audit, Indicator Builder to live backend APIs.
- Real MapLibre rendering on screen.
- SSE streaming UI for Q&A (wrapper exists; consumer is Phase 2).
- WebSocket-driven map feed (wrapper exists; consumer is Phase 2).
- Password reset, OAuth2/SSO.
- Sentry telemetry, Storybook, visual regression, i18n, SSR.

---

## 2. Final directory layout

The canonical tree at end of Phase 1:

```
src/frontend/
├─ index.html
├─ main.tsx
├─ app/
│  ├─ App.tsx
│  ├─ router.tsx
│  ├─ routes.ts
│  ├─ providers/
│  │  ├─ QueryProvider.tsx
│  │  ├─ ThemeProvider.tsx
│  │  ├─ AuthProvider.tsx
│  │  └─ ErrorBoundary.tsx
│  └─ guards/
│     ├─ RequireAuth.tsx
│     ├─ RequireAdmin.tsx
│     └─ OnboardingGate.tsx
├─ layout/
│  ├─ AppShell.tsx
│  ├─ TopNav.tsx
│  ├─ Sidebar.tsx
│  ├─ MobileNav.tsx
│  └─ CommandPalette.tsx
├─ ui/                    ← shadcn primitives + index barrel
├─ lib/
│  ├─ api/
│  │  ├─ client.ts
│  │  ├─ stream.ts
│  │  ├─ ws.ts
│  │  ├─ errors.ts
│  │  ├─ types.ts
│  │  └─ keys.ts
│  ├─ env.ts
│  ├─ cn.ts
│  ├─ format.ts
│  └─ viz.ts
├─ hooks/                 ← useBreakpoint, useTheme (re-export)
├─ features/
│  ├─ auth/               ← LoginPage, RegisterPage (Phase 1 — real)
│  ├─ onboarding/         ← OnboardingFlow (rewired)
│  ├─ intelligence-map/   ← (Phase 2 wiring)
│  ├─ progressive-disclosure/ ← (Phase 2)
│  ├─ briefs/             ← (Phase 2)
│  ├─ qa/                 ← (Phase 2, consolidated)
│  ├─ company-detail/     ← (Phase 2)
│  ├─ screener/           ← (Phase 3)
│  ├─ portfolio/          ← (Phase 3)
│  ├─ alerts/             ← (Phase 3)
│  ├─ indicator-builder/  ← (Phase 3)
│  ├─ scoring/            ← (Phase 3)
│  └─ shared/             ← Drawer, ResponsiveLayout, hooks
├─ pages/
│  └─ admin/
│     ├─ AdminLayout.tsx
│     ├─ hil/             ← Phase 1 real
│     ├─ sources/         ← Phase 1 real
│     ├─ system/          ← Phase 1 real
│     └─ ai-audit/        ← (Phase 2)
└─ styles/
   ├─ globals.css
   └─ tokens.css
```

**Repo root after Phase 1:**
- `vite.config.ts` — `root: 'src/frontend'`, `outDir: '../../dist/frontend'`,
  proxy `/api`, `/health`, `/ws` to `http://localhost:8000`.
- `tsconfig.json` — `include: ['src/frontend']`, `paths: { '@/*': ['src/frontend/*'] }`.
- `vitest.config.ts` — extends `vite.config.ts`, `jsdom`, setup files under
  `tests/frontend/`.
- `frontend/` directory: **deleted**.
- `index.html` at root: **deleted** (moved into `src/frontend/`).
- `jest.config.js`: **deleted**.

---

## 3. Tech stack (locked)

### 3.1 Runtime

| Concern | Choice |
|---|---|
| Build / dev | Vite 8 (installed) + `@tailwindcss/vite` + `@vitejs/plugin-react-swc` |
| Framework | React 18.3 (installed) |
| Router | react-router-dom 6.26 (installed) |
| Server state | @tanstack/react-query 5.40 (installed) |
| Styling | Tailwind CSS v4 (`@theme` directive in CSS, no JS config) |
| Component primitives | shadcn/ui (Radix-based, copy-paste, owned source) |
| Icons | lucide-react |
| Motion | framer-motion 11 |
| Charts | recharts (installed) |
| Map | maplibre-gl 4 + supercluster 8 (Phase 2 consumer) |
| HTML sanitiser | dompurify 3 + @types/dompurify |
| Forms | react-hook-form 7 + zod 3 + @hookform/resolvers |
| Toasts | sonner |
| Date utils | date-fns 3 |
| Theme persistence | next-themes 0.3 |
| Class merging | clsx + tailwind-merge + class-variance-authority |

### 3.2 Tooling

| Concern | Choice |
|---|---|
| Test runner | Vitest 2 + @vitest/coverage-v8 |
| DOM | jsdom |
| Mocking HTTP | msw (Mock Service Worker) for tests only — never shipped |
| Lint | eslint 9 + typescript-eslint + react/hooks + jsx-a11y |
| Format | prettier 3 + prettier-plugin-tailwindcss |

### 3.3 Concrete `package.json` deltas

**Add (dependencies):** `clsx`, `tailwind-merge`, `class-variance-authority`,
`@radix-ui/react-dialog`, `@radix-ui/react-dropdown-menu`,
`@radix-ui/react-tabs`, `@radix-ui/react-tooltip`, `@radix-ui/react-slot`,
`@radix-ui/react-select`, `@radix-ui/react-popover`,
`@radix-ui/react-toast`, `@radix-ui/react-separator`,
`@radix-ui/react-scroll-area`, `lucide-react`, `framer-motion`, `sonner`,
`next-themes`, `date-fns`, `dompurify`, `@types/dompurify`,
`react-hook-form`, `zod`, `@hookform/resolvers`, `maplibre-gl`,
`supercluster`.

**Add (devDependencies):** `tailwindcss@^4`, `@tailwindcss/vite@^4`,
`@vitejs/plugin-react-swc`, `vitest@^2`, `@vitest/ui`,
`@vitest/coverage-v8`, `jsdom`, `msw@^2`, `eslint@^9`,
`@typescript-eslint/parser`, `@typescript-eslint/eslint-plugin`,
`eslint-plugin-react`, `eslint-plugin-react-hooks`,
`eslint-plugin-jsx-a11y`, `prettier@^3`, `prettier-plugin-tailwindcss`,
`@types/supercluster`.

**Remove:** `jest`, `jest-environment-jsdom`, `ts-jest`, `@types/jest`,
`@vitejs/plugin-react` (replaced by `-react-swc`).

**Scripts:**
```json
{
  "dev": "vite",
  "build": "tsc -b && vite build",
  "preview": "vite preview",
  "test": "vitest run",
  "test:watch": "vitest",
  "test:coverage": "vitest run --coverage",
  "lint": "eslint src/frontend tests/frontend --max-warnings=0",
  "format": "prettier --write \"src/frontend/**/*.{ts,tsx,css,md}\"",
  "typecheck": "tsc --noEmit"
}
```

---

## 4. Visual design system

### 4.1 Design intent

A high-density, dark-first "command center" aesthetic — Linear / Bloomberg
Terminal / Vercel dashboard tone. Clear hierarchy, monospace numerics,
restrained accent color, sharp focus states, fast micro-interactions. Light
theme is supported but secondary.

### 4.2 Design tokens (`src/frontend/styles/tokens.css`)

CSS variables in OKLCH. Both themes share semantic token names; values switch
on `[data-theme]`.

```css
:root, [data-theme="dark"] {
  --surface-0:      oklch(14% 0.01 250);
  --surface-1:      oklch(18% 0.012 250);
  --surface-2:      oklch(22% 0.014 250);
  --surface-3:      oklch(27% 0.015 250);
  --border-subtle:  oklch(28% 0.012 250);
  --border-default: oklch(34% 0.013 250);
  --border-strong:  oklch(48% 0.015 250);

  --text-primary:   oklch(96% 0.005 250);
  --text-secondary: oklch(78% 0.008 250);
  --text-muted:     oklch(58% 0.010 250);
  --text-disabled:  oklch(42% 0.012 250);

  --signal:         oklch(72% 0.18 230);
  --signal-fg:      oklch(14% 0.01 250);
  --signal-soft:    oklch(36% 0.10 230);

  --positive:       oklch(74% 0.16 152);
  --warning:        oklch(80% 0.16 80);
  --negative:       oklch(70% 0.20 25);
  --neutral:        oklch(72% 0.04 250);

  --pulse-low:      var(--positive);
  --pulse-mid:      var(--warning);
  --pulse-high:     var(--negative);
  --pulse-extreme:  oklch(60% 0.24 15);

  --ring:           oklch(78% 0.16 230 / 0.6);

  --radius-sm: 4px; --radius-md: 6px; --radius-lg: 10px; --radius-xl: 16px;

  --shadow-sm: 0 1px 0 0 oklch(0% 0 0 / 0.4);
  --shadow-md: 0 4px 12px -2px oklch(0% 0 0 / 0.4), 0 0 0 1px var(--border-subtle);
  --shadow-popover: 0 16px 40px -8px oklch(0% 0 0 / 0.6), 0 0 0 1px var(--border-default);
}

[data-theme="light"] {
  /* Inverted scale; same semantic tokens recomputed. */
}
```

### 4.3 Tailwind v4 wiring (`src/frontend/styles/globals.css`)

```css
@import "tailwindcss";
@import "./tokens.css";

@theme {
  --color-surface-0: var(--surface-0);
  --color-surface-1: var(--surface-1);
  --color-surface-2: var(--surface-2);
  --color-text:      var(--text-primary);
  --color-muted:     var(--text-muted);
  --color-signal:    var(--signal);
  --color-positive:  var(--positive);
  --color-warning:   var(--warning);
  --color-negative:  var(--negative);

  --font-sans: "Inter", ui-sans-serif, system-ui, sans-serif;
  --font-mono: "JetBrains Mono", ui-monospace, monospace;

  --breakpoint-sm: 375px;
  --breakpoint-md: 768px;
  --breakpoint-lg: 1280px;
  --breakpoint-xl: 1440px;

  --radius-md: 6px;
  --radius-lg: 10px;
}

@layer base {
  html { color-scheme: dark; }
  body {
    background: var(--surface-0);
    color: var(--text-primary);
    font-family: var(--font-sans);
    font-feature-settings: "cv11", "ss01";
    -webkit-font-smoothing: antialiased;
  }
  .tabular { font-variant-numeric: tabular-nums; }
  @media (prefers-reduced-motion: reduce) {
    *, *::before, *::after {
      animation-duration: 0.01ms !important;
      transition-duration: 0.01ms !important;
    }
  }
}
```

### 4.4 Typography scale

| Token | px / line | Use |
|---|---|---|
| `text-xs`  | 11 / 16 | metadata, captions |
| `text-sm`  | 13 / 18 | dense tables, secondary |
| `text-base`| 14 / 20 | body, panels |
| `text-md`  | 15 / 22 | brief paragraphs |
| `text-lg`  | 17 / 24 | section headers |
| `text-xl`  | 20 / 26 | page subheaders |
| `text-2xl` | 24 / 30 | page titles |
| `text-3xl` | 30 / 36 | hero stat values |

Numerics use `font-mono` + `.tabular`. Body weight ≤ 500; headers 600;
display tracking `-0.01em` at `text-2xl+`.

### 4.5 Spacing & layout primitives

- Page gutter: `px-6` (lg+), `px-4` (md), `px-3` (sm).
- Card padding: `p-4` default, `p-6` hero.
- Section gap: `gap-6` between blocks, `gap-3` inside cards.
- Right side-panel: `w-[360px]` lg / `w-[280px]` md / Drawer below md.
- TopNav height `h-12` (48px). Sidebar `w-14` collapsed / `w-56` expanded.

### 4.6 shadcn primitives installed in Phase 1

`button`, `input`, `label`, `textarea`, `select`, `checkbox`, `radio-group`,
`switch`, `card`, `badge`, `separator`, `tabs`, `dialog`, `sheet`,
`dropdown-menu`, `popover`, `tooltip`, `command`, `scroll-area`, `skeleton`,
`alert`, `avatar`, `toast` (via sonner).

Each one re-themes via `class-variance-authority` to use our `--color-*`
tokens.

### 4.7 Iconography

`lucide-react`, `strokeWidth={1.5}`. Sizes: 16 tables, 18 nav, 20 headers.
Emoji only inside user-generated content (briefs, Q&A), never as UI signal.

### 4.8 Data-viz palette

Charts and Map pulses share one ordinal scale:
- Risk: `positive → neutral → warning → negative → extreme`
- Score (diverging around 0): `negative ↔ neutral ↔ positive`
- Category (events): 10-step categorical palette from OKLCH 60% lightness ring
  at 36° spacing.

Exported from `src/frontend/lib/viz.ts` as typed arrays.

### 4.9 Motion

- Page transitions: none (instant).
- Panel/Drawer enter: `x: 24 → 0`, `opacity: 0 → 1`, `duration: 0.18`,
  ease `[0.22, 1, 0.36, 1]`.
- Popover/Dropdown: `scale: 0.96 → 1`, `opacity: 0 → 1`, `duration: 0.12`.
- Toast: slide from bottom-right, auto-dismiss 5 s.
- Map pulses: CSS `@keyframes` only (performance).
- `prefers-reduced-motion` honoured globally via `globals.css`.

### 4.10 Accessibility baseline (REQ-N-013)

- All shadcn primitives are Radix-based → keyboard + SR correct by default.
- Contrast: `--text-primary` on `--surface-0` ≥ 13.5:1; `--text-secondary`
  ≥ 7:1; `--text-muted` ≥ 4.5:1.
- Focus ring on every interactive element:
  `focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--ring)]`.
  Never `outline-none` without a replacement ring.
- Skip-to-content link in `AppShell`.
- Live regions on Toast container and any future result-count counters.
- `eslint-plugin-jsx-a11y` runs in CI.

### 4.11 Responsive strategy (REQ-N-014)

Breakpoints `sm/md/lg/xl = 375/768/1280/1440`.
- Desktop-first surfaces (Map, Screener, Company Detail, AI Audit, Indicator
  Builder): collapse at `md` to single column with drawers; map shows a
  "best on desktop" hint at `sm`.
- Mobile-first surfaces (Briefs Reader, Alerts Center, Q&A, Onboarding,
  Auth): scale up gracefully.
- `AppShell` swaps `TopNav` (desktop) for `MobileNav` bottom-sheet at `sm`.

---

## 5. App shell & authentication

### 5.1 Composition root

```tsx
// main.tsx
createRoot(root).render(<React.StrictMode><App /></React.StrictMode>);
```

```tsx
// app/App.tsx
<ErrorBoundary>
  <ThemeProvider>
    <QueryProvider>
      <AuthProvider>
        <BrowserRouter>
          <AppRouter />
        </BrowserRouter>
        <Toaster />
      </AuthProvider>
    </QueryProvider>
  </ThemeProvider>
</ErrorBoundary>
```

Provider-order invariants:
- `ErrorBoundary` outermost — survives any provider crash.
- `ThemeProvider` before any visual provider so first paint has correct
  `[data-theme]`.
- `QueryProvider` before `AuthProvider` (auth uses `useQuery('/me')`).
- `BrowserRouter` inside auth so guards can read `useAuth()`.

### 5.2 QueryProvider

One `QueryClient`. Defaults: `staleTime: 30_000`,
`retry` only on `>=500` and < 2 attempts, `refetchOnWindowFocus: false`,
mutations no retry. `<ReactQueryDevtools />` only when `import.meta.env.DEV`.
Query keys via `qk(resource, ...ids)` helper from `lib/api/keys.ts`.

### 5.3 ThemeProvider

Wraps `next-themes`:
```
attribute="data-theme", defaultTheme="dark", enableSystem,
disableTransitionOnChange, themes=["dark","light"]
```
Persists to `localStorage('stokai-theme')`. Toggle in `TopNav` user menu.

### 5.4 AuthProvider

Owns the JWT, the current user, and login/logout. All features call
`useAuth()` or `useCurrentUser()`.

**Storage strategy:**
- Access token in **memory only** (module-scoped variable in
  `lib/api/client.ts`).
- Refresh token in an **httpOnly cookie** set by the backend on login:
  `Set-Cookie: stokai_refresh=...; HttpOnly; Secure; SameSite=Lax; Path=/api/v1/auth`.
- On mount, `AuthProvider` calls `POST /api/v1/auth/refresh` (cookie sent
  automatically). On 200 → store access token + call `GET /api/v1/me`. On
  401 → `state = anonymous` → router renders `/login`.
- Token auto-refresh: `setTimeout` scheduled for `exp - 60s` calls
  `/auth/refresh`. On failure → forced logout +
  redirect `/login?reason=session_expired`.
- A single in-flight refresh promise prevents racing parallel API calls.

**Shape:**
```ts
type AuthState =
  | { status: "loading" }
  | { status: "authenticated"; user: CurrentUser }
  | { status: "anonymous" };

interface AuthContextValue {
  state: AuthState;
  login(email: string, password: string): Promise<void>;
  register(payload: RegisterPayload): Promise<void>;
  logout(): Promise<void>;
}

interface CurrentUser {
  id: string;
  email: string;
  username: string;
  role: "user" | "admin";
  tenantId: string;
  onboardingComplete: boolean;
  features: string[];
}
```

`useCurrentUser()` is sugar that throws if not `authenticated` — for use
inside `<RequireAuth>` subtrees.

### 5.5 API client (`lib/api/client.ts`)

```ts
export async function api<T>(
  path: string,
  init?: RequestInit & { skipAuth?: boolean }
): Promise<T>;
```

Responsibilities:
1. Prefix `path` with `/api/v1`.
2. Attach `Authorization: Bearer <accessToken>` (unless `skipAuth`).
3. JSON serialize/parse.
4. On 401 → one silent `/auth/refresh` → retry once. Still 401 → emit
   `auth:expired` event → AuthProvider forces logout.
5. On non-2xx → throw `ApiError(status, code, message, details, requestId)`.
6. Unwrap `{ data, meta, error }` → return `data`.

Also export:
- `apiStream(path, { onEvent, onError })` for SSE.
- `apiSocket(path, { onMessage, onClose })` for WS.

**Lint rule:** `lib/api/client.ts` is the only file allowed to call `fetch`
against `/api/...`. Same for `EventSource` / `WebSocket`.

### 5.6 Router & route guards

`src/frontend/app/routes.ts` — pure constants:

```ts
export const ROUTES = {
  // Public
  login:        "/login",
  register:     "/register",
  // App
  home:         "/",
  onboarding:   "/onboarding",
  briefs:       "/briefs",
  brief:        "/briefs/:briefId",
  screener:     "/screener",
  company:      "/companies/:ticker",
  portfolio:    "/portfolio",
  watchlist:    "/watchlist",
  alerts:       "/alerts",
  qa:           "/qa",
  events:       "/events/:eventId/deep-dive",
  // Admin
  adminHil:     "/admin/hil",
  adminSources: "/admin/sources",
  adminSystem:  "/admin/system",
  adminAudit:   "/admin/ai-audit",
} as const;
```

`src/frontend/app/router.tsx` — every route mounted:

```tsx
<Routes>
  <Route path={ROUTES.login}    element={<LoginPage />} />
  <Route path={ROUTES.register} element={<RegisterPage />} />

  <Route element={<RequireAuth><AppShell /></RequireAuth>}>
    <Route path={ROUTES.onboarding} element={<OnboardingFlow />} />

    <Route element={<OnboardingGate />}>
      <Route path={ROUTES.home}      element={<ComingSoon plan="PLAN-F-019" />} />
      <Route path={ROUTES.briefs}    element={<ComingSoon plan="PLAN-F-026" />} />
      <Route path={ROUTES.brief}     element={<ComingSoon plan="PLAN-F-026" />} />
      <Route path={ROUTES.screener}  element={<ComingSoon plan="PLAN-F-022" />} />
      <Route path={ROUTES.company}   element={<ComingSoon plan="PLAN-F-023" />} />
      <Route path={ROUTES.portfolio} element={<ComingSoon plan="PLAN-F-024" />} />
      <Route path={ROUTES.watchlist} element={<ComingSoon plan="PLAN-F-024" />} />
      <Route path={ROUTES.alerts}    element={<ComingSoon plan="PLAN-F-025" />} />
      <Route path={ROUTES.qa}        element={<ComingSoon plan="PLAN-F-027" />} />
      <Route path={ROUTES.events}    element={<ComingSoon plan="PLAN-F-020" />} />

      <Route element={<RequireAdmin><AdminLayout /></RequireAdmin>}>
        <Route path={ROUTES.adminHil}     element={<HilQueue />} />
        <Route path={ROUTES.adminSources} element={<SourcesPage />} />
        <Route path={ROUTES.adminSystem}  element={<SystemOpsPage />} />
        <Route path={ROUTES.adminAudit}   element={<ComingSoon plan="PLAN-F-029" />} />
      </Route>
    </Route>
  </Route>

  <Route path="*" element={<NotFound />} />
</Routes>
```

`<ComingSoon plan="…" />` displays the plan ID, the requirement title pulled
from a static `REQ_TITLES` map, and a back link. Never blank, never "TODO".

Guards:
- `<RequireAuth>` — loading → skeleton; anonymous → redirect to `/login` with
  `from` preserved; authenticated → `<Outlet />`.
- `<RequireAdmin>` — assumes auth; non-admin → `<AccessDenied />` panel.
- `<OnboardingGate>` — if `!user.onboardingComplete` and path != `/onboarding`,
  redirect to `/onboarding`; else `<Outlet />`.

### 5.7 AppShell

- `TopNav` at `lg+`: brand left, primary nav center, user menu + theme toggle +
  cmd-k trigger right. Height `h-12`.
- `Sidebar` opt-in per route via outlet context.
- `MobileNav` at `sm`: bottom bar (4 routes) + user menu in a `<Sheet>` from
  top-right.
- Global `<CommandPalette />` (`⌘K` / `Ctrl+K`) lists routes + actions.
- Health-check gate: `useQuery(["health"], …)` on mount. On failure renders a
  full-screen "Backend unreachable" panel with retry button + tried URL +
  timeout 3 s.

### 5.8 Login & Register pages

Real, not placeholders.

- `LoginPage`: email + password, react-hook-form + zod, "Forgot password?"
  surfaces a toast saying it's coming. Centered `Card` on `surface-0`, brand
  mark at top.
- `RegisterPage`: email + username + password with strength meter; tenant
  auto-created server-side (REQ-F-033 MVP boundary).
- Both call `auth.login()` / `auth.register()` only — never `api()` directly.
- Success → navigate to `from` or `/`. Failure → inline field errors for 400;
  top-of-card alert for 401/429/5xx.

### 5.9 Error boundary & toasts

- `ErrorBoundary` class component: catches render-time errors, logs to console,
  renders a centered "Something went wrong" card + Reload button + error
  digest.
- `Toaster` (sonner): only way features signal transient feedback.
  `lib/toast.ts` exports `toast.success`, `toast.error(err)` (formats
  `ApiError`), `toast.promise(...)`.

---

## 6. Backend integration contract

### 6.1 Standard envelope

Success (2xx):
```json
{ "data": { ... }, "meta": { "request_id": "uuid", "elapsed_ms": 12 } }
```

Failure (4xx/5xx):
```json
{
  "error": {
    "code":    "AUTH_INVALID_CREDENTIALS",
    "message": "Email or password is incorrect.",
    "details": { "field": "password" },
    "request_id": "uuid"
  }
}
```

The client unwraps `data` or throws `ApiError`. Features never see the raw
envelope.

### 6.2 Error code conventions

| Range | Examples | Frontend behaviour |
|---|---|---|
| `AUTH_*` | `AUTH_INVALID_CREDENTIALS`, `AUTH_TOKEN_EXPIRED`, `AUTH_INSUFFICIENT_ROLE` | Auth flow handles; silent refresh on `TOKEN_EXPIRED`. |
| `VALIDATION_*` | `VALIDATION_FIELD_REQUIRED`, `VALIDATION_FORMAT` | Inline field error from `details.field`. |
| `RATE_LIMIT_*` | `RATE_LIMIT_USER`, `RATE_LIMIT_TENANT` | Toast + retry-after banner from `details.retry_after_sec`. |
| `COST_LIMIT_*` | `COST_LIMIT_DAILY`, `COST_LIMIT_MONTHLY` | Q&A cost-limit notice. |
| `NOT_FOUND` | resource-specific | 404 panel in affected feature. |
| `EXTERNAL_UNAVAILABLE` | LLM / market-data / news provider down | Toast + feature-local fallback. |
| `INTERNAL_ERROR` | catchall 500 | Generic toast; do not trip ErrorBoundary. |

`lib/api/errors.ts` exports typed predicates: `isAuthError`,
`isValidation`, `isRateLimit`, etc.

### 6.3 SSE contract (for Q&A in Phase 2)

```
GET /api/v1/qa/stream?session_id=...
Accept: text/event-stream

event: token  data: {"text": "..."}
event: source data: {"id":"src_1","title":"...","url":"..."}
event: cost   data: {"input_tokens":120,"output_tokens":45,"usd":0.0021}
event: done   data: {"message_id":"msg_..."}
event: error  data: {"code":"EXTERNAL_UNAVAILABLE","message":"..."}
```

Wrapper: `apiStream(path, { onEvent, onError })`. Returns an
`AbortController.abort`. Reuses the same `Authorization` strategy via
`fetch` + `ReadableStream`.

### 6.4 WebSocket contract (for Map feed in Phase 2)

```
WSS /api/v1/events/feed?token=<access_token>
frames: {"type":"event.created","event":{...}}
        {"type":"event.updated","event":{...}}
        {"type":"ping"}            // every 25 s
```

On `4401` close (token expired): trigger `auth.refresh()`; reconnect with
exponential backoff (1 s, 2 s, 4 s, 8 s, max 30 s).

Wrapper exported by `lib/api/ws.ts`.

### 6.5 Backend stub-mode registry

```
GET /api/v1/system/integrations
→ { "data": {
    "llm":         { "provider":"openai",  "mode":"live" },
    "embeddings":  { "provider":"openai",  "mode":"live" },
    "market_data": { "provider":"polygon", "mode":"stub", "reason":"API key not configured" },
    "news":        { "provider":"gdelt",   "mode":"stub", "reason":"License pending" },
    "social":      { "provider":"twitter", "mode":"stub" }
  } }
```

Frontend rules:
- Admin → System page renders the table verbatim.
- Features depending on a stubbed integration render `<StubModeBadge
  integration="market_data" />` next to affected UI.
- Missing integrations (`mode: "missing"`) render an empty state with a link
  to admin.
- Backend stub responses are deterministic (seeded fixtures) so tests and
  screenshots are stable.

### 6.6 Environment

Frontend env (only these allowed):
```
VITE_API_BASE_URL=/api/v1
VITE_WS_BASE_URL=
VITE_APP_NAME=StokAI
VITE_SENTRY_DSN=
VITE_ENABLE_DEVTOOLS=true
```

Read through `lib/env.ts` (zod-validated at startup). No `process.env` in
feature code. No secrets in frontend env (Sentry DSN is the only public key
allowed).

### 6.7 Vite proxy

```ts
server: {
  port: 5173,
  proxy: {
    "/api":    { target: "http://localhost:8000", changeOrigin: true },
    "/health": { target: "http://localhost:8000", changeOrigin: true },
    "/ws":     { target: "ws://localhost:8000",   ws: true, changeOrigin: true },
  },
}
```

Production: FastAPI mounts the built SPA on the same origin → no CORS.

### 6.8 API contract drift detection

Every feature module declares its expected response shape with zod:

```ts
const BriefSchema = z.object({ id: z.string(), title: z.string(), html: z.string() });
type Brief = z.infer<typeof BriefSchema>;
export const fetchBrief = (id: string) =>
  api<unknown>(`/briefs/${id}`).then(d => BriefSchema.parse(d));
```

Parse failures throw `ApiError(0, "CONTRACT_MISMATCH", ...)` with the zod
issues. Surface as a developer toast in dev; generic "Data error" toast in
prod.

### 6.9 Phase 1 backend dependencies

These endpoints must exist and conform for Phase 1 to ship:

| Endpoint | Purpose |
|---|---|
| `POST /api/v1/auth/register` | Create user + tenant |
| `POST /api/v1/auth/login` | Issue access token + set refresh cookie. Response `data: { access_token: string, exp: number (unix-seconds) }` |
| `POST /api/v1/auth/refresh` | Rotate tokens (cookie-only). Same response shape as login. |
| `POST /api/v1/auth/logout` | Revoke refresh; clear cookie |
| `GET  /api/v1/me` | Current user |
| `GET  /api/v1/onboarding/state` | Onboarding flag |
| `GET  /api/v1/system/integrations` | Stub-mode registry |
| `GET  /health` | Liveness |

Backend gaps are filed and resolved before Phase 1 closes (Step 15 audit).

---

## 7. Migration plan (15 steps)

Principles: one concern per commit; build green after every step; delete only
at the end; tests follow code; no feature work during migration.

### Step 0 — Safety net
Create branch `phase-1/foundation`. Record baseline state.

### Step 1 — Dependency surgery
Apply `package.json` deltas from §3.3. `npm install`. No code changes.
Commit: `chore(frontend): install Phase 1 deps`.

### Step 2 — Tailwind v4 + tokens
Create `src/frontend/styles/{globals,tokens}.css`. Add `@tailwindcss/vite`
to `vite.config.ts`. Delete obsolete `src/frontend/app/tailwind.config.ts`.
Commit: `feat(frontend): tailwind v4 + design tokens`.

### Step 3 — Vite & TS reconfiguration
Edit `vite.config.ts` (`root: 'src/frontend'`,
`build.outDir: '../../dist/frontend'`, proxy `/api`, `/health`, `/ws`,
alias `@`). Edit `tsconfig.json` (`include`, `paths`). Move `index.html` to
`src/frontend/index.html`; script tag → `/main.tsx`. Build fails until Step 5
(expected).
Commit: `chore(frontend): point Vite/TS at src/frontend`.

### Step 4 — Vitest replaces Jest
Delete `jest.config.js`. Create `vitest.config.ts` extending Vite. Move
`tests/frontend/__mocks__/*` content into vitest `setupTests.ts` only where
still needed. Convert `setupTests.ts` to import
`@testing-library/jest-dom/vitest`. Update scripts (§3.3).
Commit: `chore(frontend): replace Jest with Vitest`.

### Step 5 — App shell skeleton
Create `src/frontend/main.tsx`, `app/App.tsx`, `app/providers/*` (pass-through
stubs), `app/router.tsx` (single catch-all route). `npm run dev` must show
content on every path. **First green light.**
Commit: `feat(frontend): app shell skeleton`.

### Step 6 — API client + env validation (TDD)
Implement `lib/env.ts`, `lib/api/{client,errors,types,keys,stream,ws}.ts`.
Vitest tests for `client.ts` envelope handling, error throw, 401 silent
refresh, in-flight refresh dedup, query-key helper. msw for HTTP mocking.
Commit: `feat(frontend): typed API client + zod-validated env`.

### Step 7 — Auth provider + login/register + guards (TDD)
Implement `AuthProvider`, `useAuth`, `useCurrentUser`. Implement
`RequireAuth`, `RequireAdmin`, `OnboardingGate`. Build `LoginPage`,
`RegisterPage`. Install shadcn primitives as needed. Wire providers in
`App.tsx` in the order defined in §5.1. Visiting `/` redirects anonymous to
`/login`. **Second green light.**
Commit: `feat(frontend): auth flow + route guards + login/register`.

### Step 8 — Layout + nav + command palette + health gate
Build `AppShell`, `TopNav`, `MobileNav`, `Sidebar`, `CommandPalette`. Add
`Toaster`. Add theme toggle. Add health-check gate.
Commit: `feat(frontend): app shell layout, navigation, command palette, health gate`.

### Step 9 — Mount full route map with `<ComingSoon>`
Implement `<ComingSoon plan="…" />`. Replace skeleton router with full
route tree (§5.6). All routes return 200. **Third green light.**
Commit: `feat(frontend): mount full route map with placeholders`.

### Step 10 — Migrate admin pages

| From | To | Notes |
|---|---|---|
| `frontend/src/pages/admin/HilQueue.tsx` | `src/frontend/pages/admin/hil/HilQueue.tsx` | Re-skin |
| `frontend/src/components/admin/hil/*` | `src/frontend/pages/admin/hil/*` | Colocated |
| `frontend/src/pages/admin/sources/**/*` | `src/frontend/pages/admin/sources/**/*` | Re-skin entry |
| `frontend/src/pages/admin/AdminNav.tsx` | DELETE (replaced by AdminLayout) | |
| `frontend/src/pages/admin/system/*` | merge into `src/frontend/pages/admin/system/*` | Step 11 |
| `src/frontend/admin/AdminLayout.tsx` | `src/frontend/pages/admin/AdminLayout.tsx` | shadcn Tabs |
| `src/frontend/admin/RequireAdmin.tsx` | `src/frontend/app/guards/RequireAdmin.tsx` | |

Per module: update imports to `@/...`, swap classes to Tailwind tokens, run
tests, fix until green.

### Step 11 — Resolve duplicates

| Canonical (keep) | Delete |
|---|---|
| `src/frontend/pages/admin/system/CostMonitorTab.tsx` | `frontend/src/pages/admin/system/CostMonitorTab.tsx` |
| `src/frontend/pages/admin/system/IngestionJobsTab.tsx` | `frontend/src/pages/admin/system/IngestionJobsTab.tsx` |
| `src/frontend/hooks/useSystemOps.ts` | `frontend/src/pages/admin/system/hooks/useSystemOps.ts` |
| `src/frontend/components/qa/*` | `frontend/src/components/qa/*` |
| `src/frontend/api/qaApi.ts` | `frontend/src/api/qaApi.ts` |

Commit: `refactor(frontend): resolve duplicate modules across trees`.

### Step 12 — Reorganize remaining `src/frontend/`

| From | To |
|---|---|
| `src/frontend/admin/ai-audit/*` | `src/frontend/pages/admin/ai-audit/*` |
| `src/frontend/features/intelligence-map/*` | unchanged |
| `src/frontend/features/progressive-disclosure/*` | unchanged |
| `src/frontend/features/screener/*` | unchanged |
| `src/frontend/features/briefs/*` | unchanged |
| `src/frontend/features/portfolio/*` | unchanged |
| `src/frontend/features/onboarding/*` | unchanged |
| `src/frontend/pages/CompanyDetail/*` | `src/frontend/features/company-detail/*` |
| `src/frontend/pages/AlertsCenterPage.tsx` + `components/alerts/*` + `hooks/useAlerts*` | `src/frontend/features/alerts/*` |
| `src/frontend/components/indicator-builder/*` | `src/frontend/features/indicator-builder/*` |
| `src/frontend/components/scoring/*` | `src/frontend/features/scoring/*` |
| `src/frontend/features/map/EventPopup.tsx` | merge into `features/progressive-disclosure/components/EventPopup.tsx` |
| `src/frontend/components/layout/TopNav.tsx` | DELETE (replaced) |
| `src/frontend/pages/MapPage.tsx` | DELETE (deep-link is component-level in Phase 2) |
| `src/frontend/hooks/usePortfolioContext.ts` | `src/frontend/features/portfolio/usePortfolioContext.ts` |
| `src/frontend/hooks/useCurrentUser.ts` (old) | DELETE (use `AuthProvider#useCurrentUser`) |

Features still render only via `<ComingSoon>` — wiring is Phase 2.

### Step 13 — Repair broken local imports
Create `src/frontend/features/intelligence-map/lib/empty-state-message.ts`
and `time-mode-empty-state.ts` (stubs satisfying existing tests). Run
`tsc --noEmit`; fix every reported import.
Commit: `fix(frontend): repair broken local imports surfaced by tsc`.

### Step 14 — Test migration
For each `tests/frontend/*` file: update imports to `@/...`; swap
`jest.*` → `vi.*`; remove ts-jest-specifics. Delete tests for code removed
in 10–12. Mark Phase 2/3 wiring tests `.skip` with explanatory comment.
`npm run test` green for kept code.
Commit: `test(frontend): migrate test suite to vitest`.

### Step 15 — Cleanup + backend audit
`rm -rf frontend/`. Delete orphaned `__mocks__/`. Run
`typecheck && lint && test && build` — all green. Backend audit confirms
every endpoint in §6.9 conforms; failures filed as backend tasks under
Phase 1. Update `docs/ARCHITECTURE.md` and `src/frontend/README.md`.
Commit: `chore(frontend): retire legacy frontend/ tree; phase 1 complete`.

### 7.1 Per-step complexity

| Step | Complexity |
|---|---|
| 0 Safety net | S |
| 1 Deps | S |
| 2 Tailwind | S |
| 3 Vite/TS | S |
| 4 Vitest | M |
| 5 Skeleton | S |
| 6 API client | L |
| 7 Auth | L |
| 8 Layout | L |
| 9 Routes | S |
| 10 Admin migrate | M |
| 11 Dedupe | M |
| 12 Reorg | L |
| 13 Broken imports | M |
| 14 Tests | L |
| 15 Cleanup | S |

Total: ~5 L, 5 M, 6 S.

---

## 8. Testing strategy

- **TDD for foundation pieces** (Steps 6, 7): API client behaviours, refresh
  dedup, error model, env validation, auth flow, guard redirects, role gates,
  query-key helper. Coverage target ≥ 80% lines on these modules.
- **No tests for pure file moves** (Steps 10–12): existing tests move with
  their source; we update import paths only.
- **`.skip` for Phase 2/3 wiring tests** (Step 14): keep the assertions,
  mark intent, prevent rot.
- **No frontend mocking of backend behaviour** outside vitest tests. msw is
  test-time only.
- **A11y lint** runs in CI (`eslint-plugin-jsx-a11y`).
- **Build check** in CI: `typecheck && lint && test && build`.

---

## 9. Acceptance criteria

Phase 1 is "done" when **every** AC below is true.

**AC-1 — Repo structure**
- `frontend/` does not exist.
- Repo-root `index.html` does not exist.
- `src/frontend/` matches §2.
- `vite.config.ts`, `tsconfig.json`, `vitest.config.ts` point at
  `src/frontend`.

**AC-2 — Build & run**
- `npm install` completes without peer-dep conflict warnings.
- `npm run typecheck` exits 0.
- `npm run lint --max-warnings=0` exits 0.
- `npm run build` produces `dist/frontend/`.
- `npm run dev` serves on port 5173 within 5 s.
- `docker compose up` makes the app reachable end-to-end through the proxy.

**AC-3 — Tests**
- `npm run test` runs vitest; no Jest references in the repo.
- All tests for retained code pass.
- Phase 2/3 wiring tests are `.skip` with comments.
- New shell modules have ≥ 80% line coverage.

**AC-4 — Visual system**
- `styles/globals.css` imports Tailwind v4 + `tokens.css`.
- `[data-theme="dark"]` default; `[data-theme="light"]` works and persists.
- No `style={{}}` color/spacing in feature/layout files (lint).
- shadcn primitives from §4.6 exist under `ui/` and re-export from
  `ui/index.ts`.
- Keyboard tabbing reveals focus rings on every interactive element.
- Lighthouse accessibility ≥ 95 on `/login` and `/`.

**AC-5 — App shell**
- `App.tsx` provider order matches §5.1.
- `AppShell` renders `TopNav` at `lg+` and `MobileNav` at `sm`, swap at `md`.
- `CommandPalette` opens on `⌘K` / `Ctrl+K`; navigates to every primary route.
- Theme toggle changes theme without flash.
- `ErrorBoundary` renders fallback for deliberately thrown error (smoke test).

**AC-6 — Authentication**
- Anonymous user on non-public route → redirect to `/login` preserving `from`.
- Successful login stores access token in memory; refresh in httpOnly cookie
  set by backend.
- 401 from any API call triggers exactly one silent `/auth/refresh`; on
  success retry once; on failure logout + redirect
  `/login?reason=session_expired`.
- Hard-refresh on a deep route preserves session via refresh cookie.
- Registration logs in immediately and lands on `/onboarding`.
- `/admin/*` renders `AccessDenied` for non-admin.

**AC-7 — Onboarding**
- If `me.onboarding_complete === false`, user is redirected to `/onboarding`
  regardless of intended URL.
- Completing or skipping onboarding lands the user on the originally-requested
  route.

**AC-8 — Routes**
- Every path in `ROUTES` returns 200 and renders content.
- `<ComingSoon plan="…" />` shows plan ID, requirement title, back link;
  never blank, never "TODO".
- Reachable real content: `/login`, `/register`, `/onboarding`, `/admin/hil`,
  `/admin/sources`, `/admin/system`.
- `/admin/ai-audit` renders `<ComingSoon plan="PLAN-F-029" />`.

**AC-9 — Backend contract**
- `lib/api/client.ts` is the only file calling `fetch` against `/api/...`
  (lint rule).
- All responses unwrap from the envelope; `ApiError` thrown on non-2xx.
- `lib/env.ts` zod-validates env at startup; missing required vars crash with
  a clear console message.
- Health-check gate renders "Backend unreachable" panel on `/health` 5xx or
  3 s timeout.
- `GET /api/v1/system/integrations` exists on backend and conforms to §6.5.

**AC-10 — Honest UI**
- No frontend file contains static fixture data used as response data (lint:
  no `MOCK_*` / `FIXTURE_*` array exports outside `tests/`).
- `<StubModeBadge>` component exists and renders when relevant integration is
  `mode === "stub"`.

**AC-11 — Documentation**
- `docs/ARCHITECTURE.md` updated with consolidated layout + provider stack.
- `USER-GUIDE.md` updated with new `npm` scripts.
- `src/frontend/README.md` documents the `features/` convention.

---

## 10. Risks

| Risk | Mitigation |
|---|---|
| Vite 8 + `@tailwindcss/vite` + `@vitejs/plugin-react-swc` version interplay | Pin versions; Step 2 hello-world smoke build before progressing. |
| Existing tests depend on Jest-only behaviour | Catalog at Step 4; port or delete with a `// Phase X:` ticket. |
| Backend endpoints diverge from §6.9 contract | Step 15 audit; backend tasks filed under Phase 1. |
| Colocated `*.test.tsx` next to source vs `tests/frontend/` convention | Decision: keep colocation; vitest collects both. |
| Deleting `frontend/` while git tree is dirty | Step 15 runs only after green build; verify before deletion. |
| Shadcn install churn | Install primitives one at a time alongside their first consumer; review each generated file. |
| Auth refresh race under parallel API calls | Single in-flight refresh promise; covered by Step 6 tests. |
| Visual tokens too rigid for Phase 2 screens | Token additions explicitly allowed in Phase 2; design system files are owned code. |

---

## 11. Phase 2 / Phase 3 preview (not scope)

### Phase 2 — Hero screens, wired live

| Route | Feature | Plan |
|---|---|---|
| `/` | Intelligence Map + Time-mode | PLAN-F-019, F-021 |
| `/events/:eventId/deep-dive` + popup/sidepanel | Progressive Disclosure | PLAN-F-020 |
| `/briefs`, `/briefs/:id` | Briefs Reader | PLAN-F-026 |
| `/qa` | Q&A Chat (SSE) | PLAN-F-027 |
| `/companies/:ticker` | Company Detail + Analyze-Now | PLAN-F-023 |
| `/admin/ai-audit` | AI Audit Console | PLAN-F-029 |

Phase 2 depends on Phase 1's: `lib/api/client.ts`, `stream.ts`, `ws.ts`,
`useAuth`, guards, visual tokens, shadcn primitives, `<StubModeBadge>`.

### Phase 3 — Remaining + polish

| Route | Feature | Plan |
|---|---|---|
| `/screener` | Screener | PLAN-F-022 |
| `/portfolio`, `/watchlist` | Portfolio + Watchlist | PLAN-F-024 |
| `/alerts` | Alerts Center | PLAN-F-025 |
| Inside Company Detail | Indicator Builder | PLAN-F-017 |
| All routes | Responsive sweep | PLAN-N-014 |
| All routes | Accessibility sweep | REQ-N-013 |
| Infra | Sentry RUM, Storybook for `ui/`, Lighthouse-CI | — |

---

## 12. End-state demo script

> Visit `http://localhost:5173`. See a dark, polished login screen. Register
> with email and password. Land on a clean onboarding flow. Complete or skip.
> Land on the Intelligence Map's `<ComingSoon plan="PLAN-F-019" />` card, with
> full top navigation, working theme toggle, command palette, mobile/desktop
> responsive shell, and admin routes (HIL, Sources, System) that work against
> the real backend. Backend down → "Backend unreachable" panel with retry,
> not a white screen. Token expires mid-session → silent refresh, no visible
> glitch. Every page shares typography, spacing, focus states, motion. The
> product *feels* finished — that is Phase 1 done.

---

## 13. Open items for follow-up specs

- **Phase 2 spec** — to be written after Phase 1 ships, scoped to the six
  hero-screen plans above. Will detail SSE/WS consumer wiring, MapLibre
  initialization on screen, deep-link param parsing for `/companies/:ticker`,
  Q&A streaming UX, AI Audit decision-log columns.
- **Phase 3 spec** — to be written after Phase 2 ships. Scoped to the
  remaining feature plans + responsive + a11y + observability tail.
- **Backend audit punch list** — produced in Step 15; tracked separately under
  Phase 1.

---

*End of spec.*
