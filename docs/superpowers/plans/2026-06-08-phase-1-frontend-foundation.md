# Phase 1 — Frontend Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Consolidate the two parallel StokAI frontend trees into a single `src/frontend/` tree with a modern Tailwind v4 + shadcn design system, a working app shell with authentication, full route mounting (real content for Phase-1 routes, `<ComingSoon>` placeholders for Phase 2/3), a typed API client + SSE/WS wrappers, and a Vitest test suite — every route reachable, `npm run build` green, end-to-end via `docker compose`.

**Architecture:** Provider stack (`ErrorBoundary → ThemeProvider → QueryProvider → AuthProvider → BrowserRouter`) drives a `<AppShell>` layout (TopNav/MobileNav + Outlet + Toaster + CommandPalette). All HTTP/SSE/WS traffic goes through `src/frontend/lib/api/*`; auth uses in-memory access token + httpOnly refresh cookie with silent-refresh on 401. Every route is mounted from day one — Phase 2/3 features render via `<ComingSoon plan="…" />` until wired.

**Tech Stack:** Vite 8 + `@vitejs/plugin-react-swc` · React 18.3 · TypeScript 5.4 · Tailwind CSS v4 + `@tailwindcss/vite` · shadcn/ui (Radix-based) · @tanstack/react-query 5 · react-router-dom 6 · react-hook-form + zod · next-themes · sonner · framer-motion · lucide-react · maplibre-gl + supercluster (deps installed; consumer in Phase 2) · dompurify · Vitest 2 + msw 2 + jsdom.

**Spec reference:** `docs/superpowers/specs/2026-06-08-phase-1-frontend-foundation-design.md`. All section references below (e.g. §5.1) point to that spec.

---

## File structure (target end-state)

Created during this plan (new):
```
src/frontend/
├─ index.html                                 (moved from repo root)
├─ main.tsx
├─ app/
│  ├─ App.tsx
│  ├─ router.tsx
│  ├─ routes.ts
│  ├─ providers/{Query,Theme,Auth,ErrorBoundary}.tsx
│  └─ guards/{RequireAuth,RequireAdmin,OnboardingGate}.tsx
├─ layout/{AppShell,TopNav,Sidebar,MobileNav,CommandPalette}.tsx
├─ ui/                                         (shadcn primitives + index.ts)
├─ lib/
│  ├─ api/{client,stream,ws,errors,types,keys}.ts
│  ├─ env.ts
│  ├─ cn.ts
│  ├─ format.ts
│  └─ viz.ts
├─ hooks/{useBreakpoint,useTheme}.ts
├─ features/auth/{LoginPage,RegisterPage,authApi,authSchemas}.tsx
└─ styles/{globals,tokens}.css
```

Reorganised (moved into `src/frontend/`):
- Everything currently under `src/frontend/admin/ai-audit/` → `src/frontend/pages/admin/ai-audit/`
- Everything currently under `src/frontend/pages/CompanyDetail/` → `src/frontend/features/company-detail/`
- `src/frontend/pages/AlertsCenterPage.tsx` + `components/alerts/*` + `hooks/useAlerts*.ts` → `src/frontend/features/alerts/`
- `src/frontend/components/indicator-builder/*` → `src/frontend/features/indicator-builder/`
- `src/frontend/components/scoring/*` → `src/frontend/features/scoring/`
- `frontend/src/pages/admin/HilQueue.tsx` + `components/admin/hil/*` → `src/frontend/pages/admin/hil/`
- `frontend/src/pages/admin/sources/*` → `src/frontend/pages/admin/sources/`
- `src/frontend/admin/AdminLayout.tsx` → `src/frontend/pages/admin/AdminLayout.tsx`
- `src/frontend/admin/RequireAdmin.tsx` → `src/frontend/app/guards/RequireAdmin.tsx`

Deleted:
- Entire `frontend/` directory at repo root
- `index.html` at repo root
- `jest.config.js`
- `src/frontend/components/layout/TopNav.tsx` (replaced)
- `src/frontend/pages/MapPage.tsx` (Phase 2 handles deep-link at component level)
- `src/frontend/features/map/EventPopup.tsx` (duplicate)
- `src/frontend/hooks/useCurrentUser.ts` (replaced by AuthProvider)
- Duplicates: `frontend/src/components/qa/*`, `frontend/src/api/qaApi.ts`, `frontend/src/pages/admin/system/{CostMonitorTab,IngestionJobsTab}.tsx`, `frontend/src/pages/admin/system/hooks/useSystemOps.ts`, `frontend/src/pages/admin/AdminNav.tsx`
- `src/frontend/app/tailwind.config.ts` (Tailwind v4 reads from CSS)

Configuration (modified):
- `package.json` — new deps, scripts (vite/vitest/lint)
- `vite.config.ts` — `root: 'src/frontend'`
- `tsconfig.json` — `include: ['src/frontend']`, `paths: { '@/*' }`
- `vitest.config.ts` — new
- `docs/ARCHITECTURE.md` — updated layout section
- `USER-GUIDE.md` — updated `npm` scripts

---

## Conventions used throughout this plan

- All file paths absolute from repo root. Replace `<repo>` with `B:\development\python_space\stokai` when running locally.
- `npm` commands run from repo root.
- Each Task ends with a commit. Commit subjects use conventional commits (`feat(frontend): …`, `chore(frontend): …`, etc.).
- TDD tasks: write failing test → run to confirm failure → implement → run to confirm pass → commit.
- "Run: `<cmd>` — Expected: `<output>`" steps mean the engineer should run the command and verify the expected outcome before continuing.
- When a step says "paste the following into `<file>`", the file does not yet exist (create it) unless the task lists it under "Modify".

---

## Task 1: Safety net — branch + baseline

**Files:**
- No file changes.

- [ ] **Step 1.1: Verify clean working tree**

Run: `git status --short`
Expected: only the pre-existing tracked changes from the conversation start (USER-GUIDE.md plus node_modules churn) — no surprise files.

- [ ] **Step 1.2: Create the Phase 1 branch**

Run: `git checkout -b phase-1/foundation`
Expected: `Switched to a new branch 'phase-1/foundation'`.

- [ ] **Step 1.3: Record baseline — does the current app start?**

Run: `npm run dev`
Expected: Vite serves on `http://localhost:5173` (or 5174/5175 if those ports are occupied). Open the URL in a browser. Confirm `/` shows the literal text `Home` and `/admin/hil`, `/admin/sources`, `/admin/system` render. Then `Ctrl+C` to stop the server.

- [ ] **Step 1.4: Record baseline — Jest test pass/fail counts**

Run: `npm test -- --listTests 2>&1 | wc -l && npm test 2>&1 | tail -30`
Expected: a number of tests; record the passing/failing/total counts in a scratch note. This number is used at Task 34 to confirm we did not regress test coverage on retained code.

- [ ] **Step 1.5: Commit the branch baseline (none — branch only)**

No commit yet (no file changes).

---

## Task 2: Install Phase 1 dependencies

**Files:**
- Modify: `package.json`

- [ ] **Step 2.1: Replace `package.json` with Phase 1 deps**

Open `package.json` and replace its contents with:

```json
{
  "name": "stokai-frontend",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview",
    "test": "vitest run",
    "test:watch": "vitest",
    "test:coverage": "vitest run --coverage",
    "lint": "eslint src/frontend tests/frontend --max-warnings=0",
    "format": "prettier --write \"src/frontend/**/*.{ts,tsx,css,md}\"",
    "typecheck": "tsc --noEmit"
  },
  "dependencies": {
    "@hookform/resolvers": "^3.9.0",
    "@radix-ui/react-dialog": "^1.1.2",
    "@radix-ui/react-dropdown-menu": "^2.1.2",
    "@radix-ui/react-popover": "^1.1.2",
    "@radix-ui/react-scroll-area": "^1.2.1",
    "@radix-ui/react-select": "^2.1.2",
    "@radix-ui/react-separator": "^1.1.0",
    "@radix-ui/react-slot": "^1.1.0",
    "@radix-ui/react-tabs": "^1.1.1",
    "@radix-ui/react-toast": "^1.2.2",
    "@radix-ui/react-tooltip": "^1.1.4",
    "@tanstack/react-query": "^5.40.0",
    "@tanstack/react-query-devtools": "^5.40.0",
    "class-variance-authority": "^0.7.1",
    "clsx": "^2.1.1",
    "cmdk": "^1.0.4",
    "date-fns": "^3.6.0",
    "dompurify": "^3.2.0",
    "framer-motion": "^11.11.0",
    "lucide-react": "^0.460.0",
    "maplibre-gl": "^4.7.1",
    "next-themes": "^0.3.0",
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-hook-form": "^7.53.2",
    "react-router-dom": "^6.26.0",
    "recharts": "^2.12.7",
    "sonner": "^1.7.0",
    "supercluster": "^8.0.1",
    "tailwind-merge": "^2.5.4",
    "zod": "^3.23.8"
  },
  "devDependencies": {
    "@tailwindcss/vite": "^4.0.0",
    "@testing-library/jest-dom": "^6.4.6",
    "@testing-library/react": "^16.0.0",
    "@testing-library/user-event": "^14.5.2",
    "@types/dompurify": "^3.2.0",
    "@types/node": "^20.14.0",
    "@types/react": "^18.3.3",
    "@types/react-dom": "^18.3.0",
    "@types/supercluster": "^7.1.3",
    "@typescript-eslint/eslint-plugin": "^8.10.0",
    "@typescript-eslint/parser": "^8.10.0",
    "@vitejs/plugin-react-swc": "^3.7.0",
    "@vitest/coverage-v8": "^2.1.0",
    "@vitest/ui": "^2.1.0",
    "eslint": "^9.13.0",
    "eslint-plugin-jsx-a11y": "^6.10.0",
    "eslint-plugin-react": "^7.37.0",
    "eslint-plugin-react-hooks": "^5.0.0",
    "jsdom": "^25.0.0",
    "msw": "^2.6.0",
    "prettier": "^3.3.0",
    "prettier-plugin-tailwindcss": "^0.6.8",
    "tailwindcss": "^4.0.0",
    "typescript": "^5.4.5",
    "vite": "^8.0.16",
    "vitest": "^2.1.0"
  }
}
```

- [ ] **Step 2.2: Install**

Run: `npm install`
Expected: completes without errors. If npm exits non-zero, do *not* add `--force`. Read the error, investigate the version conflict, downgrade the offender by one minor, and retry. Record any version pin changes in the commit message.

- [ ] **Step 2.3: Commit**

```bash
git add package.json package-lock.json
git commit -m "chore(frontend): install Phase 1 dependencies (tailwind v4, shadcn deps, vitest, maplibre)"
```

---

## Task 3: Tailwind v4 + design tokens

**Files:**
- Create: `src/frontend/styles/tokens.css`
- Create: `src/frontend/styles/globals.css`
- Delete: `src/frontend/app/tailwind.config.ts`

- [ ] **Step 3.1: Create `src/frontend/styles/tokens.css`**

Paste into the new file:

```css
/* Design tokens — OKLCH for both themes. Section 4.2 of the spec. */

:root,
[data-theme="dark"] {
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

  --radius-sm: 4px;
  --radius-md: 6px;
  --radius-lg: 10px;
  --radius-xl: 16px;

  --shadow-sm: 0 1px 0 0 oklch(0% 0 0 / 0.4);
  --shadow-md: 0 4px 12px -2px oklch(0% 0 0 / 0.4),
               0 0 0 1px var(--border-subtle);
  --shadow-popover: 0 16px 40px -8px oklch(0% 0 0 / 0.6),
                    0 0 0 1px var(--border-default);
}

[data-theme="light"] {
  --surface-0:      oklch(99% 0.003 250);
  --surface-1:      oklch(97% 0.004 250);
  --surface-2:      oklch(94% 0.005 250);
  --surface-3:      oklch(90% 0.006 250);
  --border-subtle:  oklch(88% 0.005 250);
  --border-default: oklch(80% 0.007 250);
  --border-strong:  oklch(64% 0.010 250);

  --text-primary:   oklch(18% 0.012 250);
  --text-secondary: oklch(34% 0.013 250);
  --text-muted:     oklch(50% 0.012 250);
  --text-disabled:  oklch(70% 0.010 250);

  --signal:         oklch(54% 0.18 230);
  --signal-fg:      oklch(99% 0.003 250);
  --signal-soft:    oklch(90% 0.05 230);

  --positive:       oklch(52% 0.16 152);
  --warning:        oklch(64% 0.16 80);
  --negative:       oklch(54% 0.20 25);
  --neutral:        oklch(56% 0.04 250);

  --ring:           oklch(54% 0.18 230 / 0.55);
}
```

- [ ] **Step 3.2: Create `src/frontend/styles/globals.css`**

Paste into the new file:

```css
@import "tailwindcss";
@import "./tokens.css";

@theme {
  --color-surface-0: var(--surface-0);
  --color-surface-1: var(--surface-1);
  --color-surface-2: var(--surface-2);
  --color-surface-3: var(--surface-3);
  --color-text:      var(--text-primary);
  --color-text-secondary: var(--text-secondary);
  --color-muted:     var(--text-muted);
  --color-border:    var(--border-default);
  --color-border-subtle: var(--border-subtle);
  --color-border-strong: var(--border-strong);
  --color-signal:    var(--signal);
  --color-signal-fg: var(--signal-fg);
  --color-signal-soft: var(--signal-soft);
  --color-positive:  var(--positive);
  --color-warning:   var(--warning);
  --color-negative:  var(--negative);
  --color-neutral:   var(--neutral);

  --font-sans: "Inter", ui-sans-serif, system-ui, sans-serif;
  --font-mono: "JetBrains Mono", ui-monospace, monospace;

  --breakpoint-sm: 375px;
  --breakpoint-md: 768px;
  --breakpoint-lg: 1280px;
  --breakpoint-xl: 1440px;

  --radius-md: 6px;
  --radius-lg: 10px;
  --radius-xl: 16px;
}

@layer base {
  html {
    color-scheme: dark;
  }
  body {
    background: var(--surface-0);
    color: var(--text-primary);
    font-family: var(--font-sans);
    font-feature-settings: "cv11", "ss01";
    -webkit-font-smoothing: antialiased;
  }
  .tabular {
    font-variant-numeric: tabular-nums;
  }
  @media (prefers-reduced-motion: reduce) {
    *, *::before, *::after {
      animation-duration: 0.01ms !important;
      transition-duration: 0.01ms !important;
    }
  }
}
```

- [ ] **Step 3.3: Delete the obsolete Tailwind JS config**

Run: `git rm src/frontend/app/tailwind.config.ts`
Expected: file removed (Tailwind v4 reads its theme from CSS).

- [ ] **Step 3.4: Commit**

```bash
git add src/frontend/styles/
git commit -m "feat(frontend): tailwind v4 + design tokens"
```

---

## Task 4: Vite + TypeScript reconfiguration + relocate index.html

**Files:**
- Modify: `vite.config.ts`
- Modify: `tsconfig.json`
- Create: `src/frontend/index.html`
- Delete: `index.html` (repo root)

- [ ] **Step 4.1: Replace `vite.config.ts` contents**

```ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";
import tailwindcss from "@tailwindcss/vite";
import path from "node:path";

export default defineConfig({
  root: "src/frontend",
  publicDir: false,
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src/frontend"),
    },
  },
  server: {
    port: 5173,
    strictPort: false,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
      "/health": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
      "/ws": {
        target: "ws://localhost:8000",
        ws: true,
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "../../dist/frontend",
    emptyOutDir: true,
    sourcemap: true,
  },
});
```

- [ ] **Step 4.2: Replace `tsconfig.json` contents**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "jsx": "react-jsx",
    "moduleResolution": "bundler",
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "forceConsistentCasingInFileNames": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "allowImportingTsExtensions": false,
    "verbatimModuleSyntax": false,
    "baseUrl": ".",
    "paths": {
      "@/*": ["src/frontend/*"]
    },
    "types": ["vite/client", "node"]
  },
  "include": ["src/frontend", "tests/frontend"]
}
```

- [ ] **Step 4.3: Create `src/frontend/index.html`**

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <meta name="color-scheme" content="dark light" />
    <title>StokAI — Geopolitical Intelligence for Retail Investors</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 4.4: Delete the old root `index.html`**

Run: `git rm index.html`
Expected: removed.

- [ ] **Step 4.5: Verify config (build will fail — main.tsx missing — that's expected)**

Run: `npx tsc --noEmit 2>&1 | head -5`
Expected: errors about missing `main.tsx` / `App` imports. We fix this in Task 6.

- [ ] **Step 4.6: Commit**

```bash
git add vite.config.ts tsconfig.json src/frontend/index.html
git commit -m "chore(frontend): point Vite/TS at src/frontend; relocate index.html"
```

---

## Task 5: Replace Jest with Vitest

**Files:**
- Delete: `jest.config.js`
- Create: `vitest.config.ts`
- Modify: `tests/frontend/setupTests.ts`
- Delete: `tests/frontend/__mocks__/styleMock.js`, `dompurify.js`, `maplibre-gl.js` (we install the real packages)

- [ ] **Step 5.1: Delete Jest configuration and mocks**

```bash
git rm jest.config.js
git rm tests/frontend/__mocks__/styleMock.js tests/frontend/__mocks__/dompurify.js tests/frontend/__mocks__/maplibre-gl.js
```

If any of those mock files do not exist, ignore the rm error for that file only.

- [ ] **Step 5.2: Create `vitest.config.ts`**

```ts
import { defineConfig, mergeConfig } from "vitest/config";
import viteConfig from "./vite.config";

