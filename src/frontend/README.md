# StokAI Frontend

React 18 SPA — TypeScript · Vite 7 · Tailwind CSS v4 · TanStack Query · React Router v6

## Directory layout

```
src/frontend/
├── app/                   # Bootstrap: router.tsx, providers.tsx, App.tsx
├── layout/                # AppShell, AdminLayout, RequireAuth, OnboardingGate
├── pages/                 # Thin route-level pages; compose features
│   └── admin/             # HIL, Sources, AI-Audit, System pages
├── features/              # Domain modules — components, hooks, API, tests collocated
│   ├── intelligence-map/  # Globe map (MapLibre GL + Supercluster)
│   ├── qa/                # Q&A chat
│   ├── screener/          # Stock screener
│   ├── scoring/           # Scoring display
│   ├── indicator-builder/ # Custom indicator builder
│   ├── alerts/            # Alert management
│   ├── company-detail/    # Company detail panel
│   └── progressive-disclosure/ # Event side-panel & sparklines
├── ui/                    # Design-system primitives (shadcn/ui + custom tokens)
├── lib/                   # Shared utils, types, constants
│   └── api/               # Typed API client — only place fetch is called
└── hooks/                 # App-wide React hooks
```

## Dev server

```bash
npm run dev        # http://localhost:5173 — proxies /api to http://localhost:8000
npm run build      # Output → dist/frontend/
npm test           # Vitest
npx eslint src/frontend   # Lint (eslint.config.mjs)
```

## Conventions

- **API calls**: use `api()` from `lib/api/client.ts` — never call `fetch('/api/...')` directly
- **Styling**: Tailwind CSS utility classes only — no inline `style` props
- **Tests**: Vitest + `@testing-library/react`; test files in `__tests__/` next to their feature
- **Path alias**: `@/` → `src/frontend/` (configured in `tsconfig.json` and `vite.config.ts`)
- **Design tokens**: OKLCH colour palette defined in `src/frontend/styles/tokens.css` via `@theme {}`
