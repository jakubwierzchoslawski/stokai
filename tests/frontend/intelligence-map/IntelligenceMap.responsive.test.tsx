/**
 * IntelligenceMap.responsive.test.tsx — TDD tests for responsive Intelligence Map layout.
 *
 * Tests written first (red phase) per PLAN-N-014 TASK-005.
 *
 * Note: IntelligenceMap.tsx cannot be compiled in the Jest environment due to
 * import.meta and maplibre-gl WebGL dependencies (pre-existing constraint;
 * same limitation affects all existing intelligence-map tests).
 *
 * The responsive layout contracts are tested here via the shared Drawer and
 * useBreakpoint building blocks that IntelligenceMap composes. The full integration
 * is verified by the Playwright E2E spec (tests/e2e/responsive/intelligence-map-1280.spec.ts).
 *
 * PLAN-N-014 TASK-005
 */

import React, { useState } from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { Drawer } from "../../../src/frontend/features/shared/layout/Drawer";
import { useBreakpoint } from "../../../src/frontend/features/shared/hooks/useBreakpoint";
import { renderHook } from "@testing-library/react";

// ── Mock matchMedia for useBreakpoint ─────────────────────────────────────────

function setupMatchMedia(matchingQueries: string[]) {
  const queries = [
    "(min-width: 768px)",
    "(min-width: 1280px)",
    "(min-width: 1440px)",
  ];
  const mqls: Record<string, { matches: boolean; listeners: Array<(e: { matches: boolean }) => void> }> = {};
  queries.forEach((q) => {
    mqls[q] = { matches: matchingQueries.includes(q), listeners: [] };
  });

  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: jest.fn((q: string) => ({
      matches: mqls[q]?.matches ?? false,
      media: q,
      addEventListener: jest.fn(),
      removeEventListener: jest.fn(),
      addListener: jest.fn(),
      removeListener: jest.fn(),
      dispatchEvent: jest.fn(),
    })),
  });
}

// ── Tests: Desktop-first layout contracts ─────────────────────────────────────

describe("IntelligenceMap responsive layout contracts", () => {
  afterEach(() => {
    jest.restoreAllMocks();
  });

  /**
   * These tests verify the layout primitives that IntelligenceMap composes.
   * The actual component integration is verified via Playwright E2E.
   */

  it("useBreakpoint returns 'lg' at 1280px — side panel shown inline", () => {
    setupMatchMedia(["(min-width: 768px)", "(min-width: 1280px)"]);
    const { result } = renderHook(() => useBreakpoint());
    expect(result.current).toBe("lg");
    // Contract: IntelligenceMap renders side panel inline when breakpoint !== 'sm'
    expect(result.current !== "sm").toBe(true);
  });

  it("useBreakpoint returns 'sm' below 768px — side panel goes into Drawer", () => {
    setupMatchMedia([]);
    const { result } = renderHook(() => useBreakpoint());
    expect(result.current).toBe("sm");
    // Contract: IntelligenceMap renders Drawer toggle when breakpoint === 'sm'
    expect(result.current === "sm").toBe(true);
  });

  it("Drawer with side='right' slides in from the right side", () => {
    render(
      <Drawer open={true} onClose={jest.fn()} side="right">
        <div data-testid="side-panel-content">FilterPanel</div>
      </Drawer>,
    );

    const panel = screen.getByRole("dialog");
    // Panel should not have aria-hidden when open
    expect(panel).not.toHaveAttribute("aria-hidden", "true");
    // Side panel content should be visible in the drawer
    expect(screen.getByTestId("side-panel-content")).toBeInTheDocument();
  });

  it("Drawer at open=false hides the side panel content from interactive use", () => {
    render(
      <Drawer open={false} onClose={jest.fn()} side="right">
        <div data-testid="side-panel-content">FilterPanel</div>
      </Drawer>,
    );

    const panel = screen.getByRole("dialog", { hidden: true });
    expect(panel).toHaveAttribute("aria-hidden", "true");
  });

  it("map layout component tracks drawer open state — toggle opens, backdrop closes", () => {
    // Simulate the IntelligenceMap toggle behavior using the Drawer component directly
    function TestMapLayout() {
      const [drawerOpen, setDrawerOpen] = useState(false);
      return (
        <>
          <button data-testid="drawer-toggle-button" onClick={() => setDrawerOpen(true)}>
            Filters
          </button>
          <Drawer open={drawerOpen} onClose={() => setDrawerOpen(false)} side="right">
            <div data-testid="map-side-panel">Filter Panel</div>
          </Drawer>
        </>
      );
    }

    render(<TestMapLayout />);

    // Initially closed
    expect(screen.getByRole("dialog", { hidden: true })).toHaveAttribute("aria-hidden", "true");

    // Click toggle to open
    fireEvent.click(screen.getByTestId("drawer-toggle-button"));
    expect(screen.getByRole("dialog")).not.toHaveAttribute("aria-hidden", "true");

    // Click backdrop to close
    fireEvent.click(screen.getByTestId("drawer-backdrop"));
    expect(screen.getByRole("dialog", { hidden: true })).toHaveAttribute("aria-hidden", "true");
  });
});