export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      globals: true,
      environment: "jsdom",
      setupFiles: ["./tests/frontend/setupTests.ts"],
      include: [
        "src/frontend/**/*.{test,spec}.{ts,tsx}",
        "tests/frontend/**/*.{test,spec}.{ts,tsx}",
      ],
      exclude: ["node_modules", "dist"],
      css: false,
      coverage: {
        provider: "v8",
        reporter: ["text", "html"],
        include: ["src/frontend/**/*.{ts,tsx}"],
        exclude: [
          "src/frontend/**/*.{test,spec}.{ts,tsx}",
          "src/frontend/**/*.d.ts",
          "src/frontend/main.tsx",
          "src/frontend/ui/**",
        ],
      },
    },
  }),
);
```

- [ ] **Step 5.3: Replace `tests/frontend/setupTests.ts`**

```ts
import "@testing-library/jest-dom/vitest";
import { afterEach, vi } from "vitest";
import { cleanup } from "@testing-library/react";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

// jsdom does not implement matchMedia — required by next-themes
if (typeof window !== "undefined" && !window.matchMedia) {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }),
  });
}
```

- [ ] **Step 5.4: Smoke-test Vitest**

Create a temporary smoke test at `src/frontend/_smoke.test.ts`:

```ts
import { describe, it, expect } from "vitest";
describe("vitest smoke", () => {
  it("runs", () => {
    expect(1 + 1).toBe(2);
  });
});
```

Run: `npm test`
Expected: 1 passed test, "vitest smoke > runs". If Vitest fails to start, do not proceed — investigate (typically a `tsconfig` paths mismatch or missing `@vitejs/plugin-react-swc` install).

- [ ] **Step 5.5: Delete the smoke test**

```bash
git rm src/frontend/_smoke.test.ts
```

(Use `rm` if the file is not yet tracked.)

- [ ] **Step 5.6: Commit**

```bash
git add vitest.config.ts tests/frontend/setupTests.ts
git commit -m "chore(frontend): replace Jest with Vitest"
```

---

## Task 6: App shell skeleton

**Files:**
- Create: `src/frontend/main.tsx`
- Create: `src/frontend/app/App.tsx`
- Create: `src/frontend/app/router.tsx`
- Create: `src/frontend/lib/cn.ts`

This task gets `npm run dev` rendering something. No providers yet — they ship in Tasks 12–13.

- [ ] **Step 6.1: Create `src/frontend/lib/cn.ts`**

```ts
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
```

- [ ] **Step 6.2: Create `src/frontend/main.tsx`**

```tsx
import React from "react";
import { createRoot } from "react-dom/client";
import { App } from "./app/App";
import "./styles/globals.css";

const container = document.getElementById("root");
if (!container) {
  throw new Error("Root element #root not found in index.html");
}

createRoot(container).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
```

- [ ] **Step 6.3: Create `src/frontend/app/router.tsx` (skeleton)**

```tsx
import React from "react";
import { Routes, Route } from "react-router-dom";

export function AppRouter() {
  return (
    <Routes>
      <Route
        path="*"
        element={
          <div className="flex min-h-screen items-center justify-center bg-surface-0 text-text">
            <div className="text-lg">Shell OK</div>
          </div>
        }
      />
    </Routes>
  );
}
```

- [ ] **Step 6.4: Create `src/frontend/app/App.tsx` (skeleton)**

```tsx
import React from "react";
import { BrowserRouter } from "react-router-dom";
import { AppRouter } from "./router";

export function App() {
  return (
    <BrowserRouter>
      <AppRouter />
    </BrowserRouter>
  );
}
```

- [ ] **Step 6.5: Verify dev server**

Run: `npm run dev`
Expected: serves on port 5173. Open `http://localhost:5173/` and any random path like `/foo`; both show "Shell OK" on the dark background. Stop the server.

- [ ] **Step 6.6: Verify type check**

Run: `npm run typecheck`
Expected: exit code 0.

- [ ] **Step 6.7: Commit**

```bash
git add src/frontend/main.tsx src/frontend/app/App.tsx src/frontend/app/router.tsx src/frontend/lib/cn.ts
git commit -m "feat(frontend): app shell skeleton"
```

---

## Task 7: `lib/env.ts` — zod-validated environment

**Files:**
- Create: `src/frontend/lib/env.ts`
- Create: `src/frontend/lib/env.test.ts`
- Create: `.env.example.frontend` (documentation; not auto-loaded)

- [ ] **Step 7.1: Write the failing test**

Create `src/frontend/lib/env.test.ts`:

```ts
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

describe("env", () => {
  const originalEnv = { ...import.meta.env };
  beforeEach(() => { vi.resetModules(); });
  afterEach(() => { Object.assign(import.meta.env, originalEnv); });

  it("parses required vars with defaults", async () => {
    import.meta.env.VITE_API_BASE_URL = "/api/v1";
    import.meta.env.VITE_APP_NAME = "StokAI";
    const { env } = await import("./env");
    expect(env.apiBaseUrl).toBe("/api/v1");
    expect(env.appName).toBe("StokAI");
    expect(env.enableDevtools).toBe(false); // default when unset
  });

  it("coerces VITE_ENABLE_DEVTOOLS=\"true\" to boolean true", async () => {
    import.meta.env.VITE_API_BASE_URL = "/api/v1";
    import.meta.env.VITE_APP_NAME = "StokAI";
    import.meta.env.VITE_ENABLE_DEVTOOLS = "true";
    const { env } = await import("./env");
    expect(env.enableDevtools).toBe(true);
  });

  it("throws a clear error when a required var is missing", async () => {
    import.meta.env.VITE_API_BASE_URL = "";
    import.meta.env.VITE_APP_NAME = "";
    await expect(import("./env")).rejects.toThrow(/VITE_API_BASE_URL/);
  });
});
```

- [ ] **Step 7.2: Run the test (should fail)**

Run: `npm test -- src/frontend/lib/env.test.ts`
Expected: failures — module `./env` does not exist.

- [ ] **Step 7.3: Implement `src/frontend/lib/env.ts`**

```ts
import { z } from "zod";

const EnvSchema = z.object({
  VITE_API_BASE_URL: z.string().min(1, "VITE_API_BASE_URL is required"),
  VITE_WS_BASE_URL: z.string().optional().default(""),
  VITE_APP_NAME: z.string().min(1, "VITE_APP_NAME is required"),
  VITE_SENTRY_DSN: z.string().optional().default(""),
  VITE_ENABLE_DEVTOOLS: z
    .string()
    .optional()
    .default("false")
    .transform((s) => s === "true"),
});

const parsed = EnvSchema.safeParse(import.meta.env);

if (!parsed.success) {
  const issues = parsed.error.issues
    .map((i) => `  - ${i.path.join(".")}: ${i.message}`)
    .join("\n");
  throw new Error(
    `Frontend env validation failed.\n${issues}\n\n` +
      `Set these in your .env file (see .env.example.frontend).`,
  );
}

export const env = {
  apiBaseUrl: parsed.data.VITE_API_BASE_URL,
  wsBaseUrl: parsed.data.VITE_WS_BASE_URL,
  appName: parsed.data.VITE_APP_NAME,
  sentryDsn: parsed.data.VITE_SENTRY_DSN,
  enableDevtools: parsed.data.VITE_ENABLE_DEVTOOLS,
} as const;

export type Env = typeof env;
```

- [ ] **Step 7.4: Create `.env.example.frontend`**

```
VITE_API_BASE_URL=/api/v1
VITE_WS_BASE_URL=
VITE_APP_NAME=StokAI
VITE_SENTRY_DSN=
VITE_ENABLE_DEVTOOLS=true
```

- [ ] **Step 7.5: Update local `.env` (manual)**

The user's existing `.env` is preserved. Add the five lines above to it if they are not present. Document this in the commit message.

- [ ] **Step 7.6: Run the test (should pass)**

Run: `npm test -- src/frontend/lib/env.test.ts`
Expected: 3 passed.

- [ ] **Step 7.7: Commit**

```bash
git add src/frontend/lib/env.ts src/frontend/lib/env.test.ts .env.example.frontend
git commit -m "feat(frontend): zod-validated env loader"
```

---

## Task 8: `lib/api/{types,errors,keys}.ts` — API foundation primitives

**Files:**
- Create: `src/frontend/lib/api/types.ts`
- Create: `src/frontend/lib/api/errors.ts`
- Create: `src/frontend/lib/api/keys.ts`
- Create: `src/frontend/lib/api/errors.test.ts`
- Create: `src/frontend/lib/api/keys.test.ts`

- [ ] **Step 8.1: Create `src/frontend/lib/api/types.ts`**

```ts
export interface ApiEnvelope<T> {
  data?: T;
  meta?: { request_id?: string; elapsed_ms?: number };
  error?: ApiErrorBody;
}

export interface ApiErrorBody {
  code: string;
  message: string;
  details?: Record<string, unknown>;
  request_id?: string;
}

export type ApiErrorCode =
  | `AUTH_${string}`
  | `VALIDATION_${string}`
  | `RATE_LIMIT_${string}`
  | `COST_LIMIT_${string}`
  | "NOT_FOUND"
  | "EXTERNAL_UNAVAILABLE"
  | "INTERNAL_ERROR"
  | "CONTRACT_MISMATCH"
  | "NETWORK_ERROR"
  | (string & {});
```

- [ ] **Step 8.2: Write failing errors test**

Create `src/frontend/lib/api/errors.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import {
  ApiError,
  isAuthError,
  isValidationError,
  isRateLimit,
  isCostLimit,
  isNotFound,
  isExternalUnavailable,
} from "./errors";

describe("ApiError", () => {
  it("carries status, code, message, details, requestId", () => {
    const err = new ApiError(401, "AUTH_INVALID_CREDENTIALS", "bad", { field: "password" }, "req-1");
    expect(err.status).toBe(401);
    expect(err.code).toBe("AUTH_INVALID_CREDENTIALS");
    expect(err.message).toBe("bad");
    expect(err.details).toEqual({ field: "password" });
    expect(err.requestId).toBe("req-1");
    expect(err).toBeInstanceOf(Error);
  });

  it.each([
    ["AUTH_INVALID_CREDENTIALS", isAuthError, true],
    ["VALIDATION_FORMAT", isValidationError, true],
    ["RATE_LIMIT_USER", isRateLimit, true],
    ["COST_LIMIT_DAILY", isCostLimit, true],
    ["NOT_FOUND", isNotFound, true],
    ["EXTERNAL_UNAVAILABLE", isExternalUnavailable, true],
    ["INTERNAL_ERROR", isAuthError, false],
  ])("predicate %s → %s = %s", (code, fn, expected) => {
    const err = new ApiError(500, code, "x");
    expect(fn(err)).toBe(expected);
  });
});
```

Run: `npm test -- src/frontend/lib/api/errors.test.ts`
Expected: fails — module does not exist.

- [ ] **Step 8.3: Implement `src/frontend/lib/api/errors.ts`**

```ts
import type { ApiErrorCode } from "./types";

export class ApiError extends Error {
  readonly status: number;
  readonly code: ApiErrorCode;
  readonly details?: Record<string, unknown>;
  readonly requestId?: string;

  constructor(
    status: number,
    code: ApiErrorCode,
    message: string,
    details?: Record<string, unknown>,
    requestId?: string,
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
    this.requestId = requestId;
  }
}

export const isAuthError = (e: unknown): e is ApiError =>
  e instanceof ApiError && e.code.startsWith("AUTH_");
export const isValidationError = (e: unknown): e is ApiError =>
  e instanceof ApiError && e.code.startsWith("VALIDATION_");
export const isRateLimit = (e: unknown): e is ApiError =>
  e instanceof ApiError && e.code.startsWith("RATE_LIMIT_");
export const isCostLimit = (e: unknown): e is ApiError =>
  e instanceof ApiError && e.code.startsWith("COST_LIMIT_");
export const isNotFound = (e: unknown): e is ApiError =>
  e instanceof ApiError && e.code === "NOT_FOUND";
export const isExternalUnavailable = (e: unknown): e is ApiError =>
  e instanceof ApiError && e.code === "EXTERNAL_UNAVAILABLE";
export const isTokenExpired = (e: unknown): e is ApiError =>
  e instanceof ApiError && e.code === "AUTH_TOKEN_EXPIRED";
```

Run: `npm test -- src/frontend/lib/api/errors.test.ts`
Expected: 8 passed.

- [ ] **Step 8.4: Write failing keys test**

Create `src/frontend/lib/api/keys.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import { qk } from "./keys";

describe("qk", () => {
  it("returns a tuple of [resource, ...ids]", () => {
    expect(qk("briefs", "abc")).toEqual(["briefs", "abc"]);
  });
  it("appends a params object when provided", () => {
    expect(qk("screener", { sector: "tech" })).toEqual(["screener", { sector: "tech" }]);
  });
  it("treats a single-string call as [resource]", () => {
    expect(qk("me")).toEqual(["me"]);
  });
});
```

Run: `npm test -- src/frontend/lib/api/keys.test.ts`
Expected: fails — `./keys` does not export `qk`.

- [ ] **Step 8.5: Implement `src/frontend/lib/api/keys.ts`**

```ts
type QkPart = string | number | Record<string, unknown>;

export function qk(resource: string, ...parts: QkPart[]): readonly unknown[] {
  return [resource, ...parts];
}
```

Run: `npm test -- src/frontend/lib/api/keys.test.ts`
Expected: 3 passed.

- [ ] **Step 8.6: Commit**

```bash
git add src/frontend/lib/api/
git commit -m "feat(frontend): API envelope types, ApiError + predicates, qk helper"
```

---

## Task 9: `lib/api/client.ts` — the typed fetch wrapper

**Files:**
- Create: `src/frontend/lib/api/client.ts`
- Create: `src/frontend/lib/api/client.test.ts`
- Create: `tests/frontend/msw/server.ts`
- Create: `tests/frontend/msw/handlers.ts`

This is the highest-stakes module. TDD it carefully.

- [ ] **Step 9.1: Create the MSW server scaffold**

`tests/frontend/msw/server.ts`:

```ts
import { setupServer } from "msw/node";
import { handlers } from "./handlers";

export const server = setupServer(...handlers);
```

`tests/frontend/msw/handlers.ts`:

```ts
import { http, HttpResponse } from "msw";

export const handlers = [
  http.get("/api/v1/ping", () =>
    HttpResponse.json({ data: { pong: true }, meta: { request_id: "r1" } }),
  ),
];
```

- [ ] **Step 9.2: Integrate MSW into `setupTests.ts`**

Append to `tests/frontend/setupTests.ts`:

```ts
import { beforeAll, afterAll } from "vitest";
import { server } from "./msw/server";

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterAll(() => server.close());
afterEach(() => server.resetHandlers());
```

Note: `afterEach` is already imported at the top of the file from Task 5.3; reuse the same import.

- [ ] **Step 9.3: Write failing test — successful GET unwraps the envelope**

Create `src/frontend/lib/api/client.test.ts`:

