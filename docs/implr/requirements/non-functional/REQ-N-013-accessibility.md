---
req_id: REQ-N-013
slug: n-accessibility
title: Accessibility
type: non-functional
nfr_category: Usability
status: draft
complexity: M
tdd_required: true
source_docs:
  - ui-design-digest.md
dependencies:
  - { id: "", reason: "intelligence-map: Colorblind-safe palette applied to map pulse categories" }
superseded_by:
jira:
  id:
  issue_type: Story
  epic_link:
  priority: Medium
  labels: [frontend, accessibility, wcag]
  story_points:
  components: [frontend, accessibility]
created_at: 2026-06-02T00:00:00Z
updated_at: 2026-06-02T00:00:00Z
---

# REQ-N-??? — Accessibility

## Domain Context
The Intelligence Map uses color as the primary event-category encoding. Colorblind users must be able to distinguish all six event categories. Admin and report screens must meet WCAG 2.1 AA minimum.

## Summary
The map pulse layer must use a colorblind-safe 6-color palette for event categories. Admin and report screens must meet WCAG 2.1 AA minimum (4.5:1 contrast ratio for text, keyboard navigability, screen reader compatibility for key actions).

## Detailed Description
As specified in ui-design-digest.md business rule 14 and root-synthesis NFR candidates:

**Colorblind-safe palette:** The six event category colors must be distinguishable by users with deuteranopia, protanopia, and tritanopia. Palette selection follows established colorblind-safe guidelines (e.g. Wong palette or equivalent). Colors are fixed constants (not user-configurable in MVP).

**WCAG 2.1 AA for admin and report screens:**
- Minimum contrast ratio 4.5:1 for normal text; 3:1 for large text
- All interactive controls keyboard-accessible
- Screen reader compatibility for key actions (login, navigation, report reading)
- Focus indicators visible on all interactive elements

**Map interface (best effort):** The map interface has inherent accessibility challenges (WebGL, geospatial). WCAG AA is targeted for admin and report screens; the map targets colorblind-safe palette as the primary accommodation. A future phase will add pattern/shape encoding as supplementary category differentiation.

## Desired Outcome
Users with color vision deficiencies can distinguish event categories on the map, and users relying on assistive technology can navigate admin and report screens without functional barriers.

## Acceptance Criteria
- [ ] AC-001: Given the 6-color event category palette, a colorblind simulation tool (e.g. Coblis or Figma colorblind plugin) confirms all 6 colors are distinguishable under deuteranopia, protanopia, and tritanopia simulations.
- [ ] AC-002: Given the admin panel screens, automated accessibility testing (e.g. axe-core) reports 0 critical and 0 serious WCAG 2.1 AA violations.
- [ ] AC-003: Given a user navigates the admin panel using only a keyboard (Tab, Enter, Space, Arrow keys), all interactive controls (buttons, toggles, dropdowns) are reachable and operable.
- [ ] AC-004: Given a report is read with a screen reader (NVDA or VoiceOver), the confidence level, action signal, and disclaimer (if present) are announced by the screen reader.

## Out of Scope
- WCAG AAA compliance
- Full screen reader compatibility for the map WebGL layer (acknowledged as a limitation)

## NFR-Specific Fields

### Measurable Target
- Colorblind-safe palette: 6 colors distinguishable under 3 colorblind types (deuteranopia, protanopia, tritanopia)
- Admin + report screens: 0 critical/serious WCAG 2.1 AA violations per axe-core automated scan
- Keyboard navigation: 100% of interactive admin panel controls operable by keyboard

### Verification Method
- Method: Colorblind simulation tool on palette; axe-core automated scan in CI; manual keyboard-only navigation test
- Tool/Process: axe-core (Playwright integration); Coblis or browser colorblind simulator; manual keyboard test
- Frequency: Per release (axe-core in CI); at design review (palette check)
- Owner: QA / Frontend

### Category Rationale
Usability NFR because accessibility is both a legal obligation (WCAG) and a product quality requirement. Color-as-only-differentiator is a known failure mode for colorblind users who represent ~8% of male users.

## Subtasks
- [ ] ST-001: Design and validate colorblind-safe 6-color palette — complexity: S
- [ ] ST-002: Implement axe-core accessibility scan in CI pipeline — complexity: S
- [ ] ST-003: Audit and fix keyboard navigation gaps in admin panel — complexity: M
- [ ] ST-004: Implement screen reader announcements for key report elements — complexity: M

## Source Document References
| Document | Relevant Section | Contribution |
|----------|-----------------|-------------|
| ui-design-digest.md | Business Rule 14; Non-Functional Signals | Colorblind-safe palette mandated for map pulse categories |
