/**
 * AdminLayout.test.tsx — TDD tests for AdminLayout responsive layout.
 *
 * Tests written first (red phase) per PLAN-N-014 TASK-006.
 */

import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { AdminLayout } from "../../../src/frontend/admin/AdminLayout";

// ── Mock useBreakpoint ────────────────────────────────────────────────────────

jest.mock("../../../src/frontend/features/shared/hooks/useBreakpoint", () => ({
  useBreakpoint: jest.fn(),
}));

const { useBreakpoint } = require("../../../src/frontend/features/shared/hooks/useBreakpoint");

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("AdminLayout", () => {
  afterEach(() => {
    jest.clearAllMocks();
  });

  it("renders navigation rail and main content in flex row at lg (≥1280px)", () => {
    useBreakpoint.mockReturnValue("lg");
    render(
      <AdminLayout>
        <div>Main content</div>
      </AdminLayout>,
    );

    // Navigation rail should be present as a sibling (not in a drawer)
    expect(screen.getByRole("navigation", { name: "Admin navigation" })).toBeInTheDocument();
    expect(screen.getByRole("main")).toBeInTheDocument();

    // No hamburger button at lg
    expect(screen.queryByTestId("admin-hamburger")).not.toBeInTheDocument();
  });

  it("hides navigation rail and shows hamburger button at sm (<768px)", () => {
    useBreakpoint.mockReturnValue("sm");
    render(
      <AdminLayout>
        <div>Main content</div>
      </AdminLayout>,
    );

    // Navigation rail should NOT be in the flex row at sm
    // (it may exist inside a closed drawer, but the nav element should be hidden)
    const hamburger = screen.getByTestId("admin-hamburger");
    expect(hamburger).toBeInTheDocument();
  });

  it("opens Drawer with nav content when hamburger is clicked at sm", () => {
    useBreakpoint.mockReturnValue("sm");
    render(
      <AdminLayout>
        <div>Main content</div>
      </AdminLayout>,
    );

    fireEvent.click(screen.getByTestId("admin-hamburger"));

    // Drawer should now be open
    const dialog = screen.getByRole("dialog");
    expect(dialog).not.toHaveAttribute("aria-hidden", "true");
  });

  it("renders icon-only nav rail at md (tablet mode)", () => {
    useBreakpoint.mockReturnValue("md");
    render(
      <AdminLayout>
        <div>Main content</div>
      </AdminLayout>,
    );

    // Navigation should be present (not in a drawer)
    expect(screen.getByTestId("admin-nav-rail")).toBeInTheDocument();
    // No hamburger at tablet
    expect(screen.queryByTestId("admin-hamburger")).not.toBeInTheDocument();
  });

  it("main element has overflow-x-hidden to prevent page-level horizontal scroll", () => {
    useBreakpoint.mockReturnValue("lg");
    render(
      <AdminLayout>
        <div>Main content</div>
      </AdminLayout>,
    );

    const main = screen.getByRole("main");
    expect(main.style.overflowX).toBe("hidden");
  });
});