```ts
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "../../../../tests/frontend/msw/server";
import { api, setAccessToken, clearAccessToken } from "./client";
import { ApiError } from "./errors";

describe("api()", () => {
  beforeEach(() => clearAccessToken());
  afterEach(() => clearAccessToken());

  it("unwraps the envelope and returns data on 200", async () => {
    server.use(
      http.get("/api/v1/ping", () =>
        HttpResponse.json({ data: { pong: true } }),
      ),
    );
    const res = await api<{ pong: boolean }>("/ping");
    expect(res).toEqual({ pong: true });
  });

  it("attaches Authorization header when access token set", async () => {
    setAccessToken("tok_123");
    let received: string | null = null;
    server.use(
      http.get("/api/v1/secret", ({ request }) => {
        received = request.headers.get("authorization");
        return HttpResponse.json({ data: { ok: true } });
      }),
    );
    await api("/secret");
    expect(received).toBe("Bearer tok_123");
  });

  it("omits Authorization when skipAuth=true", async () => {
    setAccessToken("tok_123");
    let received: string | null = "PRESENT";
    server.use(
      http.get("/api/v1/public", ({ request }) => {
        received = request.headers.get("authorization");
        return HttpResponse.json({ data: { ok: true } });
      }),
    );
    await api("/public", { skipAuth: true });
    expect(received).toBeNull();
  });

  it("throws ApiError with status/code/message on 4xx", async () => {
    server.use(
      http.get("/api/v1/bad", () =>
        HttpResponse.json(
          { error: { code: "VALIDATION_FORMAT", message: "bad input", details: { field: "x" }, request_id: "r1" } },
          { status: 400 },
        ),
      ),
    );
    await expect(api("/bad")).rejects.toMatchObject({
      name: "ApiError",
      status: 400,
      code: "VALIDATION_FORMAT",
      message: "bad input",
      details: { field: "x" },
      requestId: "r1",
    });
  });

  it("retries exactly once after a silent refresh on 401, then succeeds", async () => {
    setAccessToken("expired");
    let calls = 0;
    server.use(
      http.get("/api/v1/me", ({ request }) => {
        calls += 1;
        const auth = request.headers.get("authorization");
        if (auth === "Bearer expired") {
          return HttpResponse.json(
            { error: { code: "AUTH_TOKEN_EXPIRED", message: "expired" } },
            { status: 401 },
          );
        }
        return HttpResponse.json({ data: { id: "u1" } });
      }),
      http.post("/api/v1/auth/refresh", () =>
        HttpResponse.json({ data: { access_token: "fresh", exp: Math.floor(Date.now() / 1000) + 3600 } }),
      ),
    );
    const res = await api<{ id: string }>("/me");
    expect(res).toEqual({ id: "u1" });
    expect(calls).toBe(2);
  });

  it("dedupes concurrent refresh requests", async () => {
    setAccessToken("expired");
    let refreshCalls = 0;
    server.use(
      http.get("/api/v1/me", ({ request }) => {
        const auth = request.headers.get("authorization");
        if (auth === "Bearer expired") {
          return HttpResponse.json(
            { error: { code: "AUTH_TOKEN_EXPIRED", message: "x" } },
            { status: 401 },
          );
        }
        return HttpResponse.json({ data: { id: "u1" } });
      }),
      http.post("/api/v1/auth/refresh", async () => {
        refreshCalls += 1;
        await new Promise((r) => setTimeout(r, 20));
        return HttpResponse.json({ data: { access_token: "fresh", exp: 9999 } });
      }),
    );
    await Promise.all([api("/me"), api("/me"), api("/me")]);
    expect(refreshCalls).toBe(1);
  });

  it("emits auth:expired and throws when refresh fails", async () => {
    setAccessToken("expired");
    server.use(
      http.get("/api/v1/me", () =>
        HttpResponse.json(
          { error: { code: "AUTH_TOKEN_EXPIRED", message: "x" } },
          { status: 401 },
        ),
      ),
      http.post("/api/v1/auth/refresh", () =>
        HttpResponse.json(
          { error: { code: "AUTH_REFRESH_FAILED", message: "no cookie" } },
          { status: 401 },
        ),
      ),
    );
    const handler = vi.fn();
    window.addEventListener("auth:expired", handler);
    await expect(api("/me")).rejects.toBeInstanceOf(ApiError);
    expect(handler).toHaveBeenCalledOnce();
    window.removeEventListener("auth:expired", handler);
  });

  it("throws NETWORK_ERROR for fetch failures", async () => {
    server.use(http.get("/api/v1/down", () => HttpResponse.error()));
    await expect(api("/down")).rejects.toMatchObject({ code: "NETWORK_ERROR" });
  });
});
```

Run: `npm test -- src/frontend/lib/api/client.test.ts`
Expected: every test fails — `./client` does not exist.

- [ ] **Step 9.4: Implement `src/frontend/lib/api/client.ts`**

```ts
import { env } from "../env";
import { ApiError } from "./errors";
import type { ApiEnvelope, ApiErrorBody } from "./types";

let accessToken: string | null = null;
let refreshInFlight: Promise<boolean> | null = null;

export function setAccessToken(token: string | null): void {
  accessToken = token;
}
export function getAccessToken(): string | null {
  return accessToken;
}
export function clearAccessToken(): void {
  accessToken = null;
}

interface ApiInit extends RequestInit {
  skipAuth?: boolean;
  /** Internal: prevents an infinite retry loop. */
  _retry?: boolean;
}

export async function api<T>(path: string, init: ApiInit = {}): Promise<T> {
  const url = env.apiBaseUrl.replace(/\/$/, "") + (path.startsWith("/") ? path : `/${path}`);

  const headers = new Headers(init.headers);
  if (!headers.has("content-type") && init.body && !(init.body instanceof FormData)) {
    headers.set("content-type", "application/json");
  }
  if (!init.skipAuth && accessToken) {
    headers.set("authorization", `Bearer ${accessToken}`);
  }
  headers.set("accept", "application/json");

  let response: Response;
  try {
    response = await fetch(url, { ...init, headers, credentials: "include" });
  } catch (err) {
    throw new ApiError(0, "NETWORK_ERROR", err instanceof Error ? err.message : "Network error");
  }

  if (response.status === 401 && !init._retry && !init.skipAuth) {
    const refreshed = await refreshAccessToken();
    if (refreshed) {
      return api<T>(path, { ...init, _retry: true });
    }
    window.dispatchEvent(new CustomEvent("auth:expired"));
  }

  let body: ApiEnvelope<T> | null = null;
  if (response.status !== 204) {
    try {
      body = (await response.json()) as ApiEnvelope<T>;
    } catch {
      body = null;
    }
  }

  if (!response.ok) {
    const errBody: ApiErrorBody = body?.error ?? {
      code: "INTERNAL_ERROR",
      message: `Request failed: ${response.status} ${response.statusText}`,
    };
    throw new ApiError(
      response.status,
      errBody.code,
      errBody.message,
      errBody.details,
      errBody.request_id,
    );
  }

  return (body?.data ?? (undefined as unknown)) as T;
}

async function refreshAccessToken(): Promise<boolean> {
  if (refreshInFlight) return refreshInFlight;
  refreshInFlight = (async () => {
    try {
      const url = env.apiBaseUrl.replace(/\/$/, "") + "/auth/refresh";
      const resp = await fetch(url, {
        method: "POST",
        credentials: "include",
        headers: { accept: "application/json" },
      });
      if (!resp.ok) return false;
      const body = (await resp.json()) as ApiEnvelope<{ access_token: string; exp: number }>;
      if (!body.data?.access_token) return false;
      accessToken = body.data.access_token;
      return true;
    } catch {
      return false;
    } finally {
      refreshInFlight = null;
    }
  })();
  return refreshInFlight;
}

export function __resetForTests() {
  accessToken = null;
  refreshInFlight = null;
}
```

Run: `npm test -- src/frontend/lib/api/client.test.ts`
Expected: 8 passed.

- [ ] **Step 9.5: Add the no-fetch lint exception (documentation only for now)**

Append a comment to `src/frontend/lib/api/client.ts` header so the lint rule (added later) recognises this file as the exception:

```ts
/* eslint-disable-next-line -- this is the only file allowed to call fetch against /api */
```

Place the comment immediately above the `fetch(url, ...)` and `fetch(url, { method: "POST"...})` calls. The actual lint rule is added in Task 35.

- [ ] **Step 9.6: Commit**

```bash
git add src/frontend/lib/api/client.ts src/frontend/lib/api/client.test.ts tests/frontend/msw/ tests/frontend/setupTests.ts
git commit -m "feat(frontend): typed API client with silent token refresh + in-flight dedup"
```

---

## Task 10: `lib/api/stream.ts` and `ws.ts` — SSE + WebSocket wrappers

**Files:**
- Create: `src/frontend/lib/api/stream.ts`
- Create: `src/frontend/lib/api/ws.ts`
- Create: `src/frontend/lib/api/stream.test.ts`
- Create: `src/frontend/lib/api/ws.test.ts`

- [ ] **Step 10.1: Write failing stream test**

`src/frontend/lib/api/stream.test.ts`:

```ts
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "../../../../tests/frontend/msw/server";
import { apiStream, type StreamEvent } from "./stream";
import { setAccessToken, clearAccessToken } from "./client";

describe("apiStream", () => {
  beforeEach(() => clearAccessToken());
  afterEach(() => clearAccessToken());

  it("parses sequential SSE events and calls onEvent for each", async () => {
    const sse = [
      "event: token",
      'data: {"text":"Hi"}',
      "",
      "event: token",
      'data: {"text":" there"}',
      "",
      "event: done",
      'data: {"message_id":"m1"}',
      "",
    ].join("\n");
    server.use(
      http.get("/api/v1/qa/stream", () =>
        new HttpResponse(sse, { headers: { "content-type": "text/event-stream" } }),
      ),
    );
    const events: StreamEvent[] = [];
    await new Promise<void>((resolve) => {
      apiStream("/qa/stream", {
        onEvent: (e) => {
          events.push(e);
          if (e.event === "done") resolve();
        },
        onError: () => resolve(),
      });
    });
    expect(events.map((e) => e.event)).toEqual(["token", "token", "done"]);
    expect(events[0].data).toEqual({ text: "Hi" });
  });

  it("attaches Authorization header when token set", async () => {
    setAccessToken("tok_x");
    let received: string | null = null;
    server.use(
      http.get("/api/v1/stream/check", ({ request }) => {
        received = request.headers.get("authorization");
        return new HttpResponse("", { headers: { "content-type": "text/event-stream" } });
      }),
    );
    const ctrl = apiStream("/stream/check", { onEvent: () => {}, onError: () => {} });
    await new Promise((r) => setTimeout(r, 50));
    ctrl.abort();
    expect(received).toBe("Bearer tok_x");
  });
});
```

Run: `npm test -- src/frontend/lib/api/stream.test.ts`
Expected: failures — module missing.

- [ ] **Step 10.2: Implement `src/frontend/lib/api/stream.ts`**

```ts
import { env } from "../env";
import { getAccessToken } from "./client";

export interface StreamEvent {
  event: string;
  data: unknown;
  id?: string;
}

export interface StreamHandlers {
  onEvent: (e: StreamEvent) => void;
  onError: (err: Error) => void;
}

export interface StreamHandle {
  abort: () => void;
}

export function apiStream(path: string, h: StreamHandlers): StreamHandle {
  const ctrl = new AbortController();
  const url = env.apiBaseUrl.replace(/\/$/, "") + (path.startsWith("/") ? path : `/${path}`);

  const headers: Record<string, string> = { accept: "text/event-stream" };
  const token = getAccessToken();
  if (token) headers.authorization = `Bearer ${token}`;

  (async () => {
    try {
      const resp = await fetch(url, { headers, credentials: "include", signal: ctrl.signal });
      if (!resp.ok || !resp.body) {
        h.onError(new Error(`SSE failed: ${resp.status}`));
        return;
      }
      const reader = resp.body.pipeThrough(new TextDecoderStream()).getReader();
      let buffer = "";
      // eslint-disable-next-line no-constant-condition
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += value;
        let idx: number;
        while ((idx = buffer.indexOf("\n\n")) !== -1) {
          const chunk = buffer.slice(0, idx);
          buffer = buffer.slice(idx + 2);
          const evt = parseSseChunk(chunk);
          if (evt) h.onEvent(evt);
        }
      }
    } catch (err) {
      if ((err as Error).name !== "AbortError") {
        h.onError(err as Error);
      }
    }
  })();

  return { abort: () => ctrl.abort() };
}

function parseSseChunk(chunk: string): StreamEvent | null {
  const lines = chunk.split("\n");
  let event = "message";
  let dataLines: string[] = [];
  let id: string | undefined;
  for (const line of lines) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
    else if (line.startsWith("id:")) id = line.slice(3).trim();
  }
  if (dataLines.length === 0) return null;
  const raw = dataLines.join("\n");
  let data: unknown;
  try { data = JSON.parse(raw); } catch { data = raw; }
  return { event, data, id };
}
```

Run: `npm test -- src/frontend/lib/api/stream.test.ts`
Expected: 2 passed.

- [ ] **Step 10.3: Write failing WS test**

`src/frontend/lib/api/ws.test.ts`:

```ts
import { describe, it, expect, vi, beforeEach } from "vitest";
import { apiSocket } from "./ws";
import { setAccessToken } from "./client";

class MockWebSocket {
  static instances: MockWebSocket[] = [];
  url: string;
  onopen: ((e: Event) => void) | null = null;
  onmessage: ((e: MessageEvent) => void) | null = null;
  onerror: ((e: Event) => void) | null = null;
  onclose: ((e: CloseEvent) => void) | null = null;
  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
  }
  close(_code?: number) { this.onclose?.(new CloseEvent("close", { code: _code ?? 1000 })); }
  send(_: string) {}
}

beforeEach(() => {
  MockWebSocket.instances = [];
  vi.stubGlobal("WebSocket", MockWebSocket as unknown as typeof WebSocket);
});

describe("apiSocket", () => {
  it("appends token query param when access token is set", () => {
    setAccessToken("tok_ws");
    apiSocket("/events/feed", { onMessage: () => {}, onClose: () => {} });
    expect(MockWebSocket.instances[0].url).toContain("token=tok_ws");
  });

  it("calls onMessage with parsed JSON frames", () => {
    const messages: unknown[] = [];
    apiSocket("/events/feed", {
      onMessage: (m) => messages.push(m),
      onClose: () => {},
    });
    const ws = MockWebSocket.instances[0];
    ws.onmessage?.(new MessageEvent("message", { data: JSON.stringify({ type: "ping" }) }));
    expect(messages).toEqual([{ type: "ping" }]);
  });
});
```

Run: `npm test -- src/frontend/lib/api/ws.test.ts`
Expected: failures — `./ws` missing.

- [ ] **Step 10.4: Implement `src/frontend/lib/api/ws.ts`**

```ts
import { env } from "../env";
import { getAccessToken } from "./client";

export interface SocketHandlers {
  onMessage: (msg: unknown) => void;
  onClose: (ev: CloseEvent) => void;
  onError?: (ev: Event) => void;
}

export interface SocketHandle {
  close: () => void;
}

export function apiSocket(path: string, h: SocketHandlers): SocketHandle {
  const base =
    env.wsBaseUrl ||
    (typeof window !== "undefined"
      ? `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}`
      : "");
  const token = getAccessToken();
  const separator = path.includes("?") ? "&" : "?";
  const url =
    base + (path.startsWith("/") ? path : `/${path}`) +
    (token ? `${separator}token=${encodeURIComponent(token)}` : "");

  const ws = new WebSocket(url);

  ws.onmessage = (event: MessageEvent) => {
    try {
      h.onMessage(JSON.parse(event.data as string));
    } catch {
      h.onMessage(event.data);
    }
  };
  ws.onclose = (event: CloseEvent) => h.onClose(event);
  if (h.onError) ws.onerror = (event: Event) => h.onError?.(event);

  return { close: () => ws.close() };
}
```

Run: `npm test -- src/frontend/lib/api/ws.test.ts`
Expected: 2 passed.

- [ ] **Step 10.5: Commit**

```bash
git add src/frontend/lib/api/stream.ts src/frontend/lib/api/ws.ts src/frontend/lib/api/stream.test.ts src/frontend/lib/api/ws.test.ts
git commit -m "feat(frontend): SSE + WebSocket wrappers with auth + reconnect-ready handles"
```

---

## Task 11: `useBreakpoint` hook (used by AppShell + features)

**Files:**
- Create: `src/frontend/hooks/useBreakpoint.ts`
- Create: `src/frontend/hooks/useBreakpoint.test.ts`

- [ ] **Step 11.1: Write failing test**

```ts
import { describe, it, expect, vi } from "vitest";
import { renderHook } from "@testing-library/react";
import { useBreakpoint, BREAKPOINTS } from "./useBreakpoint";

describe("useBreakpoint", () => {
  it("exports the canonical breakpoints", () => {
    expect(BREAKPOINTS).toEqual({ sm: 375, md: 768, lg: 1280, xl: 1440 });
  });

  it("returns the current bucket based on innerWidth", () => {
    Object.defineProperty(window, "innerWidth", { writable: true, configurable: true, value: 900 });
    const { result } = renderHook(() => useBreakpoint());
    expect(result.current).toBe("md");
  });
});
```

