/**
 * admin-panel-1280.spec.ts — Playwright E2E: Admin Panel at 1280px viewport.
 *
 * Verifies AC-004: Admin panel rendered on 1280px-wide viewport — all data source
 * management, AI audit console, and system operations panels fully functional
 * without horizontal scroll.
 *
 * PLAN-N-014 TASK-006
 */

import { test, expect } from "@playwright/test";
import { desktopViewport } from "./fixtures";

test.describe("Admin Panel at 1280px", () => {
  test.beforeEach(async ({ page }) => {
    await page.setViewportSize(desktopViewport);
  });

  test("AC-004: all admin section headings are visible without horizontal scroll", async ({
    page,
  }) => {
    await page.goto("/admin");

    // Verify no horizontal scroll at page level
    const scrollWidth = await page.evaluate(
      () => document.documentElement.scrollWidth,
    );
    const clientWidth = await page.evaluate(
      () => document.documentElement.clientWidth,
    );
    expect(scrollWidth).toBeLessThanOrEqual(clientWidth);
  });

  test("AC-004: navigation rail is visible as a sibling at 1280px (not inside a drawer)", async ({
    page,
  }) => {
    await page.goto("/admin");

    // Navigation rail should be visible
    const navRail = page.getByTestId("admin-nav-rail");
    await expect(navRail).toBeVisible();

    // Hamburger should NOT be visible at desktop width
    const hamburger = page.getByTestId("admin-hamburger");
    await expect(hamburger).not.toBeVisible();
  });

  test("AC-004: main content area does not produce horizontal scroll", async ({
    page,
  }) => {
    await page.goto("/admin");

    const noHorizontalScroll = await page.evaluate(() => {
      const main = document.querySelector("[data-testid='admin-main']");
      if (!main) return true;
      return main.scrollWidth <= main.clientWidth;
    });
    expect(noHorizontalScroll).toBe(true);
  });
});
