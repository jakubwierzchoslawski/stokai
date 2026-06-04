/**
 * fixtures.ts — Shared viewport size constants for Playwright responsive tests.
 *
 * All four E2E responsive specs import from this file to avoid duplicating
 * page.setViewportSize calls. Maps directly to the Tailwind canonical breakpoints
 * from tailwind.config.ts (PLAN-N-014 TASK-001).
 *
 * PLAN-N-014 TASK-010
 */

import type { ViewportSize } from "@playwright/test";

/** iPhone SE portrait — 375px (Tailwind sm breakpoint). Primary mobile test viewport. */
export const mobileViewport: ViewportSize = { width: 375, height: 812 };

/** iPad portrait — 768px (Tailwind md breakpoint). Tablet collapse test viewport. */
export const tabletViewport: ViewportSize = { width: 768, height: 1024 };

/** Standard desktop — 1280px (Tailwind lg breakpoint). Primary desktop test viewport. */
export const desktopViewport: ViewportSize = { width: 1280, height: 800 };

/** Wide desktop — 1440px (Tailwind xl breakpoint). Wide desktop test viewport. */
export const wideViewport: ViewportSize = { width: 1440, height: 900 };
