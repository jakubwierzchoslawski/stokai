---
plan_id: PLAN-N-014
slug: responsive-design
title: Responsive Design
linked_requirement: REQ-N-014
type: non-functional
status: ready
blocked_reason:
complexity: M
tdd_required: true
linked_nfrs: []
dependencies:
  - { id: PLAN-F-019, reason: "Intelligence Map is the desktop-first surface; its layout containers, MapLibre canvas sizing, and side-panel collapse behaviour are defined there and extended here" }
  - { id: PLAN-F-025, reason: "Alerts Center is the primary mobile-first surface; its list component receives touch-target and no-scroll constraints enforced here" }
executed_at:
reviewed_at:
review_id:
created_at: 2026-06-03T00:00:00Z
updated_at: 2026-06-03T00:00:00Z
---

# PLAN-N-014 — Responsive Design

## Linked Requirement
**REQ-N-014** — Responsive Design
Status: approved | Jira:

## Objective

Enforce two coexisting responsive layout strategies across the React 18 + TypeScript
frontend. Desktop-first surfaces (Intelligence Map and Admin Panel) must be fully functional
at a primary breakpoint of 1280px, with graceful panel collapsing at 768–1279px and drawer
collapse below 768px. Mobile-first surfaces (Alerts Center, Briefs Reader, Morning Brief
HTML email) must be fully functional at 375px portrait with single-column layout, 0
horizontal scroll, and touch targets of at least 44px height. A shared Tailwind CSS
breakpoint configuration (`sm=375px`, `md=768px`, `lg=1280px`, `xl=1440px`) serves both
strategies from a single build. Playwright viewport tests verify each breakpoint mechanically
against the four acceptance criteria.

## Architecture Context

This plan operates entirely within **Layer 6 — Presentation** (ARCHITECTURE.md §11) and
touches the email dispatch output of **Layer 5 — Serving** (ARCHITECTURE.md §14 — SendGrid).

**Frontend stack (ARCHITECTURE.md §11, §13):** React 18 + TypeScript, Tailwind CSS for
responsive utility classes, shadcn/ui components (responsive by default). The Tailwind
config defines project breakpoints; all responsive modifiers (`sm:`, `md:`, `lg:`, `xl:`)
derive from it. There is no separate CSS-in-JS layer — layout is utility-class-driven.

**Two layout strategies in one app:**

- `desktop-first` strategy applies to surfaces under `src/features/intelligence-map/` and
  `src/features/admin/`. Base styles target `lg` (1280px). Narrower viewports use `md:`
  modifiers for panel collapsing and a `Drawer` component at `< md` for side panels.
- `mobile-first` strategy applies to surfaces under `src/features/alerts/` (Alerts Center
  pages) and `src/features/briefs-reader/` (Reports/Briefs). Base styles target the
  smallest supported width (375px). Wider viewports add `md:` and `lg:` modifiers only for
  visual enhancement.

