import { describe, it, expect } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import React from "react";

import { server } from "../../../../../tests/frontend/msw/server";
import { useHistoricalEvents } from "@/features/intelligence-map/hooks/useHistoricalEvents";

const event = (id: string, ts: string) => ({
  event_id: id,
  category: ["geo"],
  intensity: 2,
  headline: id,
  timestamp: ts,
  lat: 0,
  lon: 0,
  relevance_window_end: ts,
  affected_companies: [],
});

function wrap({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
}

describe("useHistoricalEvents", () => {
  it("returns empty + no fetch when disabled", async () => {
    let called = false;
    server.use(
      http.get("/api/v1/events", () => {
        called = true;
        return HttpResponse.json({ data: [], meta: {} });
      }),
    );

    const { result } = renderHook(
      () =>
        useHistoricalEvents({
          dateRange: { from_date: "", to_date: "" },
          enabled: false,
        }),
      { wrapper: wrap },
    );
    await new Promise((r) => setTimeout(r, 50));
    expect(result.current.events).toEqual([]);
    expect(called).toBe(false);
  });

  it("calls GET /events?from=&to= and returns sorted asc by timestamp", async () => {
    let capturedUrl = "";
    server.use(
      http.get("/api/v1/events", ({ request }) => {
        capturedUrl = request.url;
        return HttpResponse.json({
          data: [
            event("b", "2026-02-01T00:00:00Z"),
            event("a", "2026-01-01T00:00:00Z"),
          ],
          meta: {},
        });
      }),
    );

    const { result } = renderHook(
      () =>
        useHistoricalEvents({
          dateRange: { from_date: "2026-01-01", to_date: "2026-03-01" },
          enabled: true,
        }),
      { wrapper: wrap },
    );

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.events.map((e) => e.event_id)).toEqual(["a", "b"]);
    expect(capturedUrl).toMatch(/from=2026-01-01/);
    expect(capturedUrl).toMatch(/to=2026-03-01/);
  });
});
