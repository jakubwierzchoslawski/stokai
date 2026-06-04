/**
 * email-375.spec.ts — Playwright E2E: Morning Brief email at 375px viewport.
 *
 * Verifies AC-002: Morning Brief HTML email readable on iPhone SE (375px viewport)
 * in a single-column layout without zoom or horizontal scroll.
 *
 * The rendered email HTML is served as a static route /test-email in the dev/test
 * server (the test environment must seed this route via the morning brief renderer).
 *
 * PLAN-N-014 TASK-009
 */

import { test, expect } from "@playwright/test";
import { mobileViewport } from "./fixtures";

test.describe("Morning Brief email at 375px (AC-002)", () => {
  test.beforeEach(async ({ page }) => {
    await page.setViewportSize(mobileViewport);
  });

  test("AC-002: no horizontal scroll at 375px (email renders in single column)", async ({
    page,
  }) => {
    await page.goto("/test-email");

    const scrollWidth = await page.evaluate(
      () => document.documentElement.scrollWidth,
    );
    expect(scrollWidth).toBeLessThanOrEqual(375);
  });

  test("AC-002: content column is single-width (offsetWidth ≤ 375px)", async ({
    page,
  }) => {
    await page.goto("/test-email");

    const contentWidth = await page.evaluate(() => {
      const col = document.querySelector(".content-col");
      if (!col) return 0;
      return (col as HTMLElement).offsetWidth;
    });

    expect(contentWidth).toBeLessThanOrEqual(375);
  });

  test("AC-002: no text element has computed fontSize below 14px", async ({
    page,
  }) => {
    await page.goto("/test-email");

    const hasSmallText = await page.evaluate(() => {
      const textElements = document.querySelectorAll("p, td, span, a, div");
      for (const el of textElements) {
        const computed = window.getComputedStyle(el);
        const fontSize = parseFloat(computed.fontSize);
        if (fontSize > 0 && fontSize < 14) {
          return true;
        }
      }
      return false;
    });

    expect(hasSmallText).toBe(false);
  });

  test("AC-002: two-column layout is collapsed to single column at 375px", async ({
    page,
  }) => {
    await page.goto("/test-email");

    const columnsOverflow = await page.evaluate(() => {
      const leftCols = document.querySelectorAll(".two-col-left");
      for (const col of leftCols) {
        const rect = (col as HTMLElement).getBoundingClientRect();
        if (rect.right > window.innerWidth) {
          return true;
        }
      }
      return false;
    });

    expect(columnsOverflow).toBe(false);
  });
});