**Email template (ARCHITECTURE.md §14 — SendGrid, §7.5 Workflow 1):** Morning Brief HTML
emails use inline CSS only (no external stylesheets; email client restriction). The
responsive email template is rendered server-side by the Morning Brief workflow and sent via
SendGrid. It must collapse to a single-column layout at 375px using a `max-width` wrapper
and media query inline `<style>` block (supported by modern mobile email clients and Apple
Mail's rendering engine used by iPhone SE).

**Testing (ARCHITECTURE.md implicit — Playwright):** `page.setViewportSize(...)` viewport
simulation is the verification mechanism for all breakpoint assertions. Tests run in CI with
headless Chromium at the four canonical widths: 375px, 768px, 1280px, 1440px.

**Dependency surfaces:**
- PLAN-F-019 provides `<IntelligenceMap />` and its `<FilterPanel>` / side panel components.
  This plan adds responsive modifiers to those components; it does not restructure their
  data flow.
- PLAN-F-025 provides `<AlertsListPanel />`, `<AlertListRow />`, and `<AlertRuleCard />`.
  This plan enforces `min-h-[44px]`, single-column stacking, and overflow constraints on
  those components; it does not change their data contracts.

## Component Design

### New Components

```
src/
  features/
    shared/
      layout/
        Drawer.tsx                  — slide-in drawer for side panels at < md viewport
        Drawer.test.tsx
        ResponsiveLayout.tsx        — context-aware wrapper: applies desktop-first or
                                      mobile-first layout strategy based on a `strategy`
                                      prop; no DOM output of its own (render-prop / slot)
        ResponsiveLayout.test.tsx
      hooks/
        useBreakpoint.ts            — returns current breakpoint name from matchMedia;
                                      reactive to resize events
        useBreakpoint.test.ts

  email/
    templates/
      morning-brief-email.html      — responsive HTML email template with inline CSS;
                                      single-column layout; media query for 375px
      morning-brief-email.test.html — snapshot fixture for regression (not executed; read
                                      by the snapshot test)

tests/
  e2e/
    responsive/
      alerts-center-375.spec.ts     — Playwright: Alerts Center at 375px
      intelligence-map-1280.spec.ts — Playwright: Intelligence Map at 1280px
      admin-panel-1280.spec.ts      — Playwright: Admin Panel at 1280px
      email-375.spec.ts             — Playwright: Morning Brief email at 375px (static
                                      HTML file opened in browser via file:// or local
                                      dev server route)
```

### Modified Components

| File | Change | Reason |
|------|--------|--------|
| `src/app/tailwind.config.ts` (or `tailwind.config.js`) | Set `theme.screens` to `{ sm: '375px', md: '768px', lg: '1280px', xl: '1440px' }` | Canonical breakpoints for both layout strategies (ARCHITECTURE.md §11) |
| `src/features/intelligence-map/IntelligenceMap.tsx` | Add `md:` panel-collapse modifiers; wrap side panel in `<Drawer>` at `< md`; ensure MapLibre canvas container uses `min-w-0 flex-1` so it does not overflow its flex parent at any breakpoint | AC-003: map functional at 1280px; panels collapse at 768px; drawer at mobile |
| `src/features/intelligence-map/components/FilterPanel.tsx` | Conditionally render inline or inside `<Drawer>` based on breakpoint; at `md` and above, FilterPanel is a sidebar; below `md`, it is triggered by a floating button | AC-003: map controls remain accessible |
| `src/features/alerts/components/AlertListRow.tsx` | Add `min-h-[44px]` and `items-center` to each interactive row container; ensure column layout does not produce horizontal overflow | AC-001: touch targets ≥44px, no horizontal scroll |
| `src/features/alerts/components/AlertRuleCard.tsx` | Add `min-h-[44px]` to toggle and button controls; ensure card layout is single-column at 375px | AC-001: touch targets on rule enable/delete buttons |
| `src/features/alerts/pages/AlertsCenterPage.tsx` | Enforce `overflow-x-hidden` on the page root and `max-w-full` on all direct children; verify tab bar buttons meet `min-h-[44px]` | AC-001: no horizontal scroll at 375px |
| `src/features/briefs-reader/BriefsReaderPage.tsx` (or equivalent) | Apply single-column reading layout at 375px: `max-w-full`, `break-words`, `overflow-x-hidden`, no fixed-width tables; at `lg:` widen to reading-optimised width | AC-002: briefs readable on mobile without horizontal scroll |
| `src/alerts/services/morning_brief_renderer.py` (or equivalent) | Replace multi-column HTML email layout with the responsive inline-CSS template from `email/templates/morning-brief-email.html`; ensure Jinja2 (or equivalent) renders it with tenant + report data | AC-002: Morning Brief email readable on iPhone SE |

### Interfaces and Contracts

```typescript
// src/features/shared/layout/Drawer.tsx
export interface DrawerProps {
  open: boolean;
  onClose: () => void;
  side?: "left" | "right";        // default: "left"
  children: React.ReactNode;
}
export function Drawer(props: DrawerProps): JSX.Element;

// src/features/shared/layout/ResponsiveLayout.tsx
export type LayoutStrategy = "desktop-first" | "mobile-first";
export interface ResponsiveLayoutProps {
  strategy: LayoutStrategy;
  children: React.ReactNode;
}
// Provides LayoutStrategy via React context; no wrapper div emitted.
export function ResponsiveLayout(props: ResponsiveLayoutProps): JSX.Element;
export function useLayoutStrategy(): LayoutStrategy;

// src/features/shared/hooks/useBreakpoint.ts
export type Breakpoint = "sm" | "md" | "lg" | "xl";
// Returns the current active breakpoint based on matchMedia queries.
// "sm"  = viewport width < 768px
// "md"  = 768px ≤ width < 1280px
// "lg"  = 1280px ≤ width < 1440px
// "xl"  = width ≥ 1440px
export function useBreakpoint(): Breakpoint;
```

## Implementation Tasks

### TASK-001: Tailwind breakpoint configuration · S/no-TDD · src/app/tailwind.config.ts

Set `theme.screens` to the canonical four breakpoints:
```
sm: '375px'
md: '768px'
lg: '1280px'
xl: '1440px'
```
Remove any default Tailwind screens that differ from this set (Tailwind defaults include
`sm: 640px` which conflicts with the 375px mobile-first requirement). Export the config so
TypeScript consumers can import the screen values as constants.

This change has no runtime logic and no test. Verify manually in the dev server that
`sm:` modifiers activate at 375px and `lg:` at 1280px.

**AC covered**: enables all ACs (breakpoint foundation for all responsive utility classes)

---

### TASK-002: `useBreakpoint` hook · M/TDD · src/features/shared/hooks/useBreakpoint.ts, src/features/shared/hooks/useBreakpoint.test.ts

Implement `useBreakpoint(): Breakpoint` using `window.matchMedia`. Register change listeners
for the three threshold media queries (`(min-width: 768px)`, `(min-width: 1280px)`,
`(min-width: 1440px)`) and derive the current breakpoint from their combined match state.
Return a stable `Breakpoint` string that updates on every viewport resize crossing a
threshold. Clean up all listeners on unmount.

The hook must not throw in SSR environments (guard with `typeof window !== "undefined"`).

**Tests to write first (TDD):**
- Mock `matchMedia` returning no matches → `useBreakpoint()` returns `"sm"`
- Mock `matchMedia` matching `(min-width: 768px)` only → returns `"md"`
- Mock `matchMedia` matching `(min-width: 768px)` and `(min-width: 1280px)` → returns `"lg"`
- Mock `matchMedia` matching all three queries → returns `"xl"`
- Simulate a resize event crossing the `md` threshold → hook re-renders with `"md"` (use `act` + fake matchMedia listener dispatch)
- Unmounting the hook → all three `removeEventListener` calls are made (spy on `removeEventListener`)

**AC covered**: enables TASK-003 (Drawer), TASK-004 (IntelligenceMap responsive), AC-001, AC-003

---

### TASK-003: Drawer component · M/TDD · src/features/shared/layout/Drawer.tsx, src/features/shared/layout/Drawer.test.tsx

Implement `<Drawer open onClose side children>`. The drawer is a `fixed` overlay panel that
slides in from `side` (default `"left"`) using a CSS `translate-x` transition. When
`open=false`, the panel is translated fully off-screen and `aria-hidden="true"` is set.
When `open=true`, the panel slides in and keyboard focus is trapped inside using the
`focus-trap-react` library (or equivalent). Pressing Escape calls `onClose`. A semi-opaque
backdrop behind the panel calls `onClose` on click. The panel itself has a `min-w-[280px]`
and `max-w-[90vw]` so it is usable at 375px without consuming the full viewport.

**Tests to write first (TDD):**
- `<Drawer open={false} onClose={...}>` → panel element has `aria-hidden="true"` and transform class indicating off-screen
- `<Drawer open={true} onClose={fn}>` → panel element is visible (`aria-hidden` absent or `false`)
- `open=true` → pressing Escape calls `onClose` once
- `open=true` → clicking the backdrop calls `onClose` once
- `open=true` → clicking inside the panel content does not call `onClose`
- `open` transitions from `true` to `false` → `aria-hidden` becomes `"true"` (controlled re-render test)

**AC covered**: AC-003 (side panels collapse to drawer on mobile for Intelligence Map)

---

### TASK-004: `ResponsiveLayout` context provider · S/no-TDD · src/features/shared/layout/ResponsiveLayout.tsx

Implement `<ResponsiveLayout strategy="desktop-first" | "mobile-first">` as a thin React
context provider. No DOM wrapper emitted (use a `Fragment`). Export `useLayoutStrategy()`
for consumers to read the active strategy. Wrap the Intelligence Map route subtree with
`strategy="desktop-first"` and the Alerts / Briefs Reader subtrees with
`strategy="mobile-first"` in `src/app/router.tsx`.

**AC covered**: enables TASK-005 and TASK-006 (conditional rendering based on strategy)

---

### TASK-005: Intelligence Map responsive layout · M/TDD · src/features/intelligence-map/IntelligenceMap.tsx, src/features/intelligence-map/components/FilterPanel.tsx, src/features/intelligence-map/IntelligenceMap.test.tsx

Modify `<IntelligenceMap />` for desktop-first responsive behaviour:

1. At `lg` (≥1280px): map canvas + right side-panel in a flex row. Side panel has a fixed
   `w-[360px]` and the map canvas fills remaining width with `min-w-0 flex-1 h-full`.
2. At `md` (768–1279px): side panel collapses to `w-[280px]` (narrower, still visible).
   Map canvas still functional. `<FilterPanel>` is rendered as a sidebar.
3. Below `md` (<768px): side panel is hidden from the flex row and instead rendered inside
   `<Drawer side="right">`. A floating toggle button `fixed bottom-4 right-4` opens the
   drawer. `<FilterPanel>` moves inside the drawer alongside the side panel.

Add `overflow-hidden` to the outermost map container to prevent any child from causing
horizontal scroll. The MapLibre canvas must never have an explicit pixel width set; it must
size to its flex container via `width: 100%; height: 100%` (MapLibre default behaviour
when the container is sized by CSS).

**Tests to write first (TDD):**
- Render `<IntelligenceMap />` in a 1280px-wide container (mocked) → side panel rendered as sibling in flex row (not inside a Drawer); `getByRole("complementary")` or test-id is directly in the document, not nested inside a drawer portal
- Render in a 767px-wide container → side panel is NOT in the flex row; the floating drawer toggle button is present in the DOM
- Floating drawer toggle clicked → `<Drawer open={true}>` is rendered with the side panel content
- Closing the drawer → `<Drawer open={false}>` and panel reverts to hidden state
- Map container element has no explicit `width` attribute that could cause overflow (assert via computed style)

**AC covered**: AC-003 (Intelligence Map fully functional at 1280px; panels collapse appropriately)

---

### TASK-006: Admin Panel responsive layout · M/TDD · src/features/admin/AdminLayout.tsx (or equivalent), tests/e2e/responsive/admin-panel-1280.spec.ts

Audit the Admin Panel layout (route `/admin`) for the same desktop-first breakpoints:

1. At `lg` (≥1280px): left navigation rail + main content in a flex row. All four admin
   sections (Source Management, AI Audit Console, System Operations, User Management)
   visible and scrollable within `main`. No horizontal scroll on the `<main>` element.
2. At `md` (768–1279px): navigation rail collapses to icon-only mode with tooltips.
3. Below `md`: navigation rail hidden; a top `<header>` hamburger menu opens a `<Drawer>`.

Apply `max-w-full overflow-x-hidden` to all data tables within admin sections. Tables with
many columns must become horizontally scrollable within their own container (`overflow-x-auto`
on a wrapping `<div>`) rather than causing page-level horizontal scroll.

**Tests to write first (TDD):**
- Render `<AdminLayout>` in a 1280px container → left rail and main content are both visible in a flex row; `getByRole("navigation")` is in the document (not in a drawer)
- Render in a 767px container → navigation is NOT in a flex row; hamburger button is present
- Hamburger clicked → `<Drawer>` with nav content opens
- A data table rendered inside a 1280px admin layout → parent page `<body>` does not have horizontal scrollbar (assert `scrollWidth <= clientWidth` via Playwright or jsdom)

Write `tests/e2e/responsive/admin-panel-1280.spec.ts` using Playwright:
- `page.setViewportSize({ width: 1280, height: 800 })` → navigate to `/admin`
- Assert all four admin section headings are visible without horizontal scroll
- Assert `document.documentElement.scrollWidth <= document.documentElement.clientWidth`

**AC covered**: AC-004 (Admin Panel fully functional at 1280px without horizontal scroll)

---

### TASK-007: Alerts Center mobile-first layout · M/TDD · src/features/alerts/pages/AlertsCenterPage.tsx, src/features/alerts/components/AlertListRow.tsx, src/features/alerts/components/AlertRuleCard.tsx, tests/e2e/responsive/alerts-center-375.spec.ts

Enforce mobile-first constraints on all Alerts Center components:

**`AlertsCenterPage.tsx`:**
- Root container: `overflow-x-hidden w-full`. No fixed-width child containers. Tab buttons:
  `min-h-[44px] px-4`.

**`AlertListRow.tsx`:**
- Row outer element: `min-h-[44px] flex items-center flex-wrap`. All columns use
  `flex-shrink` so they wrap rather than overflow. The event-title link truncation at 60
  chars must not produce horizontal scroll (use `max-w-full overflow-hidden text-ellipsis
  whitespace-nowrap` scoped inside the link container, not on the row).
- Action signal badge: `inline-flex items-center min-h-[44px]`.

**`AlertRuleCard.tsx`:**
- Enable/disable toggle: `min-h-[44px]`. Edit and Delete buttons: `min-h-[44px]`. Card
  container: `max-w-full`. Any metadata that would overflow at 375px stacks vertically
  (`flex-col` at base, `sm:flex-row` optional).

Also verify `AlertFilterBar.tsx`: filter dropdowns use `w-full` at base (full width on
mobile) and `sm:w-auto` for horizontal layout at wider breakpoints.

**Tests to write first (TDD):**
- Render `<AlertListRow item={mockItem} />` in a 375px jsdom container → row element's computed `minHeight` is at least 44px (assert via `getBoundingClientRect()` mock or inline style assertion on `min-h-[44px]` class presence)
- Render `<AlertRuleCard rule={mockRule} />` in 375px container → toggle button has `min-h-[44px]` class
- Render `<AlertsCenterPage />` in 375px viewport → no child element has a computed width exceeding 375px (shallow DOM check: assert no inline `width: NNNpx` where NNN > 375 exists)
- `AlertFilterBar` at 375px → dropdowns rendered as `w-full` block elements (class assertion)

Write `tests/e2e/responsive/alerts-center-375.spec.ts` using Playwright:
- `page.setViewportSize({ width: 375, height: 812 })`
- Navigate to `/alerts`
- Assert `document.documentElement.scrollWidth <= 375` (no horizontal scroll)
- Assert all alert row elements have `offsetHeight >= 44` (touch target)
- Assert all interactive elements (tab buttons, rule toggles) have `offsetHeight >= 44`

**AC covered**: AC-001 (Alerts Center at 375px: no horizontal scroll, touch targets ≥44px)

---

### TASK-008: Briefs Reader mobile-first layout · M/TDD · src/features/briefs-reader/BriefsReaderPage.tsx, tests/e2e/responsive/briefs-reader-375.spec.ts

Apply mobile-first reading layout to the Briefs Reader (route `/briefs` or `/reports`):

1. All prose containers: `max-w-full overflow-x-hidden break-words`. Long URLs or code
   snippets: `break-all`. No fixed-width prose container that would overflow 375px.
2. Any embedded images: `max-w-full h-auto` (responsive images).
3. Any data tables within a brief: wrapped in `<div class="overflow-x-auto max-w-full">` so
   they scroll horizontally within their container, not the page. Page-level horizontal
   scroll must be 0.
4. Typography scale: base font size `text-base` (16px), line height `leading-relaxed`; at
   `lg:` optionally increase to `text-lg`. Font size must never be below 16px on mobile to
   avoid iOS auto-zoom on input focus (no inputs in the reader, but enforce as a convention).
5. Report title and metadata header: single column stacking at base; `md:flex-row` optional.

**Tests to write first (TDD):**
- Render `<BriefsReaderPage report={longMockReport} />` → root container has `overflow-x-hidden` class
- A mock report containing a wide data table → the table's parent wrapper has `overflow-x-auto` and `max-w-full`; the `<body>` scroll width does not exceed container width
- A mock report with a long unbroken URL string → the URL element has `break-all` class

Write `tests/e2e/responsive/briefs-reader-375.spec.ts` using Playwright:
- `page.setViewportSize({ width: 375, height: 812 })`
- Navigate to a brief detail route with a seeded test brief
- Assert `document.documentElement.scrollWidth <= 375`
- Assert no text is clipped horizontally (approximated via `overflow: hidden` computed style check on the prose container)

**AC covered**: AC-002 (partial — Briefs Reader web surface; email template covered by TASK-009)

---

### TASK-009: Responsive Morning Brief email template · M/TDD · src/email/templates/morning-brief-email.html, src/alerts/services/morning_brief_renderer.py, tests/e2e/responsive/email-375.spec.ts

Create `src/email/templates/morning-brief-email.html` as a self-contained HTML email
template with inline CSS only (no external stylesheets — email client restriction per
ARCHITECTURE.md §14). Template requirements:

1. Outer container: `<table width="100%" cellpadding="0" cellspacing="0">` pattern (email
   safe layout; no CSS flexbox/grid — not supported in Outlook).
2. Inner content column: `max-width: 600px; width: 100%; margin: 0 auto;` so it centres on
   desktop email clients but fills the full width on mobile.
3. Inline `<style>` block in `<head>` with a single media query:
   ```css
   @media only screen and (max-width: 600px) {
     .content-col { width: 100% !important; padding: 16px !important; }
     .two-col-left, .two-col-right { display: block !important; width: 100% !important; }
   }
   ```
   This collapses any two-column layout to single-column at ≤600px (covers the 375px iPhone
   SE viewport).
4. Font sizes: minimum `14px` inline for body copy; `18px` for section headings.
5. All links: `display: inline-block; padding: 8px 16px;` (tappable links).
6. Images (if any): `max-width: 100%; height: auto;`.

Modify `morning_brief_renderer.py` (or the Morning Brief workflow's email formatting step)
to load this template via Jinja2 and render it with the report data dict. The previous
renderer (assumed to be a hardcoded or non-responsive template) is replaced.

**Tests to write first (TDD):**
- Render the template with a minimal report data dict → the rendered HTML contains `@media only screen and (max-width: 600px)` in the `<style>` block (string assertion)
- Render the template → HTML does not contain any `<link rel="stylesheet">` tag (no external CSS — email client constraint)
- Render the template with a report that has 3 recommendations → the rendered HTML contains all 3 recommendation blocks
- `morning_brief_renderer.render(report_data)` returns a string containing `<!DOCTYPE html>` (valid HTML document)

Write `tests/e2e/responsive/email-375.spec.ts` using Playwright:
- Serve the rendered HTML template as a static route (`/test-email`) in the dev/test server
- `page.setViewportSize({ width: 375, height: 812 })`
- Navigate to `/test-email`
- Assert `document.documentElement.scrollWidth <= 375` (no horizontal scroll)
- Assert the content column is single-width (computed `offsetWidth <= 375`)
- Assert no text element has a computed `fontSize` below `14px` (font readability)

**AC covered**: AC-002 (Morning Brief email readable on iPhone SE at 375px)

---

### TASK-010: Playwright E2E responsive test suite · M/TDD · tests/e2e/responsive/alerts-center-375.spec.ts, tests/e2e/responsive/intelligence-map-1280.spec.ts, tests/e2e/responsive/admin-panel-1280.spec.ts, tests/e2e/responsive/email-375.spec.ts

Consolidate and finalise all four Playwright viewport test files. Each file is authored per
its TASK (TASK-006, TASK-007, TASK-008, TASK-009 each write their own Playwright spec).
This task adds the final `intelligence-map-1280.spec.ts` and ensures a shared `viewport`
fixture is established so all specs import `{ test, expect }` from a shared helper rather
than duplicating `page.setViewportSize` calls.

`tests/e2e/responsive/fixtures.ts`:
- `mobileViewport`: `{ width: 375, height: 812 }` (iPhone SE)
- `tabletViewport`: `{ width: 768, height: 1024 }`
- `desktopViewport`: `{ width: 1280, height: 800 }`
- `wideViewport`: `{ width: 1440, height: 900 }`

`tests/e2e/responsive/intelligence-map-1280.spec.ts`:
- `page.setViewportSize(desktopViewport)`
- Navigate to `/` (Intelligence Map)
- Assert the map canvas element is visible and has `offsetWidth >= 800` (takes up most of the 1280px viewport)
- Assert the side panel is visible as a sibling (not inside a drawer); assert `offsetWidth >= 280`
- Assert `document.documentElement.scrollWidth <= 1280`
- Assert the `<FilterPanel>` is visible in the sidebar (not in a drawer trigger)
- At `tabletViewport`: navigate to `/`, assert map canvas still visible, assert no horizontal scroll

**Tests to write first (TDD):**
(Each bullet above is a discrete Playwright test case; all are TDD — the assertions are
written before the layout changes in TASK-005 are verified.)

**AC covered**: AC-001, AC-002, AC-003, AC-004

---

## Acceptance Criteria Coverage

- AC-001: Alerts Center rendered on 375px-wide viewport → all alert items readable without horizontal scroll; all tap targets are at least 44px in height → TASK-007, TASK-010
- AC-002: Morning Brief HTML email opened on iPhone SE (375px viewport) → full content readable in single-column layout without zoom or horizontal scroll → TASK-008, TASK-009, TASK-010
- AC-003: Intelligence Map rendered on 1280px-wide desktop viewport → full map, sidebar, and control panels simultaneously visible and functional → TASK-005, TASK-010
- AC-004: Admin panel rendered on 1280px-wide viewport → all data source management, AI audit console, and system operations panels fully functional without horizontal scroll → TASK-006, TASK-010

## Acceptance Notes

AC-002 covers both the Briefs Reader web surface (TASK-008) and the Morning Brief HTML
email (TASK-009). The email is validated via a Playwright test that loads the rendered HTML
as a local static route — this is the closest practical approximation to an email client
viewport test without a real device. The iPhone SE media query activation depends on the
`<style>` block in the HTML head being processed by the browser rendering engine (supported
by Chromium). Actual email client rendering (Apple Mail, Gmail mobile) requires manual
spot-check on first send; that verification is not automated.

The two-column collapse in the email template (TASK-009) targets `max-width: 600px` in the
CSS media query rather than exactly 375px. This is intentional: 600px is the standard email
single-column collapse threshold; 375px viewports trigger it. Setting the threshold to
exactly 375px would prevent correct rendering on larger phone screens (e.g. 390px iPhone
14).

## Risks and Notes

- **Tailwind `sm` breakpoint override (TASK-001):** Tailwind's default `sm` is 640px.
  Changing it to 375px means any existing code using `sm:` modifiers targets a narrower
  viewport than expected. Grep all existing `sm:` utility usages before applying TASK-001
  and audit for unintended side effects. Because all dependent functional plans (PLAN-F-019,
  PLAN-F-025) are in `ready` status and not yet implemented, this risk is low — but must be
  re-evaluated if any `sm:` classes are already present in the codebase.

- **MapLibre canvas sizing at narrow viewports (TASK-005):** MapLibre GL JS measures its
  container's `clientWidth` and `clientHeight` on `resize`. If the container is inside a
  flex child with `min-width: 0` omitted, the canvas can overflow its parent. The fix is
  `min-w-0` on the flex child — a one-class change, but easy to miss. The Playwright
  `scrollWidth` assertion in TASK-010 will catch this if it regresses.

- **Email client CSS support (TASK-009):** Inline `<style>` media queries are supported by
  Apple Mail (iOS), Gmail app (iOS/Android with remote images disabled), and Outlook.com
  web. Outlook Desktop (Windows, Word rendering engine) does not support `@media` queries.
  The fallback for Outlook Desktop is the outer `<table>` with `max-width: 600px` which
  renders as a centred single column regardless — acceptable degradation.

- **Playwright test isolation (TASK-010):** E2E tests require the full app dev server or a
  built static export. For CI, use `playwright.config.ts` with `webServer` pointing to
  `vite preview` or `vite build && vite preview`. Ensure the test brief and test email
  routes are seeded in the test environment; do not rely on production data fixtures.

- **`focus-trap-react` dependency (TASK-003):** If the project does not already use this
  library, add it to `package.json`. Alternative: implement focus trap manually using
  `TreeWalker` and `keydown` listener. Either approach is acceptable; document the choice
  in `Drawer.tsx`.