Run: `npm test -- src/frontend/hooks/useBreakpoint.test.ts`
Expected: failures.

- [ ] **Step 11.2: Implement**

```ts
import { useEffect, useState } from "react";

export const BREAKPOINTS = { sm: 375, md: 768, lg: 1280, xl: 1440 } as const;
export type Breakpoint = keyof typeof BREAKPOINTS;

export function useBreakpoint(): Breakpoint {
  const [bp, setBp] = useState<Breakpoint>(() => compute(window.innerWidth));
  useEffect(() => {
    const onResize = () => setBp(compute(window.innerWidth));
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);
  return bp;
}

function compute(w: number): Breakpoint {
  if (w >= BREAKPOINTS.xl) return "xl";
  if (w >= BREAKPOINTS.lg) return "lg";
  if (w >= BREAKPOINTS.md) return "md";
  return "sm";
}
```

Run: `npm test -- src/frontend/hooks/useBreakpoint.test.ts`
Expected: 2 passed.

- [ ] **Step 11.3: Commit**

```bash
git add src/frontend/hooks/useBreakpoint.ts src/frontend/hooks/useBreakpoint.test.ts
git commit -m "feat(frontend): useBreakpoint hook with canonical breakpoints"
```

---

## Task 12: ThemeProvider + QueryProvider + ErrorBoundary

**Files:**
- Create: `src/frontend/app/providers/ThemeProvider.tsx`
- Create: `src/frontend/app/providers/QueryProvider.tsx`
- Create: `src/frontend/app/providers/ErrorBoundary.tsx`

- [ ] **Step 12.1: Implement `ThemeProvider.tsx`**

```tsx
import React from "react";
import { ThemeProvider as NextThemeProvider } from "next-themes";

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  return (
    <NextThemeProvider
      attribute="data-theme"
      defaultTheme="dark"
      enableSystem
      disableTransitionOnChange
      themes={["dark", "light"]}
      storageKey="stokai-theme"
    >
      {children}
    </NextThemeProvider>
  );
}
```

- [ ] **Step 12.2: Implement `QueryProvider.tsx`**

```tsx
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ReactQueryDevtools } from "@tanstack/react-query-devtools";
import { ApiError } from "../../lib/api/errors";
import { env } from "../../lib/env";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      refetchOnWindowFocus: false,
      retry: (count, err) => err instanceof ApiError && err.status >= 500 && count < 2,
    },
    mutations: { retry: 0 },
  },
});

export function QueryProvider({ children }: { children: React.ReactNode }) {
  return (
    <QueryClientProvider client={queryClient}>
      {children}
      {env.enableDevtools && <ReactQueryDevtools initialIsOpen={false} />}
    </QueryClientProvider>
  );
}
```

- [ ] **Step 12.3: Implement `ErrorBoundary.tsx`**

```tsx
import React from "react";

interface State {
  error: Error | null;
}

export class ErrorBoundary extends React.Component<{ children: React.ReactNode }, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error("[ErrorBoundary]", error, info);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="flex min-h-screen items-center justify-center bg-surface-0 p-6 text-text">
          <div className="max-w-md rounded-lg border border-border bg-surface-1 p-6 shadow-md">
            <h1 className="text-xl font-semibold">Something went wrong</h1>
            <p className="mt-2 text-sm text-muted">
              The application hit an unexpected error. Try reloading the page.
            </p>
            <pre className="mt-3 overflow-auto rounded bg-surface-0 p-2 text-xs text-muted">
              {this.state.error.message}
            </pre>
            <button
              className="mt-4 rounded bg-signal px-3 py-1.5 text-sm font-medium text-signal-fg focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--ring)]"
              onClick={() => window.location.reload()}
            >
              Reload
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
```

- [ ] **Step 12.4: Commit**

```bash
git add src/frontend/app/providers/
git commit -m "feat(frontend): Theme, Query, ErrorBoundary providers"
```

---

## Task 13: AuthProvider (TDD) + `useAuth` + `useCurrentUser`

**Files:**
- Create: `src/frontend/app/providers/AuthProvider.tsx`
- Create: `src/frontend/app/providers/AuthProvider.test.tsx`
- Create: `src/frontend/features/auth/authApi.ts`

- [ ] **Step 13.1: Implement the auth API surface**

`src/frontend/features/auth/authApi.ts`:

```ts
import { z } from "zod";
import { api } from "../../lib/api/client";

const CurrentUserSchema = z.object({
  id: z.string(),
  email: z.string(),
  username: z.string(),
  role: z.enum(["user", "admin"]),
  tenantId: z.string(),
  onboardingComplete: z.boolean(),
  features: z.array(z.string()),
});
export type CurrentUser = z.infer<typeof CurrentUserSchema>;

const TokenSchema = z.object({
  access_token: z.string(),
  exp: z.number(),
});

export async function postLogin(email: string, password: string) {
  const raw = await api<unknown>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
    skipAuth: true,
  });
  return TokenSchema.parse(raw);
}

export async function postRegister(payload: { email: string; username: string; password: string }) {
  const raw = await api<unknown>("/auth/register", {
    method: "POST",
    body: JSON.stringify(payload),
    skipAuth: true,
  });
  return TokenSchema.parse(raw);
}

export async function postLogout(): Promise<void> {
  await api("/auth/logout", { method: "POST" });
}

export async function fetchMe(): Promise<CurrentUser> {
  const raw = await api<unknown>("/me");
  return CurrentUserSchema.parse(raw);
}

export async function postRefresh() {
  const raw = await api<unknown>("/auth/refresh", { method: "POST", skipAuth: true });
  return TokenSchema.parse(raw);
}
```

- [ ] **Step 13.2: Write failing AuthProvider test**

`src/frontend/app/providers/AuthProvider.test.tsx`:

```tsx
import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { http, HttpResponse } from "msw";
import { render, screen, act } from "@testing-library/react";
import { server } from "../../../../tests/frontend/msw/server";
import { AuthProvider, useAuth } from "./AuthProvider";
import { QueryProvider } from "./QueryProvider";

function Harness() {
  const { state, login, logout } = useAuth();
  return (
    <div>
      <div data-testid="status">{state.status}</div>
      <div data-testid="email">{state.status === "authenticated" ? state.user.email : ""}</div>
      <button onClick={() => login("a@b.com", "pw")}>login</button>
      <button onClick={() => logout()}>logout</button>
    </div>
  );
}

function wrap() {
  return render(
    <QueryProvider>
      <AuthProvider>
        <Harness />
      </AuthProvider>
    </QueryProvider>,
  );
}

describe("AuthProvider", () => {
  beforeEach(() => {
    server.use(
      http.post("/api/v1/auth/refresh", () =>
        HttpResponse.json({ error: { code: "AUTH_REFRESH_FAILED", message: "no cookie" } }, { status: 401 }),
      ),
    );
  });

  it("starts in loading and resolves to anonymous when refresh fails on mount", async () => {
    wrap();
    expect(screen.getByTestId("status").textContent).toBe("loading");
    await screen.findByText("anonymous");
  });

  it("logs in, fetches /me, becomes authenticated", async () => {
    server.use(
      http.post("/api/v1/auth/login", () =>
        HttpResponse.json({ data: { access_token: "tok", exp: Math.floor(Date.now() / 1000) + 3600 } }),
      ),
      http.get("/api/v1/me", () =>
        HttpResponse.json({
          data: {
            id: "u1", email: "a@b.com", username: "a", role: "user",
            tenantId: "t1", onboardingComplete: true, features: [],
          },
        }),
      ),
    );
    wrap();
    await screen.findByText("anonymous");
    await act(async () => { screen.getByText("login").click(); });
    await screen.findByText("authenticated");
    expect(screen.getByTestId("email").textContent).toBe("a@b.com");
  });
});
```

Run: `npm test -- src/frontend/app/providers/AuthProvider.test.tsx`
Expected: failures — provider missing.

- [ ] **Step 13.3: Implement `AuthProvider.tsx`**

```tsx
import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { setAccessToken, clearAccessToken } from "../../lib/api/client";
import { fetchMe, postLogin, postLogout, postRefresh, postRegister, type CurrentUser } from "../../features/auth/authApi";

export type AuthState =
  | { status: "loading" }
  | { status: "authenticated"; user: CurrentUser }
  | { status: "anonymous" };

interface AuthContextValue {
  state: AuthState;
  login: (email: string, password: string) => Promise<void>;
  register: (payload: { email: string; username: string; password: string }) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<AuthState>({ status: "loading" });
  const refreshTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const scheduleRefresh = useCallback((expSeconds: number) => {
    if (refreshTimer.current) clearTimeout(refreshTimer.current);
    const ms = Math.max((expSeconds - 60) * 1000 - Date.now(), 5_000);
    refreshTimer.current = setTimeout(async () => {
      try {
        const tok = await postRefresh();
        setAccessToken(tok.access_token);
        scheduleRefresh(tok.exp);
      } catch {
        await doLogout();
      }
    }, ms);
  }, []);

  const completeLogin = useCallback(
    async (accessToken: string, exp: number) => {
      setAccessToken(accessToken);
      scheduleRefresh(exp);
      const user = await fetchMe();
      setState({ status: "authenticated", user });
    },
    [scheduleRefresh],
  );

  const doLogout = useCallback(async () => {
    if (refreshTimer.current) clearTimeout(refreshTimer.current);
    clearAccessToken();
    try { await postLogout(); } catch { /* ignore */ }
    setState({ status: "anonymous" });
  }, []);

  // Mount: try refresh
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const tok = await postRefresh();
        if (cancelled) return;
        await completeLogin(tok.access_token, tok.exp);
      } catch {
        if (!cancelled) setState({ status: "anonymous" });
      }
    })();
    return () => { cancelled = true; };
  }, [completeLogin]);

  // Listen for forced logout from API client
  useEffect(() => {
    const handler = () => { void doLogout(); };
    window.addEventListener("auth:expired", handler);
    return () => window.removeEventListener("auth:expired", handler);
  }, [doLogout]);

  const value: AuthContextValue = useMemo(
    () => ({
      state,
      login: async (email, password) => {
        const tok = await postLogin(email, password);
        await completeLogin(tok.access_token, tok.exp);
      },
      register: async (payload) => {
        const tok = await postRegister(payload);
        await completeLogin(tok.access_token, tok.exp);
      },
      logout: doLogout,
    }),
    [state, completeLogin, doLogout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const v = useContext(AuthContext);
  if (!v) throw new Error("useAuth must be used inside AuthProvider");
  return v;
}

export function useCurrentUser(): CurrentUser {
  const { state } = useAuth();
  if (state.status !== "authenticated") {
    throw new Error("useCurrentUser called outside an authenticated context");
  }
  return state.user;
}
```

Run: `npm test -- src/frontend/app/providers/AuthProvider.test.tsx`
Expected: 2 passed.

- [ ] **Step 13.4: Commit**

```bash
git add src/frontend/app/providers/AuthProvider.tsx src/frontend/app/providers/AuthProvider.test.tsx src/frontend/features/auth/authApi.ts
git commit -m "feat(frontend): AuthProvider with silent refresh + useCurrentUser"
```

---

## Task 14: Route guards — `RequireAuth`, `RequireAdmin`, `OnboardingGate`

**Files:**
- Create: `src/frontend/app/guards/RequireAuth.tsx`
- Create: `src/frontend/app/guards/RequireAdmin.tsx`
- Create: `src/frontend/app/guards/OnboardingGate.tsx`
- Create: `src/frontend/app/guards/guards.test.tsx`
- Create: `src/frontend/app/routes.ts`

- [ ] **Step 14.1: Create routes constants first**

`src/frontend/app/routes.ts`:

```ts
export const ROUTES = {
  login: "/login",
  register: "/register",
  home: "/",
  onboarding: "/onboarding",
  briefs: "/briefs",
  brief: "/briefs/:briefId",
  screener: "/screener",
  company: "/companies/:ticker",
  portfolio: "/portfolio",
  watchlist: "/watchlist",
  alerts: "/alerts",
  qa: "/qa",
  events: "/events/:eventId/deep-dive",
  adminHil: "/admin/hil",
  adminSources: "/admin/sources",
  adminSystem: "/admin/system",
  adminAudit: "/admin/ai-audit",
} as const;
```

- [ ] **Step 14.2: Write failing guard tests**

`src/frontend/app/guards/guards.test.tsx`:

```tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { RequireAuth } from "./RequireAuth";
import { RequireAdmin } from "./RequireAdmin";
import { OnboardingGate } from "./OnboardingGate";
import * as AuthMod from "../providers/AuthProvider";

const useAuthSpy = vi.spyOn(AuthMod, "useAuth");

function setAuth(state: AuthMod.AuthState) {
  useAuthSpy.mockReturnValue({
    state,
    login: vi.fn(), register: vi.fn(), logout: vi.fn(),
  });
}

describe("guards", () => {
  it("RequireAuth shows skeleton while loading", () => {
    setAuth({ status: "loading" });
    render(
      <MemoryRouter><RequireAuth><div>protected</div></RequireAuth></MemoryRouter>,
    );
    expect(screen.getByTestId("auth-loading")).toBeInTheDocument();
  });

  it("RequireAuth redirects anonymous to /login", () => {
    setAuth({ status: "anonymous" });
    render(
      <MemoryRouter initialEntries={["/secret"]}>
        <Routes>
          <Route path="/login" element={<div>login page</div>} />
          <Route path="/secret" element={<RequireAuth><div>secret</div></RequireAuth>} />
        </Routes>
      </MemoryRouter>,
    );
    expect(screen.getByText("login page")).toBeInTheDocument();
  });

  it("RequireAdmin denies non-admin", () => {
    setAuth({
      status: "authenticated",
      user: { id: "u", email: "e", username: "u", role: "user", tenantId: "t", onboardingComplete: true, features: [] },
    });
    render(
      <MemoryRouter><RequireAdmin><div>admin only</div></RequireAdmin></MemoryRouter>,
    );
    expect(screen.getByTestId("access-denied")).toBeInTheDocument();
  });

  it("OnboardingGate redirects when onboarding incomplete", () => {
    setAuth({
      status: "authenticated",
      user: { id: "u", email: "e", username: "u", role: "user", tenantId: "t", onboardingComplete: false, features: [] },
    });
    render(
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route path="/onboarding" element={<div>onboarding</div>} />
          <Route element={<OnboardingGate />}>
            <Route path="/" element={<div>home</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );
    expect(screen.getByText("onboarding")).toBeInTheDocument();
  });
});
```

Run: `npm test -- src/frontend/app/guards/guards.test.tsx`
Expected: failures.

- [ ] **Step 14.3: Implement `RequireAuth.tsx`**

```tsx
import React from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../providers/AuthProvider";
import { ROUTES } from "../routes";

export function RequireAuth({ children }: { children: React.ReactNode }) {
  const { state } = useAuth();
  const location = useLocation();
  if (state.status === "loading") {
    return <div data-testid="auth-loading" className="flex min-h-screen items-center justify-center text-muted">Loading…</div>;
  }
  if (state.status === "anonymous") {
    return <Navigate to={ROUTES.login} replace state={{ from: location }} />;
  }
  return <>{children}</>;
}
```

- [ ] **Step 14.4: Implement `RequireAdmin.tsx`**

```tsx
import React from "react";
import { useAuth } from "../providers/AuthProvider";

export function RequireAdmin({ children }: { children: React.ReactNode }) {
  const { state } = useAuth();
  if (state.status !== "authenticated" || state.user.role !== "admin") {
    return (
      <div data-testid="access-denied" className="flex min-h-[60vh] items-center justify-center p-6">
        <div className="max-w-md rounded-lg border border-border bg-surface-1 p-6 text-center">
          <h2 className="text-lg font-semibold">Access denied</h2>
          <p className="mt-2 text-sm text-muted">You need administrator permissions to view this page.</p>
        </div>
      </div>
    );
  }
  return <>{children}</>;
}
```

- [ ] **Step 14.5: Implement `OnboardingGate.tsx`**

```tsx
import React from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../providers/AuthProvider";
import { ROUTES } from "../routes";

export function OnboardingGate() {
  const { state } = useAuth();
  const location = useLocation();
  if (state.status !== "authenticated") return <Outlet />;
  if (!state.user.onboardingComplete && location.pathname !== ROUTES.onboarding) {
    return <Navigate to={ROUTES.onboarding} replace />;
  }
  return <Outlet />;
}
```

Run: `npm test -- src/frontend/app/guards/guards.test.tsx`
Expected: 4 passed.

- [ ] **Step 14.6: Commit**

```bash
git add src/frontend/app/guards/ src/frontend/app/routes.ts
git commit -m "feat(frontend): route guards (RequireAuth, RequireAdmin, OnboardingGate) + ROUTES constants"
```

