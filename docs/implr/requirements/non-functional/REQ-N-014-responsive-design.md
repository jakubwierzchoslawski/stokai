---
req_id: REQ-N-014
slug: n-responsive-design
title: Responsive Design
type: non-functional
nfr_category: Usability
status: approved
complexity: M
tdd_required: true
source_docs:
  - ui-design-digest.md
dependencies:
  - { id: "", reason: "intelligence-map: Map interface is desktop-first" }
  - { id: "", reason: "alerts-center: Alerts reading is mobile-first" }
superseded_by:
jira:
  id:
  issue_type: Story
  epic_link:
  priority: Medium
  labels: [frontend, responsive, mobile]
  story_points:
  components: [frontend, ux]
created_at: 2026-06-02T00:00:00Z
updated_at: 2026-06-02T00:00:00Z
---

# REQ-N-??? — Responsive Design

## Domain Context
The map decision interface is desktop-first (full-screen map, side panels, data density). Alert reading and Morning Brief reading are mobile-first (linear, single-column, scannable). Two distinct layout strategies for two distinct use cases.

## Summary
The map and admin panel must be desktop-first with full functionality on screens ≥1280px wide. Alert notifications, Alerts Center, and Reports/Briefs reader must be mobile-first with full functionality on screens ≥375px wide (portrait). The two strategies coexist in the same React app.

## Detailed Description
As specified in ui-design-digest.md business rule 6 and root-synthesis NFR candidates:

**Desktop-first surfaces (map decision interface + admin panel):**
- Primary breakpoint: ≥1280px; full feature set
- Tablet (768–1279px): usable with some panel collapsing; map remains functional
- Mobile (<768px): map accessible but side panels collapse to drawer; not the primary use case

**Mobile-first surfaces (alerts, briefs reader):**
- Primary breakpoint: ≥375px (portrait); full feature set
- Single-column linear layout
- Alerts Center: list view optimized for thumb scrolling
- Briefs reader: full report readable on mobile without horizontal scroll
- Alert notification emails: responsive HTML email template

**Shared requirement:**
- No horizontal scroll on any supported breakpoint for its primary surface type
- Touch targets ≥44px on mobile-first surfaces

## Desired Outcome
Users receive alert notifications and read morning briefs comfortably on mobile devices, while the full analytical decision-making interface is optimized for desktop use, without maintaining two separate codebases.

## Acceptance Criteria
- [ ] AC-001: Given the Alerts Center is rendered on a 375px-wide viewport, all alert items are readable without horizontal scroll and all tap targets are at least 44px in height.
- [ ] AC-002: Given a Morning Brief HTML email is opened on an iPhone SE (375px viewport), the full content is readable in a single-column layout without zoom or horizontal scroll.
- [ ] AC-003: Given the Intelligence Map is rendered on a 1280px-wide desktop viewport, the full map, sidebar, and control panels are simultaneously visible and functional.
- [ ] AC-004: Given the admin panel is rendered on a 1280px-wide viewport, all data source management, AI audit console, and system operations panels are fully functional without horizontal scroll.

## Out of Scope
- Native mobile app (web responsive only)
- Progressive Web App (PWA) capabilities (post-MVP)

## NFR-Specific Fields

### Measurable Target
- Mobile-first surfaces: fully functional at 375px width portrait; 0 horizontal scroll; touch targets ≥44px height
- Desktop-first surfaces: fully functional at 1280px width; no feature degradation on primary breakpoint
- Verified breakpoints: 375px, 768px, 1280px, 1440px

### Verification Method
- Method: Playwright viewport tests at defined breakpoints; manual device testing
- Tool/Process: Playwright responsive tests (375px, 768px, 1280px); Chrome DevTools device simulation; real device check on iPhone and Android
- Frequency: Per release
- Owner: QA / Frontend

### Category Rationale
Usability NFR because alerts and briefs are consumed asynchronously on mobile devices while users are away from their desks. A non-functional mobile layout means users miss time-sensitive information.

## Subtasks
- [ ] ST-001: Implement responsive CSS for mobile-first surfaces (alerts, briefs reader) — complexity: M
- [ ] ST-002: Implement responsive email template for Morning Brief HTML email — complexity: M
- [ ] ST-003: Implement desktop-first layout for map and admin panel — complexity: M
- [ ] ST-004: Playwright viewport tests at defined breakpoints — complexity: M

## Source Document References
| Document | Relevant Section | Contribution |
|----------|-----------------|-------------|
| ui-design-digest.md | Business Rule 6; Non-Functional Signals | Desktop-first map decision interface; mobile-first alerts and brief-reading |
