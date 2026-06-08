import { describe, it, expect, vi, beforeEach , type Mock } from 'vitest';
/**
 * HilQueue page tests â€” PLAN-F-013 TASK-008
 *
 * Covers:
 *   - Non-admin/operator users are redirected to /
 */
import React from "react";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

// Mock useCurrentUser
vi.mock("@/app/providers/AuthProvider", () => ({
  useCurrentUser: vi.fn(),
}));

// Mock useHilQueue
vi.mock("./useHilQueue", () => ({
  useHilQueue: vi.fn(),
}));

// Mock child components to avoid dependency cascade
vi.mock("./HilQueueTable", () => ({
  HilQueueTable: () => React.createElement("div", { "data-testid": "hil-table" }),
}));
vi.mock("./HilItemDetail", () => ({
  HilItemDetail: () => React.createElement("div", { "data-testid": "hil-detail" }),
}));
vi.mock("./HilActionButtons", () => ({
  HilActionButtons: () => React.createElement("div", { "data-testid": "hil-actions" }),
}));

import { useCurrentUser } from "@/app/providers/AuthProvider";
import { useHilQueue } from "./useHilQueue";
import { HilQueue } from "./HilQueue";

const mockUseCurrentUser = useCurrentUser as Mock;
const mockUseHilQueue = useHilQueue as Mock;

function renderWithRouter(component: React.ReactElement) {
  return render(
    React.createElement(
      MemoryRouter,
      { initialEntries: ["/admin/hil"] },
      component,
    ),
  );
}

describe("HilQueue page", () => {
  beforeEach(() => {
    mockUseHilQueue.mockReturnValue({
      items: [],
      isLoading: false,
      executeAction: vi.fn(),
    });
  });

  it("renders the queue page for admin role", () => {
    mockUseCurrentUser.mockReturnValue({
      user: { user_id: "u1", tenant_id: "t1", role: "admin", email: "a@test.com" },
      isLoading: false,
    });

    renderWithRouter(React.createElement(HilQueue));
    expect(screen.getByTestId("hil-queue-page")).toBeTruthy();
  });

  it("renders the queue page for operator role", () => {
    mockUseCurrentUser.mockReturnValue({
      user: { user_id: "u1", tenant_id: "t1", role: "operator", email: "op@test.com" },
      isLoading: false,
    });

    renderWithRouter(React.createElement(HilQueue));
    expect(screen.getByTestId("hil-queue-page")).toBeTruthy();
  });

  it("redirects end_user to /", () => {
    mockUseCurrentUser.mockReturnValue({
      user: { user_id: "u1", tenant_id: "t1", role: "end_user", email: "user@test.com" },
      isLoading: false,
    });

    const { container } = renderWithRouter(React.createElement(HilQueue));
    // Navigate component will change location; hil-queue-page should not be present
    expect(screen.queryByTestId("hil-queue-page")).toBeNull();
  });

  it("renders nothing while user is loading", () => {
    mockUseCurrentUser.mockReturnValue({ user: null, isLoading: true });

    const { container } = renderWithRouter(React.createElement(HilQueue));
    // Returns null when no user
    expect(screen.queryByTestId("hil-queue-page")).toBeNull();
  });
});
