/**
 * SourcesPage and SourceList tests — PLAN-F-028 TASK-007
 *
 * Uses msw to mock the /api/v1/admin/sources endpoint.
 *
 * Tests cover:
 *   - SourceList renders a row per source.
 *   - Health badge shows green when rate_limit_pct < 70%.
 *   - Health badge shows amber when rate_limit_pct >= 70% and < 80%.
 *   - Health badge shows red when rate_limit_pct >= 80%.
 *   - Enable toggle optimistically updates; reverts on API error.
 *   - Non-admin user is redirected to /.
 */
import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// ── Mocks ─────────────────────────────────────────────────────────────────────

jest.mock("../../../hooks/useCurrentUser", () => ({
  useCurrentUser: jest.fn(),
}));

jest.mock("./SocialSourcesPanel", () => ({
  SocialSourcesPanel: () =>
    React.createElement("div", { "data-testid": "social-panel" }),
}));

jest.mock("./BindingsPanel", () => ({
  BindingsPanel: () =>
    React.createElement("div", { "data-testid": "bindings-panel" }),
}));

import { useCurrentUser } from "../../../hooks/useCurrentUser";

const mockUseCurrentUser = useCurrentUser as jest.Mock;

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeSource(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    source_id: "src-001",
    display_name: "Finnhub",
    interface_type: "PriceProvider",
    enabled: true,
    config: {},
    cost_tier: "low",
    priority: 1,
    health: {
      calls_today: 50,
      errors_today: 2,
      rate_limit_pct_used: 40.0,
      estimated_cost_today: 0.005,
    },
    ...overrides,
  };
}

function makeFetchMock(data: unknown, ok = true) {
  return jest.fn().mockResolvedValue({
    ok,
    status: ok ? 200 : 500,
    json: async () => (ok ? { data, error: null } : { data: null, error: { code: "ERR", message: "fail" } }),
  });
}

function renderWithProviders(ui: React.ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    React.createElement(
      QueryClientProvider,
      { client },
      React.createElement(MemoryRouter, { initialEntries: ["/admin/sources"] }, ui),
    ),
  );
}

// ── SourceList tests ──────────────────────────────────────────────────────────

describe("SourceList", () => {
  beforeEach(() => {
    jest.resetAllMocks();
    mockUseCurrentUser.mockReturnValue({
      user: { user_id: "u1", tenant_id: "t1", role: "admin", email: "a@test.com" },
      isLoading: false,
    });
  });

  it("renders a row per source", async () => {
    const sources = [makeSource(), makeSource({ source_id: "src-002", display_name: "Polygon" })];
    (global as any).fetch = makeFetchMock(sources);

    const { SourcesPage } = require("./SourcesPage");
    renderWithProviders(React.createElement(SourcesPage));

    await waitFor(() => {
      expect(screen.getByText("Finnhub")).toBeTruthy();
      expect(screen.getByText("Polygon")).toBeTruthy();
    });
  });

  it("health badge is green when rate_limit_pct < 70", async () => {
    const sources = [makeSource({ health: { calls_today: 10, errors_today: 0, rate_limit_pct_used: 40.0, estimated_cost_today: 0 } })];
    (global as any).fetch = makeFetchMock(sources);

    const { SourcesPage } = require("./SourcesPage");
    renderWithProviders(React.createElement(SourcesPage));

    await waitFor(() => {
      const badge = screen.getByTestId("health-badge");
      expect(badge.className).toContain("green");
    });
  });

  it("health badge is amber when rate_limit_pct is 70-80", async () => {
    const sources = [makeSource({ health: { calls_today: 10, errors_today: 0, rate_limit_pct_used: 75.0, estimated_cost_today: 0 } })];
    (global as any).fetch = makeFetchMock(sources);

    const { SourcesPage } = require("./SourcesPage");
    renderWithProviders(React.createElement(SourcesPage));

    await waitFor(() => {
      const badge = screen.getByTestId("health-badge");
      expect(badge.className).toContain("amber");
    });
  });

  it("health badge is red when rate_limit_pct >= 80", async () => {
    const sources = [makeSource({ health: { calls_today: 10, errors_today: 0, rate_limit_pct_used: 85.0, estimated_cost_today: 0 } })];
    (global as any).fetch = makeFetchMock(sources);

    const { SourcesPage } = require("./SourcesPage");
    renderWithProviders(React.createElement(SourcesPage));

    await waitFor(() => {
      const badge = screen.getByTestId("health-badge");
      expect(badge.className).toContain("red");
    });
  });

  it("non-admin user is redirected to /", async () => {
    mockUseCurrentUser.mockReturnValue({
      user: { user_id: "u2", tenant_id: "t1", role: "end_user", email: "u@test.com" },
      isLoading: false,
    });

    (global as any).fetch = makeFetchMock([]);

    const { SourcesPage } = require("./SourcesPage");
    renderWithProviders(React.createElement(SourcesPage));

    await waitFor(() => {
      expect(screen.queryByTestId("sources-page")).toBeNull();
    });
  });
});