---

## Task 15: Install shadcn primitives + `ui/index.ts` barrel

**Files:**
- Create: `src/frontend/ui/*` (multiple primitive components)
- Create: `src/frontend/ui/index.ts`
- Create: `components.json` (shadcn config; at repo root)

- [ ] **Step 15.1: Create `components.json` for shadcn CLI**

```json
{
  "$schema": "https://ui.shadcn.com/schema.json",
  "style": "default",
  "rsc": false,
  "tsx": true,
  "tailwind": {
    "config": "",
    "css": "src/frontend/styles/globals.css",
    "baseColor": "neutral",
    "cssVariables": true,
    "prefix": ""
  },
  "aliases": {
    "components": "@/ui",
    "utils": "@/lib/cn",
    "ui": "@/ui",
    "lib": "@/lib",
    "hooks": "@/hooks"
  }
}
```

- [ ] **Step 15.2: Generate primitives**

Run from repo root, one at a time, in this order:

```bash
npx shadcn@latest add button input label textarea select checkbox switch card badge separator tabs dialog sheet dropdown-menu popover tooltip scroll-area skeleton alert avatar
npx shadcn@latest add command radio-group
```

After each command:
- Inspect any new file under `src/frontend/ui/`. Confirm imports point to `@/lib/cn`.
- If a primitive references CSS variables like `bg-background`, replace those with our token-aware classes (`bg-surface-1`, `text-text`, `border-border`) so the primitive uses the token system. The shadcn-default `bg-background text-foreground` map to `surface-0` and `text-primary` respectively in our scheme — apply that substitution consistently:
  - `bg-background` → `bg-surface-0`
  - `bg-card` → `bg-surface-1`
  - `bg-popover` → `bg-surface-2`
  - `bg-muted` → `bg-surface-2`
  - `text-foreground` → `text-text`
  - `text-card-foreground` → `text-text`
  - `text-muted-foreground` → `text-muted`
  - `border-input` → `border-border`
  - `border-border` → `border-border` (no change)
  - `ring-ring` → `ring-[var(--ring)]`
  - `bg-primary` → `bg-signal`
  - `text-primary-foreground` → `text-signal-fg`
  - `bg-destructive` → `bg-negative`
  - `text-destructive-foreground` → `text-text`

Apply substitutions with a single sed/PowerShell pass over `src/frontend/ui/*.tsx` after generation, or by hand if cleaner.

- [ ] **Step 15.3: Sonner installation**

```bash
npx shadcn@latest add sonner
```

(This places the `Toaster` wrapper at `src/frontend/ui/sonner.tsx`.)

- [ ] **Step 15.4: Create the UI barrel `src/frontend/ui/index.ts`**

```ts
export * from "./button";
export * from "./input";
export * from "./label";
export * from "./textarea";
export * from "./select";
export * from "./checkbox";
export * from "./radio-group";
export * from "./switch";
export * from "./card";
export * from "./badge";
export * from "./separator";
export * from "./tabs";
export * from "./dialog";
export * from "./sheet";
export * from "./dropdown-menu";
export * from "./popover";
export * from "./tooltip";
export * from "./scroll-area";
export * from "./skeleton";
export * from "./alert";
export * from "./avatar";
export * from "./command";
export * from "./sonner";
```

- [ ] **Step 15.5: Smoke-test build**

Run: `npm run typecheck`
Expected: exit 0.

- [ ] **Step 15.6: Commit**

```bash
git add components.json src/frontend/ui/
git commit -m "feat(frontend): install shadcn primitives + token-aware re-mapping"
```

---

## Task 16: LoginPage + RegisterPage (with auth forms)

**Files:**
- Create: `src/frontend/features/auth/authSchemas.ts`
- Create: `src/frontend/features/auth/LoginPage.tsx`
- Create: `src/frontend/features/auth/RegisterPage.tsx`
- Create: `src/frontend/features/auth/LoginPage.test.tsx`

- [ ] **Step 16.1: Create `authSchemas.ts`**

```ts
import { z } from "zod";

export const LoginSchema = z.object({
  email: z.string().email("Enter a valid email"),
  password: z.string().min(1, "Password is required"),
});
export type LoginInput = z.infer<typeof LoginSchema>;

export const RegisterSchema = z.object({
  email: z.string().email("Enter a valid email"),
  username: z.string().min(2, "Username must be at least 2 characters").max(32),
  password: z
    .string()
    .min(8, "At least 8 characters")
    .regex(/[A-Z]/, "Must include an uppercase letter")
    .regex(/[0-9]/, "Must include a number"),
});
export type RegisterInput = z.infer<typeof RegisterSchema>;
```

- [ ] **Step 16.2: Implement `LoginPage.tsx`**

```tsx
import React from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useLocation, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Button, Card, CardContent, CardHeader, Input, Label, Alert } from "@/ui";
import { useAuth } from "@/app/providers/AuthProvider";
import { ROUTES } from "@/app/routes";
import { LoginSchema, type LoginInput } from "./authSchemas";
import { ApiError, isAuthError } from "@/lib/api/errors";

export function LoginPage() {
  const { login } = useAuth();
  const nav = useNavigate();
  const loc = useLocation();
  const from = (loc.state as { from?: { pathname: string } } | null)?.from?.pathname ?? ROUTES.home;

  const {
    register, handleSubmit, formState: { errors, isSubmitting }, setError,
  } = useForm<LoginInput>({ resolver: zodResolver(LoginSchema) });

  const onSubmit = async (values: LoginInput) => {
    try {
      await login(values.email, values.password);
      nav(from, { replace: true });
    } catch (err) {
      if (err instanceof ApiError && isAuthError(err)) {
        setError("password", { message: err.message });
      } else {
        toast.error(err instanceof Error ? err.message : "Sign in failed");
      }
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-surface-0 p-4">
      <Card className="w-full max-w-sm border-border bg-surface-1">
        <CardHeader>
          <div className="text-2xl font-semibold tracking-tight">StokAI</div>
          <div className="text-sm text-muted">Sign in to continue</div>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
            <div className="space-y-1">
              <Label htmlFor="email">Email</Label>
              <Input id="email" type="email" autoComplete="email" autoFocus {...register("email")} aria-invalid={!!errors.email} />
              {errors.email && <p className="text-xs text-negative">{errors.email.message}</p>}
            </div>
            <div className="space-y-1">
              <Label htmlFor="password">Password</Label>
              <Input id="password" type="password" autoComplete="current-password" {...register("password")} aria-invalid={!!errors.password} />
              {errors.password && <p className="text-xs text-negative">{errors.password.message}</p>}
            </div>
            <Button type="submit" className="w-full" disabled={isSubmitting}>
              {isSubmitting ? "Signing in…" : "Sign in"}
            </Button>
            <div className="flex items-center justify-between text-xs text-muted">
              <button
                type="button"
                className="hover:text-text"
                onClick={() => toast.info("Password reset is coming soon.")}
              >
                Forgot password?
              </button>
              <a href={ROUTES.register} className="hover:text-text">Create account</a>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
```

- [ ] **Step 16.3: Implement `RegisterPage.tsx`**

```tsx
import React from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Button, Card, CardContent, CardHeader, Input, Label } from "@/ui";
import { useAuth } from "@/app/providers/AuthProvider";
import { ROUTES } from "@/app/routes";
import { RegisterSchema, type RegisterInput } from "./authSchemas";
import { ApiError, isValidationError } from "@/lib/api/errors";

export function RegisterPage() {
  const { register: doRegister } = useAuth();
  const nav = useNavigate();
  const {
    register, handleSubmit, formState: { errors, isSubmitting }, setError, watch,
  } = useForm<RegisterInput>({ resolver: zodResolver(RegisterSchema) });
  const password = watch("password") ?? "";
  const strength = scoreStrength(password);

  const onSubmit = async (values: RegisterInput) => {
    try {
      await doRegister(values);
      nav(ROUTES.onboarding, { replace: true });
    } catch (err) {
      if (err instanceof ApiError && isValidationError(err) && err.details?.field) {
        const field = String(err.details.field) as keyof RegisterInput;
        setError(field, { message: err.message });
      } else {
        toast.error(err instanceof Error ? err.message : "Registration failed");
      }
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-surface-0 p-4">
      <Card className="w-full max-w-sm border-border bg-surface-1">
        <CardHeader>
          <div className="text-2xl font-semibold tracking-tight">Create your account</div>
          <div className="text-sm text-muted">Join StokAI to access intelligence briefs.</div>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
            <Field label="Email" id="email" type="email" autoComplete="email" autoFocus
                   register={register("email")} error={errors.email?.message} />
            <Field label="Username" id="username" type="text" autoComplete="username"
                   register={register("username")} error={errors.username?.message} />
            <Field label="Password" id="password" type="password" autoComplete="new-password"
                   register={register("password")} error={errors.password?.message} />
            <PasswordStrength score={strength} />
            <Button type="submit" className="w-full" disabled={isSubmitting}>
              {isSubmitting ? "Creating…" : "Create account"}
            </Button>
            <div className="text-center text-xs text-muted">
              Already have an account? <a href={ROUTES.login} className="hover:text-text">Sign in</a>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}

function Field({
  label, id, type, autoComplete, autoFocus, register, error,
}: { label: string; id: string; type: string; autoComplete: string; autoFocus?: boolean; register: ReturnType<ReturnType<typeof useForm>["register"]>; error?: string }) {
  return (
    <div className="space-y-1">
      <Label htmlFor={id}>{label}</Label>
      <Input id={id} type={type} autoComplete={autoComplete} autoFocus={autoFocus} {...register} aria-invalid={!!error} />
      {error && <p className="text-xs text-negative">{error}</p>}
    </div>
  );
}

function scoreStrength(p: string): 0 | 1 | 2 | 3 | 4 {
  let s = 0;
  if (p.length >= 8) s += 1;
  if (/[A-Z]/.test(p)) s += 1;
  if (/[0-9]/.test(p)) s += 1;
  if (/[^A-Za-z0-9]/.test(p)) s += 1;
  return Math.min(s, 4) as 0 | 1 | 2 | 3 | 4;
}

function PasswordStrength({ score }: { score: 0 | 1 | 2 | 3 | 4 }) {
  const colors = ["bg-surface-3", "bg-negative", "bg-warning", "bg-warning", "bg-positive"];
  const label = ["Too short", "Weak", "OK", "Good", "Strong"][score];
  return (
    <div className="space-y-1">
      <div className="flex gap-1">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className={`h-1 flex-1 rounded ${i < score ? colors[score] : "bg-surface-3"}`} />
        ))}
      </div>
      <div className="text-xs text-muted">{label}</div>
    </div>
  );
}
```

- [ ] **Step 16.4: Write LoginPage test (smoke + happy path)**

`src/frontend/features/auth/LoginPage.test.tsx`:

```tsx
import { describe, it, expect, beforeEach } from "vitest";
import { http, HttpResponse } from "msw";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { server } from "../../../../tests/frontend/msw/server";
import { QueryProvider } from "@/app/providers/QueryProvider";
import { AuthProvider } from "@/app/providers/AuthProvider";
import { LoginPage } from "./LoginPage";

function setup() {
  return render(
    <MemoryRouter initialEntries={["/login"]}>
      <QueryProvider>
        <AuthProvider>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/" element={<div>home</div>} />
          </Routes>
        </AuthProvider>
      </QueryProvider>
    </MemoryRouter>,
  );
}

describe("LoginPage", () => {
  beforeEach(() => {
    server.use(
      http.post("/api/v1/auth/refresh", () =>
        HttpResponse.json({ error: { code: "AUTH_REFRESH_FAILED", message: "no" } }, { status: 401 }),
      ),
    );
  });

  it("renders the form", async () => {
    setup();
    expect(await screen.findByLabelText(/email/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
  });

  it("logs in and navigates home", async () => {
    server.use(
      http.post("/api/v1/auth/login", () =>
        HttpResponse.json({ data: { access_token: "tok", exp: Math.floor(Date.now() / 1000) + 3600 } }),
      ),
      http.get("/api/v1/me", () =>
        HttpResponse.json({
          data: { id: "u", email: "a@b.com", username: "a", role: "user", tenantId: "t", onboardingComplete: true, features: [] },
        }),
      ),
    );
    setup();
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText(/email/i), "a@b.com");
    await user.type(screen.getByLabelText(/password/i), "secret");
    await user.click(screen.getByRole("button", { name: /sign in/i }));
    await screen.findByText("home");
  });
});
```

Run: `npm test -- src/frontend/features/auth/`
Expected: 2 passed.

- [ ] **Step 16.5: Commit**

```bash
git add src/frontend/features/auth/
git commit -m "feat(frontend): LoginPage + RegisterPage with zod schemas"
```

---

## Task 17: TopNav + MobileNav + Sidebar (with theme toggle + user menu)

**Files:**
- Create: `src/frontend/layout/TopNav.tsx`
- Create: `src/frontend/layout/MobileNav.tsx`
- Create: `src/frontend/layout/Sidebar.tsx`
- Create: `src/frontend/layout/ThemeToggle.tsx`

- [ ] **Step 17.1: Implement `ThemeToggle.tsx`**

```tsx
import React from "react";
import { useTheme } from "next-themes";
import { Moon, Sun } from "lucide-react";
import { Button } from "@/ui";

export function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme();
  const isDark = resolvedTheme === "dark";
  return (
    <Button
      variant="ghost"
      size="icon"
      aria-label={isDark ? "Switch to light theme" : "Switch to dark theme"}
      onClick={() => setTheme(isDark ? "light" : "dark")}
    >
      {isDark ? <Sun className="h-[18px] w-[18px]" /> : <Moon className="h-[18px] w-[18px]" />}
    </Button>
  );
}
```

- [ ] **Step 17.2: Implement `TopNav.tsx`**

```tsx
import React from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { LogOut, Search, User as UserIcon } from "lucide-react";
import { Button, DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger, Avatar, AvatarFallback } from "@/ui";
import { useAuth } from "@/app/providers/AuthProvider";
import { ROUTES } from "@/app/routes";
import { ThemeToggle } from "./ThemeToggle";

const PRIMARY_NAV: ReadonlyArray<{ to: string; label: string }> = [
  { to: ROUTES.home, label: "Map" },
  { to: ROUTES.briefs, label: "Briefs" },
  { to: ROUTES.screener, label: "Screener" },
  { to: ROUTES.portfolio, label: "Portfolio" },
  { to: ROUTES.alerts, label: "Alerts" },
  { to: ROUTES.qa, label: "Q&A" },
];

export function TopNav({ onOpenCommand }: { onOpenCommand: () => void }) {
  const { state, logout } = useAuth();
  const nav = useNavigate();
  const user = state.status === "authenticated" ? state.user : null;
  const initials = user?.username?.[0]?.toUpperCase() ?? "?";

  return (
    <header className="sticky top-0 z-30 flex h-12 items-center gap-4 border-b border-border bg-surface-1 px-6">
      <NavLink to={ROUTES.home} className="text-sm font-semibold tracking-tight">
        StokAI
      </NavLink>
      <nav aria-label="Primary" className="hidden md:flex items-center gap-1">
        {PRIMARY_NAV.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              `rounded px-2 py-1 text-sm ${isActive ? "bg-surface-2 text-text" : "text-muted hover:text-text"}`
            }
          >
            {item.label}
          </NavLink>
        ))}
      </nav>
      <div className="ml-auto flex items-center gap-2">
        <Button variant="ghost" size="sm" onClick={onOpenCommand} aria-label="Open command palette" className="gap-2">
          <Search className="h-4 w-4" /><span className="hidden sm:inline text-xs">⌘K</span>
        </Button>
        <ThemeToggle />
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon" aria-label="User menu">
              <Avatar className="h-7 w-7"><AvatarFallback>{initials}</AvatarFallback></Avatar>
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="min-w-[180px]">
            <DropdownMenuItem className="text-xs text-muted">{user?.email ?? "Guest"}</DropdownMenuItem>
            <DropdownMenuSeparator />
            {user?.role === "admin" && (
              <DropdownMenuItem onClick={() => nav(ROUTES.adminHil)}>
                <UserIcon className="mr-2 h-4 w-4" /> Admin
              </DropdownMenuItem>
            )}
            <DropdownMenuItem onClick={() => void logout()}>
              <LogOut className="mr-2 h-4 w-4" /> Sign out
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  );
}
```

- [ ] **Step 17.3: Implement `MobileNav.tsx`**

