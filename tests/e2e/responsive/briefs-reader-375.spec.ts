/**
 * briefs-reader-375.spec.ts — Playwright E2E: Briefs Reader at 375px viewport.
 *
 * Verifies AC-002 (web surface): Brief detail page readable at 375px without
 * horizontal scroll.
 *
 * PLAN-N-014 TASK-008
 */

import { test, expect } from "@playwright/test";
import { mobileViewport } from "./fixtures";

test.describe("Briefs Reader at 375px (AC-002)", () => {
  test.beforeEach(async ({ page }) => {
    await page.setViewportSize(mobileViewport);
  });

  test("AC-002: no horizontal scroll on brief detail page at 375px", async ({
    page,
  }) => {
    // Navigate to a brief detail with a seeded test brief
    await page.goto("/briefs/test-brief-1");

    const scrollWidth = await page.evaluate(
      () => document.documentElement.scrollWidth,
    );
    expect(scrollWidth).toBeLessThanOrEqual(375);
  });

  test("AC-002: prose container has overflow-x-hidden (no text clipping)", async ({
    page,
  }) => {
    await page.goto("/briefs/test-brief-1");

    const overflowX = await page.evaluate(() => {
      const container = document.querySelector("[data-testid='brief-body']");
      if (!container) return null;
      return window.getComputedStyle(container).overflowX;
    });

    // The computed overflow-x should prevent horizontal overflow
    expect(["hidden", "clip"]).toContain(overflowX);
  });

  test("AC-002: brief detail article does not overflow 375px viewport width", async ({
    page,
  }) => {
    await page.goto("/briefs/test-brief-1");

    const articleWidth = await page.evaluate(() => {
      const article = document.querySelector("[data-testid='brief-detail']");
      if (!article) return 0;
      return (article as HTMLElement).offsetWidth;
    });

    expect(articleWidth).toBeLessThanOrEqual(375);
  });
});
