import { describe, it, expect, vi, beforeEach } from 'vitest';
/**
 * BindingsPanel tests â€” PLAN-F-028 TASK-010
 *
 * Tests cover:
 *   - Renders loading state while fetching.
 *   - Renders empty state when no bindings exist.
 *   - Renders market rows when bindings exist.
 *   - Shows "Change will take effect within 60 s" toast after successful PUT.
 */
import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// â”€â”€ Mocks â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

function makeClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
}

function makeFetch(bindingsData: unknown, sourcesData: unknown) {
  return vi.fn().mockImplementation((url: string) => {
    if (url.includes("/bindings")) {
      return Promise.resolve({
        ok: true,
        status: 200,
        json: async () => ({ data: bindingsData, error: null }),
      });
    }
    if (url.includes("/sources")) {
      return Promise.resolve({
        ok: true,
        status: 200,
        json: async () => ({ data: sourcesData, error: null }),
      });
    }
    return Promise.resolve({ ok: false, status: 404, json: async () => null });
  });
}

function renderPanel() {
  const client = makeClient();
  const { BindingsPanel } = require("./BindingsPanel");
  return render(
    React.createElement(
      QueryClientProvider,
      { client },
      React.createElement(BindingsPanel),
    ),
  );
}

// â”€â”€ Tests â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

describe("BindingsPanel", () => {
  beforeEach(() => {
    vi.resetModules();
    vi.resetAllMocks();
  });

  it("shows loading state initially", () => {
    (global as any).fetch = vi.fn().mockReturnValue(new Promise(() => {})); // never resolves
    renderPanel();
    expect(screen.getByTestId("bindings-loading")).toBeTruthy();
  });

  it("shows empty state when no bindings exist", async () => {
    (global as any).fetch = makeFetch([], []);
    renderPanel();

    await waitFor(() => {
      expect(screen.getByTestId("bindings-empty")).toBeTruthy();
    });
  });

  it("renders market rows when bindings exist", async () => {
    const marketId = "11111111-0000-0000-0000-000000000001";
    const bindings = [
      { market_id: marketId, interface_type: "PriceProvider", source_id: "src-001", role: "primary" },
    ];
    const sources = [
      { source_id: "src-001", display_name: "Finnhub", interface_type: "PriceProvider", enabled: true, config: {}, cost_tier: "low", priority: 1, health: null },
    ];

    (global as any).fetch = makeFetch(bindings, sources);
    renderPanel();

    await waitFor(() => {
      expect(screen.getByTestId(`binding-row-${marketId}`)).toBeTruthy();
    });
  });

  it("shows toast after successful PUT", async () => {
    const marketId = "22222222-0000-0000-0000-000000000002";
    const bindings = [
      { market_id: marketId, interface_type: "PriceProvider", source_id: "src-001", role: "primary" },
    ];
    const sources = [
      { source_id: "src-001", display_name: "Finnhub", interface_type: "PriceProvider", enabled: true, config: {}, cost_tier: "low", priority: 1, health: null },
      { source_id: "src-002", display_name: "Polygon", interface_type: "PriceProvider", enabled: true, config: {}, cost_tier: "medium", priority: 0, health: null },
    ];

    (global as any).fetch = vi.fn().mockImplementation((url: string, opts?: RequestInit) => {
      if ((opts?.method === "PUT") || url.includes("/bindings") && opts?.method === "PUT") {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => ({
            data: { market_id: marketId, interface_type: "PriceProvider", source_id: "src-002", role: "primary" },
            error: null,
          }),
        });
      }
      if (url.includes("/bindings")) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => ({ data: bindings, error: null }),
        });
      }
      if (url.includes("/sources")) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => ({ data: sources, error: null }),
        });
      }
      return Promise.resolve({ ok: false, status: 404, json: async () => null });
    });

    renderPanel();

    await waitFor(() => {
      expect(screen.getByTestId(`binding-row-${marketId}`)).toBeTruthy();
    });

    // Change the primary binding select
    const select = screen.getByTestId(
      `binding-select-${marketId}-PriceProvider-primary`
    );
    fireEvent.change(select, { target: { value: "src-002" } });

    await waitFor(() => {
      expect(screen.getByTestId("bindings-toast")).toBeTruthy();
      expect(screen.getByText(/60 s/)).toBeTruthy();
    });
  });
});