```tsx
import React from "react";
import { NavLink } from "react-router-dom";
import { Map, FileText, Search, Bell } from "lucide-react";
import { ROUTES } from "@/app/routes";

const ITEMS = [
  { to: ROUTES.home, label: "Map", Icon: Map },
  { to: ROUTES.briefs, label: "Briefs", Icon: FileText },
  { to: ROUTES.screener, label: "Screener", Icon: Search },
  { to: ROUTES.alerts, label: "Alerts", Icon: Bell },
] as const;

export function MobileNav() {
  return (
    <nav
      aria-label="Primary mobile"
      className="fixed bottom-0 left-0 right-0 z-30 flex h-14 border-t border-border bg-surface-1 md:hidden"
    >
      {ITEMS.map(({ to, label, Icon }) => (
        <NavLink
          key={to}
          to={to}
          className={({ isActive }) =>
            `flex flex-1 flex-col items-center justify-center gap-0.5 text-[11px] ${
              isActive ? "text-text" : "text-muted"
            }`
          }
        >
          <Icon className="h-5 w-5" />
          {label}
        </NavLink>
      ))}
    </nav>
  );
}
```

- [ ] **Step 17.4: Implement `Sidebar.tsx` (opt-in scaffold)**

```tsx
import React from "react";

export function Sidebar({ children }: { children?: React.ReactNode }) {
  return (
    <aside className="hidden lg:flex w-56 shrink-0 flex-col border-r border-border bg-surface-1">
      {children}
    </aside>
  );
}
```

- [ ] **Step 17.5: Commit**

```bash
git add src/frontend/layout/TopNav.tsx src/frontend/layout/MobileNav.tsx src/frontend/layout/Sidebar.tsx src/frontend/layout/ThemeToggle.tsx
git commit -m "feat(frontend): TopNav, MobileNav, Sidebar, ThemeToggle"
```

---

## Task 18: CommandPalette + AppShell composition with health gate

**Files:**
- Create: `src/frontend/layout/CommandPalette.tsx`
- Create: `src/frontend/layout/AppShell.tsx`
- Create: `src/frontend/features/system/integrationsApi.ts`

- [ ] **Step 18.1: Implement `CommandPalette.tsx`**

```tsx
import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { CommandDialog, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/ui";
import { ROUTES } from "@/app/routes";

const NAV: ReadonlyArray<{ label: string; path: string; group: string }> = [
  { label: "Intelligence Map", path: ROUTES.home, group: "Navigate" },
  { label: "Briefs", path: ROUTES.briefs, group: "Navigate" },
  { label: "Screener", path: ROUTES.screener, group: "Navigate" },
  { label: "Portfolio", path: ROUTES.portfolio, group: "Navigate" },
  { label: "Watchlist", path: ROUTES.watchlist, group: "Navigate" },
  { label: "Alerts", path: ROUTES.alerts, group: "Navigate" },
  { label: "Q&A", path: ROUTES.qa, group: "Navigate" },
  { label: "Admin: HIL Queue", path: ROUTES.adminHil, group: "Admin" },
  { label: "Admin: Data Sources", path: ROUTES.adminSources, group: "Admin" },
  { label: "Admin: System Operations", path: ROUTES.adminSystem, group: "Admin" },
  { label: "Admin: AI Audit", path: ROUTES.adminAudit, group: "Admin" },
];

export function CommandPalette({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  const nav = useNavigate();
  return (
    <CommandDialog open={open} onOpenChange={onOpenChange}>
      <CommandInput placeholder="Type a command or search…" />
      <CommandList>
        <CommandEmpty>No results.</CommandEmpty>
        {["Navigate", "Admin"].map((g) => (
          <CommandGroup key={g} heading={g}>
            {NAV.filter((n) => n.group === g).map((n) => (
              <CommandItem key={n.path} onSelect={() => { nav(n.path); onOpenChange(false); }}>
                {n.label}
              </CommandItem>
            ))}
          </CommandGroup>
        ))}
      </CommandList>
    </CommandDialog>
  );
}

export function useCommandPalette() {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((v) => !v);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  return { open, setOpen };
}
```

- [ ] **Step 18.2: Implement `AppShell.tsx`**

```tsx
import React from "react";
import { Outlet } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Toaster } from "sonner";
import { Button } from "@/ui";
import { TopNav } from "./TopNav";
import { MobileNav } from "./MobileNav";
import { CommandPalette, useCommandPalette } from "./CommandPalette";

async function pingHealth(): Promise<boolean> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 3_000);
  try {
    const res = await fetch("/health", { signal: ctrl.signal });
    return res.ok;
  } catch {
    return false;
  } finally {
    clearTimeout(timer);
  }
}

export function AppShell() {
  const { open, setOpen } = useCommandPalette();
  const health = useQuery({
    queryKey: ["health"],
    queryFn: pingHealth,
    refetchInterval: 30_000,
    retry: 0,
  });

  if (health.isSuccess && !health.data) {
    return <BackendUnreachable onRetry={() => health.refetch()} />;
  }

  return (
    <div className="min-h-screen bg-surface-0 text-text">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-2 focus:z-50 focus:rounded focus:bg-surface-2 focus:px-3 focus:py-1.5 focus:text-sm"
      >
        Skip to content
      </a>
      <TopNav onOpenCommand={() => setOpen(true)} />
      <main id="main" className="pb-16 md:pb-0">
        <Outlet />
      </main>
      <MobileNav />
      <CommandPalette open={open} onOpenChange={setOpen} />
      <Toaster richColors closeButton position="bottom-right" />
    </div>
  );
}

function BackendUnreachable({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-surface-0 p-6 text-text">
      <div className="max-w-md rounded-lg border border-border bg-surface-1 p-6 text-center">
        <h1 className="text-xl font-semibold">Backend unreachable</h1>
        <p className="mt-2 text-sm text-muted">
          The API is not responding at <code>/health</code>. Confirm <code>docker compose up</code> is running.
        </p>
        <Button className="mt-4" onClick={onRetry}>Retry</Button>
      </div>
    </div>
  );
}
```

- [ ] **Step 18.3: Stub `features/system/integrationsApi.ts` (used by StubModeBadge later)**

```ts
import { z } from "zod";
import { api } from "@/lib/api/client";

const IntegrationSchema = z.object({
  provider: z.string(),
  mode: z.enum(["live", "stub", "missing"]),
  reason: z.string().optional(),
});

export const IntegrationsSchema = z.record(z.string(), IntegrationSchema);
export type Integrations = z.infer<typeof IntegrationsSchema>;

export async function fetchIntegrations(): Promise<Integrations> {
  const raw = await api<unknown>("/system/integrations");
  return IntegrationsSchema.parse(raw);
}
```

- [ ] **Step 18.4: Commit**

```bash
git add src/frontend/layout/CommandPalette.tsx src/frontend/layout/AppShell.tsx src/frontend/features/system/integrationsApi.ts
git commit -m "feat(frontend): AppShell with health gate + CommandPalette + integrations API"
```

---

## Task 19: Wire `App.tsx` providers + minimal route stub for live smoke

**Files:**
- Modify: `src/frontend/app/App.tsx`
- Modify: `src/frontend/app/router.tsx`

- [ ] **Step 19.1: Replace `App.tsx`**

```tsx
import React from "react";
import { BrowserRouter } from "react-router-dom";
import { ErrorBoundary } from "./providers/ErrorBoundary";
import { ThemeProvider } from "./providers/ThemeProvider";
import { QueryProvider } from "./providers/QueryProvider";
import { AuthProvider } from "./providers/AuthProvider";
import { AppRouter } from "./router";

export function App() {
  return (
    <ErrorBoundary>
      <ThemeProvider>
        <QueryProvider>
          <AuthProvider>
            <BrowserRouter>
              <AppRouter />
            </BrowserRouter>
          </AuthProvider>
        </QueryProvider>
      </ThemeProvider>
    </ErrorBoundary>
  );
}
```

- [ ] **Step 19.2: Replace `router.tsx` with the login-only route map (interim)**

```tsx
import React from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import { LoginPage } from "@/features/auth/LoginPage";
import { RegisterPage } from "@/features/auth/RegisterPage";
import { RequireAuth } from "./guards/RequireAuth";
import { AppShell } from "@/layout/AppShell";
import { ROUTES } from "./routes";

export function AppRouter() {
  return (
    <Routes>
      <Route path={ROUTES.login} element={<LoginPage />} />
      <Route path={ROUTES.register} element={<RegisterPage />} />
      <Route
        element={
          <RequireAuth>
            <AppShell />
          </RequireAuth>
        }
      >
        <Route path={ROUTES.home} element={<div className="p-6">App home (interim)</div>} />
      </Route>
      <Route path="*" element={<Navigate to={ROUTES.home} replace />} />
    </Routes>
  );
}
```

- [ ] **Step 19.3: Manual smoke**

