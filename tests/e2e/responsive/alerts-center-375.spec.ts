/**
 * alerts-center-375.spec.ts — Playwright E2E: Alerts Center at 375px viewport.
 *
 * Verifies AC-001: Alerts Center rendered on 375px-wide viewport — all alert
 * items readable without horizontal scroll; all tap targets are at least 44px
 * in height.
 *
 * PLAN-N-014 TASK-007
 */

import { test, expect } from "@playwright/test";
import { mobileViewport } from "./fixtures";

test.describe("Alerts Center at 375px (AC-001)", () => {
  test.beforeEach(async ({ page }) => {
    await page.setViewportSize(mobileViewport);
  });

  test("AC-001: no horizontal scroll at 375px", async ({ page }) => {
    await page.goto("/alerts");

    const scrollWidth = await page.evaluate(
      () => document.documentElement.scrollWidth,
    );
    expect(scrollWidth).toBeLessThanOrEqual(375);
  });

  test("AC-001: all alert row elements have offsetHeight ≥ 44 (touch target)", async ({
    page,
  }) => {
    await page.goto("/alerts");

    const rows = await page.$$("[data-testid='alert-list-row']");
    for (const row of rows) {
      const height = await row.evaluate((el) => (el as HTMLElement).offsetHeight);
      expect(height).toBeGreaterThanOrEqual(44);
    }
  });

  test("AC-001: tab buttons have offsetHeight ≥ 44 (touch target)", async ({
    page,
  }) => {
    await page.goto("/alerts");

    const tabAlerts = page.getByTestId("tab-alerts");
    const tabRules = page.getByTestId("tab-rules");

    const alertsHeight = await tabAlerts.evaluate(
      (el) => (el as HTMLElement).offsetHeight,
    );
    const rulesHeight = await tabRules.evaluate(
      (el) => (el as HTMLElement).offsetHeight,
    );

    expect(alertsHeight).toBeGreaterThanOrEqual(44);
    expect(rulesHeight).toBeGreaterThanOrEqual(44);
  });

  test("AC-001: interactive elements (rule toggles) have offsetHeight ≥ 44", async ({
    page,
  }) => {
    await page.goto("/alerts");

    // Switch to Rules tab
    await page.getByTestId("tab-rules").click();

    const toggles = await page.$$("[data-testid='enabled-toggle']");
    for (const toggle of toggles) {
      const parentLabel = await toggle.evaluateHandle(
        (el) => el.closest("label"),
      );
      if (parentLabel) {
        const height = await (parentLabel as any).evaluate(
          (el: HTMLElement) => el.offsetHeight,
        );
        expect(height).toBeGreaterThanOrEqual(44);
      }
    }
  });
});
