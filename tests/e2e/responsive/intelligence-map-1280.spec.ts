/**
 * intelligence-map-1280.spec.ts — Playwright E2E: Intelligence Map at 1280px viewport.
 *
 * Verifies AC-003: Intelligence Map rendered on 1280px-wide desktop viewport — full
 * map, sidebar, and control panels simultaneously visible and functional.
 *
 * PLAN-N-014 TASK-010
 */

import { test, expect } from "@playwright/test";
import { desktopViewport, tabletViewport } from "./fixtures";

test.describe("Intelligence Map at 1280px (AC-003)", () => {
  test("AC-003: map canvas is visible and fills most of the 1280px viewport", async ({
    page,
  }) => {
    await page.setViewportSize(desktopViewport);
    await page.goto("/");

    const mapCanvas = page.getByTestId("map-container");
    await expect(mapCanvas).toBeVisible();

    const width = await mapCanvas.evaluate(
      (el) => (el as HTMLElement).offsetWidth,
    );
    // Map should take up at least 800px of the 1280px viewport
    // (1280 - 360px side panel = ~920px minimum)
    expect(width).toBeGreaterThanOrEqual(800);
  });

  test("AC-003: side panel is visible as sibling at 1280px (not inside a drawer)", async ({
    page,
  }) => {
    await page.setViewportSize(desktopViewport);
    await page.goto("/");

    // Side panel should be visible directly (not in a closed drawer)
    const sidePanel = page.getByTestId("map-side-panel");
    await expect(sidePanel).toBeVisible();

    // Panel should have meaningful width
    const panelWidth = await sidePanel.evaluate(
      (el) => (el as HTMLElement).offsetWidth,
    );
    expect(panelWidth).toBeGreaterThanOrEqual(280);
  });

  test("AC-003: no horizontal scroll at 1280px", async ({ page }) => {
    await page.setViewportSize(desktopViewport);
    await page.goto("/");

    const scrollWidth = await page.evaluate(
      () => document.documentElement.scrollWidth,
    );
    expect(scrollWidth).toBeLessThanOrEqual(1280);
  });

  test("AC-003: FilterPanel is visible in the sidebar at 1280px (not behind a drawer trigger)", async ({
    page,
  }) => {
    await page.setViewportSize(desktopViewport);
    await page.goto("/");

    // FilterPanel should be directly visible, not behind a drawer
    const filterPanel = page.getByTestId("filter-panel");
    await expect(filterPanel).toBeVisible();
  });

  test("AC-003: drawer toggle button is NOT visible at 1280px (desktop mode)", async ({
    page,
  }) => {
    await page.setViewportSize(desktopViewport);
    await page.goto("/");

    const toggleBtn = page.getByTestId("drawer-toggle-button");
    // At desktop breakpoint, the floating drawer toggle should not be rendered
    await expect(toggleBtn).not.toBeVisible();
  });

  test("map canvas still visible at tablet viewport (768px) with no horizontal scroll", async ({
    page,
  }) => {
    await page.setViewportSize(tabletViewport);
    await page.goto("/");

    const mapCanvas = page.getByTestId("map-container");
    await expect(mapCanvas).toBeVisible();

    const scrollWidth = await page.evaluate(
      () => document.documentElement.scrollWidth,
    );
    expect(scrollWidth).toBeLessThanOrEqual(768);
  });
});