Run: `npm run dev`
Expected:
- Visit `http://localhost:5173/` while backend is down → "Backend unreachable" panel (or immediate `/login` redirect if anonymous resolves first; both are acceptable).
- Visit `/login` → login form renders.
- Theme toggle works in TopNav once you log in (you can't log in yet without backend — confirm only that the route loads cleanly).

- [ ] **Step 19.4: Commit**

```bash
git add src/frontend/app/App.tsx src/frontend/app/router.tsx
git commit -m "feat(frontend): wire provider stack + login route into router"
```

---

## Task 20: Migrate admin HIL page

**Files:**
- Create: `src/frontend/pages/admin/hil/HilQueue.tsx` (moved)
- Create: `src/frontend/pages/admin/hil/HilQueueTable.tsx`, `HilItemDetail.tsx`, `HilActionButtons.tsx`, `useHilQueue.ts`
- Delete: `frontend/src/pages/admin/HilQueue.tsx` and `frontend/src/components/admin/hil/*`

- [ ] **Step 20.1: Move files**

Run from repo root:

```bash
mkdir -p src/frontend/pages/admin/hil
git mv frontend/src/pages/admin/HilQueue.tsx src/frontend/pages/admin/hil/HilQueue.tsx
git mv frontend/src/components/admin/hil/HilQueueTable.tsx src/frontend/pages/admin/hil/HilQueueTable.tsx
git mv frontend/src/components/admin/hil/HilItemDetail.tsx src/frontend/pages/admin/hil/HilItemDetail.tsx
git mv frontend/src/components/admin/hil/HilActionButtons.tsx src/frontend/pages/admin/hil/HilActionButtons.tsx
git mv frontend/src/components/admin/hil/useHilQueue.ts src/frontend/pages/admin/hil/useHilQueue.ts
git mv frontend/src/components/admin/hil/HilQueueTable.test.tsx src/frontend/pages/admin/hil/HilQueueTable.test.tsx
git mv frontend/src/components/admin/hil/HilActionButtons.test.tsx src/frontend/pages/admin/hil/HilActionButtons.test.tsx
git mv frontend/src/components/admin/hil/useHilQueue.test.ts src/frontend/pages/admin/hil/useHilQueue.test.ts
git mv frontend/src/pages/admin/HilQueue.test.tsx src/frontend/pages/admin/hil/HilQueue.test.tsx
```

- [ ] **Step 20.2: Update imports in moved files**

For every file under `src/frontend/pages/admin/hil/`:
- Replace relative imports referring to `../../components/admin/hil/...` with sibling imports `./...`.
- Replace `useCurrentUser` imports from `../../../hooks/useCurrentUser` with `@/app/providers/AuthProvider` and rename usage to `useCurrentUser`.
- Replace any `fetch("/api/...")` calls with `api()` from `@/lib/api/client`.
- Update class names per the substitution map in Task 15.2.

- [ ] **Step 20.3: Run the HIL tests**

Run: `npm test -- src/frontend/pages/admin/hil/`
Expected: tests run; any failures are due to either (a) import path issues — fix and re-run, or (b) tests that assert against the old class names — update assertions.

- [ ] **Step 20.4: Commit**

```bash
git add src/frontend/pages/admin/hil/
git rm -r frontend/src/pages/admin/HilQueue.tsx frontend/src/components/admin/hil/ frontend/src/pages/admin/HilQueue.test.tsx 2>/dev/null || true
git commit -m "refactor(frontend): migrate HIL admin page to src/frontend/pages/admin/hil"
```

---

## Task 21: Migrate admin Sources page

**Files:**
- Create: `src/frontend/pages/admin/sources/*` (moved)
- Delete: `frontend/src/pages/admin/sources/*`

- [ ] **Step 21.1: Move files**

```bash
mkdir -p src/frontend/pages/admin/sources/hooks
git mv frontend/src/pages/admin/sources/SourcesPage.tsx src/frontend/pages/admin/sources/SourcesPage.tsx
git mv frontend/src/pages/admin/sources/SourcesPage.test.tsx src/frontend/pages/admin/sources/SourcesPage.test.tsx
git mv frontend/src/pages/admin/sources/SourceList.tsx src/frontend/pages/admin/sources/SourceList.tsx
git mv frontend/src/pages/admin/sources/AddSourceModal.tsx src/frontend/pages/admin/sources/AddSourceModal.tsx
git mv frontend/src/pages/admin/sources/AddSourceModal.test.tsx src/frontend/pages/admin/sources/AddSourceModal.test.tsx
git mv frontend/src/pages/admin/sources/SocialSourcesPanel.tsx src/frontend/pages/admin/sources/SocialSourcesPanel.tsx
git mv frontend/src/pages/admin/sources/BindingsPanel.tsx src/frontend/pages/admin/sources/BindingsPanel.tsx
git mv frontend/src/pages/admin/sources/BindingsPanel.test.tsx src/frontend/pages/admin/sources/BindingsPanel.test.tsx
git mv frontend/src/pages/admin/sources/hooks/useSources.ts src/frontend/pages/admin/sources/hooks/useSources.ts
git mv frontend/src/pages/admin/sources/hooks/useBindings.ts src/frontend/pages/admin/sources/hooks/useBindings.ts
```

- [ ] **Step 21.2: Rewire imports + API client**

Apply the same import substitution rules as Task 20.2.

- [ ] **Step 21.3: Run the Sources tests**

Run: `npm test -- src/frontend/pages/admin/sources/`
Expected: green (after import fixes).

- [ ] **Step 21.4: Commit**

```bash
git add src/frontend/pages/admin/sources/
git rm -r frontend/src/pages/admin/sources/ 2>/dev/null || true
git commit -m "refactor(frontend): migrate Sources admin page to src/frontend/pages/admin/sources"
```

---

## Task 22: Consolidate AdminLayout + Admin/System; delete duplicates

**Files:**
- Move: `src/frontend/admin/AdminLayout.tsx` → `src/frontend/pages/admin/AdminLayout.tsx`
- Move: `src/frontend/admin/RequireAdmin.tsx` → DELETE (already replaced by `app/guards/RequireAdmin.tsx`)
- Keep canonical: `src/frontend/pages/admin/system/*` (already in canonical location)
- Delete: `frontend/src/pages/admin/system/*`, `frontend/src/pages/admin/AdminNav.tsx`

- [ ] **Step 22.1: Move AdminLayout**

```bash
git mv src/frontend/admin/AdminLayout.tsx src/frontend/pages/admin/AdminLayout.tsx
git mv tests/frontend/admin/AdminLayout.test.tsx tests/frontend/admin/AdminLayout.test.tsx
# (Test path unchanged — only the source moves)
```

Rewrite `AdminLayout.tsx` to use shadcn `Tabs`:

```tsx
import React from "react";
import { NavLink, Outlet } from "react-router-dom";
import { ROUTES } from "@/app/routes";

const TABS = [
  { to: ROUTES.adminHil, label: "HIL Queue" },
  { to: ROUTES.adminSources, label: "Data Sources" },
  { to: ROUTES.adminSystem, label: "System Ops" },
  { to: ROUTES.adminAudit, label: "AI Audit" },
];

export function AdminLayout() {
  return (
    <div className="p-6">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight">Admin</h1>
        <nav className="mt-3 flex gap-1 border-b border-border" aria-label="Admin tabs">
          {TABS.map((t) => (
            <NavLink
              key={t.to}
              to={t.to}
              className={({ isActive }) =>
                `border-b-2 px-3 py-1.5 text-sm ${
                  isActive ? "border-signal text-text" : "border-transparent text-muted hover:text-text"
                }`
              }
            >
              {t.label}
            </NavLink>
          ))}
        </nav>
      </div>
      <Outlet />
    </div>
  );
}
```

- [ ] **Step 22.2: Delete the duplicated old RequireAdmin and admin folder shells**

```bash
git rm src/frontend/admin/RequireAdmin.tsx
rmdir src/frontend/admin 2>/dev/null || true
```

- [ ] **Step 22.3: Delete `frontend/src` admin/system + AdminNav duplicates**

```bash
git rm -r frontend/src/pages/admin/system/
git rm frontend/src/pages/admin/AdminNav.tsx
```

- [ ] **Step 22.4: Reapply token substitutions to canonical admin/system files**

For each file in `src/frontend/pages/admin/system/*`:
- Apply the substitution map from Task 15.2.
- Replace local `fetch` calls with `api()` from `@/lib/api/client`.

- [ ] **Step 22.5: Run admin system tests**

Run: `npm test -- src/frontend/pages/admin/system/ tests/frontend/admin/`
Expected: green.

- [ ] **Step 22.6: Commit**

```bash
git add src/frontend/pages/admin/AdminLayout.tsx src/frontend/pages/admin/system/
git commit -m "refactor(frontend): consolidate AdminLayout + dedupe admin/system"
```

---

## Task 23: Resolve QA duplicates

**Files:**
- Keep canonical: `src/frontend/components/qa/*`, `src/frontend/api/qaApi.ts`
- Delete: `frontend/src/components/qa/*`, `frontend/src/api/qaApi.ts`
- Move canonical to its new home under `src/frontend/features/qa/`

- [ ] **Step 23.1: Move QA to features**

```bash
mkdir -p src/frontend/features/qa
git mv src/frontend/components/qa/QAChatPanel.tsx src/frontend/features/qa/QAChatPanel.tsx
git mv src/frontend/components/qa/QACostLimitNotice.tsx src/frontend/features/qa/QACostLimitNotice.tsx
git mv src/frontend/components/qa/QAMessageBubble.tsx src/frontend/features/qa/QAMessageBubble.tsx
git mv src/frontend/components/qa/QAMessageList.tsx src/frontend/features/qa/QAMessageList.tsx
git mv src/frontend/components/qa/QASourcesList.tsx src/frontend/features/qa/QASourcesList.tsx
git mv src/frontend/components/qa/useQASession.ts src/frontend/features/qa/useQASession.ts
git mv src/frontend/components/qa/useQAStream.ts src/frontend/features/qa/useQAStream.ts
git mv src/frontend/api/qaApi.ts src/frontend/features/qa/qaApi.ts
```

Update import paths inside these files: `../../api/qaApi` → `./qaApi`, etc.

- [ ] **Step 23.2: Delete duplicates**

```bash
git rm -r frontend/src/components/qa/ frontend/src/api/qaApi.ts
```

- [ ] **Step 23.3: Update `tests/frontend/qa/*` imports**

For each test under `tests/frontend/qa/`, change imports from `@/components/qa/...` or relative `frontend/src/...` to `@/features/qa/...`.

- [ ] **Step 23.4: Commit**

```bash
git add src/frontend/features/qa/ tests/frontend/qa/
git commit -m "refactor(frontend): consolidate QA into features/qa; remove duplicate from frontend/"
```

---

## Task 24: Reorganise AI Audit → `pages/admin/ai-audit`

**Files:**
- Move: `src/frontend/admin/ai-audit/*` → `src/frontend/pages/admin/ai-audit/*`

- [ ] **Step 24.1: Move files**

```bash
mkdir -p src/frontend/pages/admin/ai-audit
git mv src/frontend/admin/ai-audit/* src/frontend/pages/admin/ai-audit/
rmdir src/frontend/admin/ai-audit 2>/dev/null || true
```

- [ ] **Step 24.2: Update import paths within moved files**

Tooling: run a project-wide `tsc --noEmit`; fix every reported import.

Run: `npx tsc --noEmit 2>&1 | grep "Cannot find module" | head -40`
Fix each reported path manually using IDE refactor or sed:
- `@/admin/...` → `@/pages/admin/...`

- [ ] **Step 24.3: Commit**

```bash
git add src/frontend/pages/admin/ai-audit/
git commit -m "refactor(frontend): move admin AI audit pages into pages/admin/ai-audit"
```

---

## Task 25: Reorganise feature folders — CompanyDetail, Alerts, IndicatorBuilder, Scoring

**Files:**
- Move CompanyDetail: `src/frontend/pages/CompanyDetail/*` → `src/frontend/features/company-detail/*`
- Move Alerts: combine `src/frontend/pages/AlertsCenterPage.tsx`, `src/frontend/components/alerts/*`, `src/frontend/hooks/useAlerts*.ts` → `src/frontend/features/alerts/`
- Move IndicatorBuilder: `src/frontend/components/indicator-builder/*` → `src/frontend/features/indicator-builder/*`
- Move Scoring: `src/frontend/components/scoring/*` → `src/frontend/features/scoring/*`

- [ ] **Step 25.1: Move CompanyDetail**

```bash
mkdir -p src/frontend/features/company-detail
git mv src/frontend/pages/CompanyDetail/* src/frontend/features/company-detail/
rmdir src/frontend/pages/CompanyDetail 2>/dev/null || true
```

Fix imports inside moved files (`../../api/...` → `@/lib/api/...`, etc.).
Update test files under `tests/frontend/CompanyDetail/` imports to `@/features/company-detail/...`.

- [ ] **Step 25.2: Move Alerts**

```bash
mkdir -p src/frontend/features/alerts
git mv src/frontend/pages/AlertsCenterPage.tsx src/frontend/features/alerts/AlertsCenterPage.tsx
git mv src/frontend/components/alerts/* src/frontend/features/alerts/
git mv src/frontend/hooks/useAlerts.ts src/frontend/features/alerts/useAlerts.ts
git mv src/frontend/hooks/useAlertRules.ts src/frontend/features/alerts/useAlertRules.ts
git mv src/frontend/hooks/useAntiFatigueSettings.ts src/frontend/features/alerts/useAntiFatigueSettings.ts
git mv src/frontend/hooks/useMutateAlertRule.ts src/frontend/features/alerts/useMutateAlertRule.ts
rmdir src/frontend/components/alerts 2>/dev/null || true
```

Fix imports inside the moved files and inside `tests/frontend/alerts/` test files.

- [ ] **Step 25.3: Move IndicatorBuilder**

```bash
mkdir -p src/frontend/features/indicator-builder
git mv src/frontend/components/indicator-builder/* src/frontend/features/indicator-builder/
rmdir src/frontend/components/indicator-builder 2>/dev/null || true
```

- [ ] **Step 25.4: Move Scoring**

```bash
mkdir -p src/frontend/features/scoring
git mv src/frontend/components/scoring/* src/frontend/features/scoring/
rmdir src/frontend/components/scoring 2>/dev/null || true
```

- [ ] **Step 25.5: Run typecheck and fix every import error**

Run: `npx tsc --noEmit 2>&1 | head -60`
Fix all reported imports. Do not progress until `tsc --noEmit` exits 0.

- [ ] **Step 25.6: Commit**

```bash
git add src/frontend/features/
git commit -m "refactor(frontend): reorganise CompanyDetail, Alerts, IndicatorBuilder, Scoring into features/"
```

---

## Task 26: Final cleanup — delete orphan files

**Files:**
- Delete: `src/frontend/components/layout/TopNav.tsx`
- Delete: `src/frontend/pages/MapPage.tsx`
- Delete: `src/frontend/features/map/EventPopup.tsx` (duplicate; PD version is canonical)
- Delete: `src/frontend/hooks/useCurrentUser.ts` (replaced by AuthProvider)
- Move: `src/frontend/hooks/usePortfolioContext.ts` → `src/frontend/features/portfolio/usePortfolioContext.ts`
- Move: `src/frontend/hooks/useSystemOps.ts` → `src/frontend/pages/admin/system/hooks/useSystemOps.ts` (if not already there)

- [ ] **Step 26.1: Delete and move**

```bash
git rm src/frontend/components/layout/TopNav.tsx 2>/dev/null || true
git rm src/frontend/pages/MapPage.tsx 2>/dev/null || true
git rm src/frontend/features/map/EventPopup.tsx 2>/dev/null || true
git rm src/frontend/hooks/useCurrentUser.ts 2>/dev/null || true

mkdir -p src/frontend/features/portfolio
git mv src/frontend/hooks/usePortfolioContext.ts src/frontend/features/portfolio/usePortfolioContext.ts 2>/dev/null || true

# Remove empty dirs
rmdir src/frontend/components/layout 2>/dev/null || true
rmdir src/frontend/components 2>/dev/null || true
rmdir src/frontend/features/map 2>/dev/null || true
```

- [ ] **Step 26.2: Fix any imports broken by deletions**

Run: `npx tsc --noEmit 2>&1 | head -40`
For each "Cannot find module" — either the import is from a deleted file (delete the importing code) or it points to a moved location (update path).

Special case: the existing `IntelligenceMap.tsx` imports two non-existent modules:
- `./lib/empty-state-message` — create stub
- `./lib/time-mode-empty-state` — create stub

Create `src/frontend/features/intelligence-map/lib/empty-state-message.ts`:

```ts
export function generateEmptyStateMessage(filterCount: number): string {
  if (filterCount === 0) return "No events to display.";
  return `No events match the current ${filterCount} filter${filterCount === 1 ? "" : "s"}.`;
}
```

Create `src/frontend/features/intelligence-map/lib/time-mode-empty-state.ts`:

```ts
import type { DateRange } from "../types/time-mode.types";

export function generateTimeModeEmptyStateMessage(
  mode: "live" | "historical" | "playback",
  range?: DateRange,
): string {
  if (mode === "live") return "Waiting for the next event…";
  if (mode === "historical" && range) {
    return `No historical events between ${range.start.toISOString().slice(0, 10)} and ${range.end.toISOString().slice(0, 10)}.`;
  }
  return "No events to display.";
}
```

Adjust shape if the tests under `tests/frontend/intelligence-map/time-mode-empty-state.test.ts` expect a different signature; pass those tests, then iterate.

- [ ] **Step 26.3: `tsc --noEmit` green**

Run: `npx tsc --noEmit`
Expected: exit 0.

- [ ] **Step 26.4: Commit**

```bash
git add -A src/frontend/
git commit -m "refactor(frontend): final cleanup + repair broken local imports (intelligence-map/lib stubs)"
```

---

## Task 27: ComingSoon component + REQ titles map + full router mount

**Files:**
- Create: `src/frontend/app/ComingSoon.tsx`
- Create: `src/frontend/app/reqTitles.ts`
- Create: `src/frontend/app/NotFound.tsx`
- Modify: `src/frontend/app/router.tsx`

- [ ] **Step 27.1: Create `reqTitles.ts`**

```ts
export const REQ_TITLES: Record<string, string> = {
  "PLAN-F-019": "Intelligence Map (Primary Interface)",
  "PLAN-F-020": "Progressive Disclosure UI",
  "PLAN-F-021": "Map Live / Historical / Playback Modes",
  "PLAN-F-022": "Screener",
  "PLAN-F-023": "Company Detail and On-Demand Analysis",
  "PLAN-F-024": "Portfolio and Watchlist Management",
  "PLAN-F-025": "Alerts Center",
  "PLAN-F-026": "Briefs and Reports Reader",
  "PLAN-F-027": "Q&A Chat Interface",
  "PLAN-F-029": "Admin: AI Audit Console",
};
```

- [ ] **Step 27.2: Create `ComingSoon.tsx`**

```tsx
import React from "react";
import { Link } from "react-router-dom";
import { Construction } from "lucide-react";
import { Button } from "@/ui";
import { ROUTES } from "./routes";
import { REQ_TITLES } from "./reqTitles";

export function ComingSoon({ plan }: { plan: keyof typeof REQ_TITLES | string }) {
  const title = REQ_TITLES[plan] ?? "Coming soon";
  return (
    <div className="flex min-h-[70vh] items-center justify-center p-6">
      <div className="max-w-md rounded-lg border border-border bg-surface-1 p-8 text-center">
        <Construction className="mx-auto h-8 w-8 text-muted" />
        <div className="mt-3 text-xs font-mono uppercase tracking-wider text-muted">{plan}</div>
        <h1 className="mt-1 text-xl font-semibold">{title}</h1>
        <p className="mt-2 text-sm text-muted">
          Wired in a later phase. The route is registered and the components exist — Phase 2/3 connects them to live backend APIs.
        </p>
        <Button asChild className="mt-5" variant="secondary">
          <Link to={ROUTES.home}>Back to map</Link>
        </Button>
      </div>
    </div>
  );
}
```

- [ ] **Step 27.3: Create `NotFound.tsx`**

```tsx
import React from "react";
import { Link } from "react-router-dom";
import { Button } from "@/ui";
import { ROUTES } from "./routes";

export function NotFound() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-surface-0 p-6 text-text">
      <div className="text-center">
        <div className="text-5xl font-bold tracking-tight">404</div>
        <p className="mt-2 text-sm text-muted">That page does not exist.</p>
        <Button asChild className="mt-4"><Link to={ROUTES.home}>Go home</Link></Button>
      </div>
    </div>
  );
}
```

- [ ] **Step 27.4: Replace `router.tsx` with the full mount**

```tsx
import React from "react";
import { Routes, Route } from "react-router-dom";
import { LoginPage } from "@/features/auth/LoginPage";
import { RegisterPage } from "@/features/auth/RegisterPage";
import { OnboardingFlow } from "@/features/onboarding/OnboardingFlow";
import { RequireAuth } from "./guards/RequireAuth";
import { RequireAdmin } from "./guards/RequireAdmin";
import { OnboardingGate } from "./guards/OnboardingGate";
import { AppShell } from "@/layout/AppShell";
import { AdminLayout } from "@/pages/admin/AdminLayout";
import { HilQueue } from "@/pages/admin/hil/HilQueue";
import { SourcesPage } from "@/pages/admin/sources/SourcesPage";
import { SystemOpsPage } from "@/pages/admin/system/SystemOpsPage";
import { ComingSoon } from "./ComingSoon";
import { NotFound } from "./NotFound";
import { ROUTES } from "./routes";

export function AppRouter() {
  return (
    <Routes>
      <Route path={ROUTES.login} element={<LoginPage />} />
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
  );
}
```

- [ ] **Step 27.5: Verify the OnboardingFlow component exists at the import path**

Run: `ls src/frontend/features/onboarding/OnboardingFlow.tsx`
If missing, copy the existing implementation from its current location (it was already moved in Task 25 if it lived under `src/frontend/features/onboarding/`). If it lives elsewhere, `git mv` it now and update the import in `router.tsx`.

- [ ] **Step 27.6: Smoke test all routes (manual)**

Run: `npm run dev`
Visit each path; confirm:
- `/login`, `/register` → render auth pages.
- `/` (after login) → ComingSoon for PLAN-F-019.
- `/briefs`, `/screener`, `/portfolio`, `/watchlist`, `/alerts`, `/qa`, `/events/x/deep-dive`, `/companies/AAPL`, `/briefs/abc` → ComingSoon cards.
- `/admin/hil`, `/admin/sources`, `/admin/system` → real content (if backend up); otherwise the page shell renders, even if data is missing.
- `/admin/ai-audit` → ComingSoon.
- `/bogus` → NotFound.

- [ ] **Step 27.7: Commit**

```bash
git add src/frontend/app/
git commit -m "feat(frontend): mount full route map with ComingSoon placeholders"
```

---

## Task 28: Repair remaining broken local imports

**Files:**
- Multiple files across `src/frontend/` (case-by-case)

- [ ] **Step 28.1: Run a full type check**

Run: `npx tsc --noEmit 2>&1 | tee /tmp/tsc.log`
Expected: triage every error.

- [ ] **Step 28.2: For each `Cannot find module` error**

Categorize and fix:

1. **Missing utility file** → create a minimal stub that satisfies the tests calling it (similar to Task 26 Step 26.2).
2. **Wrong path after move** → update the import.
3. **Symbol renamed** → update the import name.
4. **Genuinely deleted** → delete the importing code if it is now dead, or restore the symbol if it is still used.

- [ ] **Step 28.3: Final type-check green**

Run: `npm run typecheck`
Expected: exit 0.

- [ ] **Step 28.4: Commit**

```bash
git add -A src/frontend/
git commit -m "fix(frontend): repair broken local imports surfaced by tsc"
```

---

## Task 29: Migrate test suite to Vitest

**Files:**
- Multiple files under `tests/frontend/**` and `src/frontend/**/*.test.{ts,tsx}`

- [ ] **Step 29.1: Convert Jest → Vitest API per file**

For every test file under `tests/frontend/` and any colocated `*.test.tsx` in `src/frontend/`:
- Replace `jest.fn` → `vi.fn`
- Replace `jest.mock` → `vi.mock`
- Replace `jest.spyOn` → `vi.spyOn`
- Replace `jest.clearAllMocks` → `vi.clearAllMocks`
- Replace `import "@testing-library/jest-dom/extend-expect"` → remove (handled in setupTests).
- Replace any `require()` with ESM `import`.

PowerShell helper to find candidates:
```powershell
Get-ChildItem -Recurse -Path tests/frontend,src/frontend -Include "*.test.ts","*.test.tsx" |
  Select-String -Pattern "jest\." -List
```

- [ ] **Step 29.2: Update import paths**

For every test, replace absolute imports starting with `frontend/src/...` or relative imports leaving the canonical tree with `@/...` aliases.

- [ ] **Step 29.3: Skip Phase 2/3 wiring tests**

Identify tests that exercise feature-integration wiring whose backend wiring is Phase 2/3. For each:
- Change `describe(...)` → `describe.skip(...)` or `it(...)` → `it.skip(...)`.
- Add a comment `// Phase 2: enable when wired in PLAN-F-XXX`.

Candidates (use judgement; add to the list when applicable):
- `tests/frontend/intelligence-map/map-websocket.test.tsx` → Phase 2 (WS consumer).
- `tests/frontend/intelligence-map/IntelligenceMap.responsive.test.tsx` → keep if it only renders the component; skip if it requires WS feed.
- `tests/frontend/portfolio/OnboardingFlow.test.tsx` → keep (onboarding is Phase 1).
- `tests/frontend/CompanyDetail/*` → skip wiring tests; keep unit tests that don't hit `fetch`.
- `tests/frontend/alerts/AlertsCenterResponsive.test.tsx` → skip if it requires the alerts API.

- [ ] **Step 29.4: Run the whole suite**

Run: `npm test`
Expected: a clean run. Failing tests fall into three buckets:
1. Tests for retained code that legitimately broke during migration → fix.
2. Tests that exercise behaviour we intentionally changed → update the assertion.
3. Tests for Phase 2/3 wiring → `.skip` per Step 29.3.

Iterate until: passed + skipped = total, failed = 0.

- [ ] **Step 29.5: Coverage check on new shell modules**

Run: `npm run test:coverage`
Expected: `src/frontend/lib/api/*` and `src/frontend/app/providers/*` show ≥ 80 % line coverage. If lower, add targeted tests until the threshold is met.

- [ ] **Step 29.6: Commit**

```bash
git add -A tests/frontend/ src/frontend/
git commit -m "test(frontend): migrate suite to vitest; skip Phase 2/3 wiring tests"
```

---

## Task 30: Lint setup + token-only / no-direct-fetch enforcement

**Files:**
- Create: `eslint.config.js`
- Create: `.prettierrc.json`

- [ ] **Step 30.1: Create `eslint.config.js`**

```js
import js from "@eslint/js";
import tseslint from "typescript-eslint";
import react from "eslint-plugin-react";
import hooks from "eslint-plugin-react-hooks";
import a11y from "eslint-plugin-jsx-a11y";

export default tseslint.config(
  { ignores: ["dist", "node_modules", "src/frontend/ui/**"] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ["**/*.{ts,tsx}"],
    plugins: {
      react,
      "react-hooks": hooks,
      "jsx-a11y": a11y,
    },
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "module",
      globals: { window: "readonly", document: "readonly", fetch: "readonly", WebSocket: "readonly", EventSource: "readonly", CloseEvent: "readonly", CustomEvent: "readonly" },
    },
    settings: { react: { version: "detect" } },
    rules: {
      "react/jsx-uses-react": "off",
      "react/react-in-jsx-scope": "off",
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/exhaustive-deps": "warn",
      "@typescript-eslint/no-unused-vars": ["warn", { argsIgnorePattern: "^_" }],
      "@typescript-eslint/no-explicit-any": "warn",
      "jsx-a11y/alt-text": "error",
      "jsx-a11y/anchor-is-valid": "warn",
      "no-restricted-syntax": [
        "error",
        {
          selector:
            "CallExpression[callee.name='fetch'][arguments.0.value=/^\\/api\\//]",
          message:
            "Do not call fetch('/api/...') directly. Use api() from @/lib/api/client.",
        },
        {
          selector: "JSXAttribute[name.name='style']",
          message:
            "Avoid inline style props for color/spacing. Use Tailwind utility classes against design tokens.",
        },
      ],
    },
  },
  {
    files: ["src/frontend/lib/api/client.ts"],
    rules: { "no-restricted-syntax": "off" },
  },
  {
    files: ["**/*.test.{ts,tsx}", "tests/**"],
    rules: {
      "no-restricted-syntax": "off",
      "@typescript-eslint/no-explicit-any": "off",
    },
  },
);
```

- [ ] **Step 30.2: Create `.prettierrc.json`**

```json
{
  "semi": true,
  "singleQuote": false,
  "trailingComma": "all",
  "printWidth": 100,
  "plugins": ["prettier-plugin-tailwindcss"]
}
```

- [ ] **Step 30.3: Run lint**

Run: `npm run lint`
Expected: errors at first — fix them one by one:
- Direct `fetch("/api/...")` calls in feature code → replace with `api()`.
- Inline `style={{ color: ..., padding: ... }}` → replace with Tailwind class.
- Missing alt/label attributes → fix.

Iterate until `npm run lint` exits 0.

- [ ] **Step 30.4: Commit**

```bash
git add eslint.config.js .prettierrc.json
git commit -m "chore(frontend): ESLint flat config + no-direct-fetch + no-inline-style rules"
```

---

## Task 31: Delete the legacy `frontend/` directory

**Files:**
- Delete: `frontend/` (entire directory)

- [ ] **Step 31.1: Verify nothing imports from it**

Run: `npx tsc --noEmit && npm test && npm run lint`
Expected: all green. If anything still references `frontend/src/...`, fix it before deleting.

- [ ] **Step 31.2: Run a final build**

Run: `npm run build`
Expected: outputs to `dist/frontend/`. Open `dist/frontend/index.html` and confirm bundled assets reference `assets/...`.

- [ ] **Step 31.3: Delete `frontend/`**

```bash
git rm -rf frontend/
```

- [ ] **Step 31.4: Verify dev server, tests, build still green**

```bash
npm run typecheck
npm run lint
npm test
npm run build
```

All exit 0.

- [ ] **Step 31.5: Commit**

```bash
git commit -m "chore(frontend): delete legacy frontend/ directory; phase 1 file moves complete"
```

---

## Task 32: Backend audit — confirm Phase-1 endpoints exist & conform

**Files:**
- Create: `scripts/check-phase1-backend.mjs`

- [ ] **Step 32.1: Create the audit script**

```js
#!/usr/bin/env node
// Confirms the Phase-1 backend contract. Run while `docker compose up` is live.
const BASE = process.env.STOKAI_API ?? "http://localhost:8000";

const checks = [
  { method: "GET",  path: "/health",                       expect: (r) => r.status === 200 },
  { method: "POST", path: "/api/v1/auth/refresh",          expect: (r) => [200, 401].includes(r.status) },
  { method: "GET",  path: "/api/v1/me",                    expect: (r) => [200, 401].includes(r.status) },
  { method: "GET",  path: "/api/v1/onboarding/state",      expect: (r) => [200, 401].includes(r.status) },
  { method: "GET",  path: "/api/v1/system/integrations",   expect: (r) => [200, 401].includes(r.status) },
];

let failed = 0;
for (const c of checks) {
  try {
    const r = await fetch(BASE + c.path, { method: c.method });
    const ok = c.expect(r);
    console.log(`${ok ? "✔" : "✘"} ${c.method} ${c.path} → ${r.status}`);
    if (!ok) failed += 1;
  } catch (err) {
    console.log(`✘ ${c.method} ${c.path} → ${err.message}`);
    failed += 1;
  }
}

// Envelope shape check for /api/v1/me when authenticated (informational only)
process.exit(failed === 0 ? 0 : 1);
```

- [ ] **Step 32.2: Run the audit**

```bash
docker compose up -d
node scripts/check-phase1-backend.mjs
```

Expected: all checks ✔. Any ✘ becomes a backend task tracked under Phase 1 — create them as TODO items in your tracker and continue with the audit summary only after the failures are fixed.

- [ ] **Step 32.3: Commit**

```bash
git add scripts/check-phase1-backend.mjs
git commit -m "chore(frontend): add Phase 1 backend contract audit script"
```

---

## Task 33: Documentation updates

**Files:**
- Modify: `docs/ARCHITECTURE.md`
- Modify: `USER-GUIDE.md`
- Create: `src/frontend/README.md`

- [ ] **Step 33.1: Update `docs/ARCHITECTURE.md`**

Add (or replace) a "Frontend Layout" section near the existing layout discussion:

```markdown
### Frontend Layout (Phase 1)

The frontend lives entirely under `src/frontend/`. Vite's `root` is set to this
directory, so `index.html`, `main.tsx`, and the bundle entry point all live
inside it. The provider stack is composed top-down:

  ErrorBoundary
    └─ ThemeProvider (next-themes)
        └─ QueryProvider (@tanstack/react-query)
            └─ AuthProvider
                └─ BrowserRouter
                    └─ AppRouter → AppShell → Outlet

All HTTP, SSE, and WebSocket traffic flows through `src/frontend/lib/api/*`.
Features never call `fetch` against `/api/...` directly (enforced by ESLint).
Authentication uses an in-memory access token plus an httpOnly refresh cookie
issued by the backend.

Phase 1 routes show real content for: `/login`, `/register`, `/onboarding`,
`/admin/hil`, `/admin/sources`, `/admin/system`. All other routes mount a
`<ComingSoon plan="…" />` placeholder that names the PLAN-F-NNN that will wire
the feature in a later phase.
```

- [ ] **Step 33.2: Update `USER-GUIDE.md`**

Find the section that documents `npm` scripts and replace with:

```markdown
### Frontend scripts

| Script | Purpose |
|---|---|
| `npm run dev` | Vite dev server on port 5173 (proxies `/api`, `/health`, `/ws` to localhost:8000) |
| `npm run build` | Type-check + production build into `dist/frontend/` |
| `npm run preview` | Serve the production build locally |
| `npm test` | Vitest single run |
| `npm run test:watch` | Vitest watch mode |
| `npm run test:coverage` | Vitest coverage report |
| `npm run lint` | ESLint with zero warnings allowed |
| `npm run format` | Prettier write across `src/frontend` |
| `npm run typecheck` | `tsc --noEmit` |

The frontend expects the API on `localhost:8000` for `npm run dev`; production
builds are served by FastAPI on the same origin.
```

- [ ] **Step 33.3: Create `src/frontend/README.md`**

```markdown
# StokAI Frontend

Vite + React + TypeScript SPA. All source lives in this directory.

## Conventions

- **`features/<feature>/`** — one folder per requirement. Contains components,
  hooks, API client wrappers, and tests for that feature. Add new features
  here; do not place feature code under `components/` or `pages/`.
- **`pages/admin/<area>/`** — admin-only routes. Wrapped by `<RequireAdmin>`
  in the router.
- **`ui/`** — shadcn primitives. Owned source; safe to edit. Always re-export
  via `@/ui`.
- **`layout/`** — `AppShell`, `TopNav`, `MobileNav`, `Sidebar`,
  `CommandPalette`. Anything that frames a route.
- **`lib/api/`** — the single API client. **No feature is allowed to call
  `fetch` against `/api/...`** — use `api()`.
- **`styles/`** — `globals.css` (Tailwind v4 + tokens), `tokens.css` (CSS
  variables). Token names are stable across phases.

## Adding a feature

1. Create `src/frontend/features/<name>/`.
2. Build components using `@/ui` primitives and Tailwind utility classes
   bound to the design tokens (`bg-surface-1`, `text-text`, `border-border`,
   etc.). No inline styles for color/spacing.
3. Use `api()` (or `apiStream` / `apiSocket`) for backend traffic. Wrap
   responses in `zod` schemas for runtime contract enforcement.
4. Wire the route in `src/frontend/app/router.tsx`. Replace the route's
   `<ComingSoon>` element with your page.
```

- [ ] **Step 33.4: Commit**

```bash
git add docs/ARCHITECTURE.md USER-GUIDE.md src/frontend/README.md
git commit -m "docs: update for Phase 1 frontend foundation"
```

---

## Task 34: End-to-end verification

**Files:**
- No file changes (verification only).

- [ ] **Step 34.1: Full build pipeline**

```bash
npm install
npm run typecheck
npm run lint
npm test
npm run build
```

All exit 0.

- [ ] **Step 34.2: docker-compose smoke**

```bash
docker compose up -d
node scripts/check-phase1-backend.mjs
npm run dev
```

Visit `http://localhost:5173/`. Manual checks:

- Anonymous redirected to `/login`.
- Submit invalid credentials → inline error.
- Register a new user → land on `/onboarding`.
- Complete or skip onboarding → land on `/` showing `<ComingSoon plan="PLAN-F-019" />`.
- TopNav: theme toggle works without flash; user menu shows email; sign out returns to `/login`.
- `⌘K` opens the command palette; selecting "Briefs" navigates to `/briefs` with ComingSoon card.
- Visit `/admin/hil` (after promoting your user to `admin` in the DB) → real HIL queue renders.
- `/admin/ai-audit` → ComingSoon.
- `/bogus-path` → 404 page.
- Stop the backend (`docker compose stop api`) → reload → "Backend unreachable" panel.
- Restart backend, click "Retry" → app resumes.

- [ ] **Step 34.3: Tab through `/login` with keyboard**

Confirm focus rings are visible on the email field, password field, sign-in button, "Forgot password?", and "Create account". No `outline: none` without a replacement ring.

- [ ] **Step 34.4: Lighthouse accessibility (manual)**

In Chrome DevTools → Lighthouse, run Accessibility on `/login` and `/`.
Expected: ≥ 95 on both.

- [ ] **Step 34.5: Stop servers**

```bash
# Ctrl+C in the `npm run dev` terminal
docker compose down
```

- [ ] **Step 34.6: Tag the completion**

```bash
git tag -a phase-1-foundation -m "Phase 1 frontend foundation complete"
```

(Do not push the tag; user pushes manually after reviewing.)

---

## Task 35: PR-ready summary

**Files:**
- No file changes.

- [ ] **Step 35.1: Summarise the branch**

Print and save to `docs/superpowers/specs/2026-06-08-phase-1-frontend-foundation-design.md.completion.md` (a sidecar completion log — does not modify the spec itself):

```bash
git log phase-1/foundation ^main --oneline > docs/superpowers/specs/2026-06-08-phase-1-frontend-foundation-design.md.completion.md
git add docs/superpowers/specs/2026-06-08-phase-1-frontend-foundation-design.md.completion.md
git commit -m "docs: Phase 1 completion log"
```

- [ ] **Step 35.2: Confirm acceptance criteria**

Walk the spec's §9 Acceptance Criteria list (AC-1 through AC-11) and verify each. Note any deviations in the completion log. Phase 1 is complete only when every AC is checked.

---

## Self-review checklist

Before handing the plan to subagent-driven-development or executing-plans, the author verified:

- **Spec coverage:** Every section of the spec maps to at least one task —
  - §2 layout → Task 4 + Tasks 20–26
  - §3 stack → Task 2 + Task 5 + Task 15
  - §4 visual system → Task 3 + Task 15
  - §5 app shell + auth → Tasks 6, 12–14, 16–19, 27
  - §6 backend contract → Tasks 7–10, 18 (integrations), 32 (audit)
  - §7 migration plan → Tasks 1–32 in order
  - §8 testing strategy → Tasks 5, 8–14, 16, 29
  - §9 ACs → Tasks 31 (delete frontend/), 32 (backend audit), 34 (verification)
  - §10 risks → addressed via per-task verification steps
  - §11 Phase 2/3 preview → Task 27 ComingSoon
  - §13 follow-ups → Task 32 audit script

- **Placeholder scan:** No `TBD` / `TODO` / "add appropriate error handling"
  patterns. Every step has either complete code, a precise command, or a list
  of concrete file moves.

- **Type consistency:**
  - `setAccessToken` / `getAccessToken` / `clearAccessToken` used identically
    across `client.ts`, `AuthProvider.tsx`, and all tests.
  - `AuthState` discriminated union (`"loading" | "authenticated" | "anonymous"`)
    consistent in `AuthProvider.tsx`, `guards.test.tsx`, `LoginPage.tsx`.
  - `apiStream(path, { onEvent, onError })` returns `{ abort }`; `apiSocket(path,
    { onMessage, onClose, onError? })` returns `{ close }` — used consistently
    in tests and consumers.
  - `ApiError(status, code, message, details?, requestId?)` shape consistent
    everywhere.
  - `ROUTES` keys consistent between `routes.ts`, `router.tsx`, `TopNav.tsx`,
    `MobileNav.tsx`, `CommandPalette.tsx`.

---

*End of plan.*
