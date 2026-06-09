import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import React from "react";

import { server } from "../../../../../tests/frontend/msw/server";

// Mock apiSocket — msw does not handle WS in jsdom.
vi.mock("@/lib/api/ws", () => {
  let lastHandlers: {
    onMessage: (m: unknown) => void;
    onClose: (e: CloseEvent) => void;
  } | null = null;
  let closes = 0;
  return {
    apiSocket: (
      _path: string,
      handlers: {
        onMessage: (m: unknown) => void;
        onClose: (e: CloseEvent) => void;
      },
    ) => {
      lastHandlers = handlers;
      return {
        close: () => {
          closes += 1;
        },
      };
    },
    __test__: {
      pushMessage: (m: unknown) => lastHandlers?.onMessage(m),
      getCloseCount: () => closes,
      reset: () => {
        lastHandlers = null;
        closes = 0;
      },
    },
  };
});

import * as ws from "@/lib/api/ws";
const { __test__ } = ws as unknown as {
  __test__: {
    pushMessage: (m: unknown) => void;
    getCloseCount: () => number;
    reset: () => void;
  };
};

import { useEventFeed } from "@/features/intelligence-map/hooks/useEventFeed";

const validEvent = {
  event_id: "evt-ws-1",
  category: ["geo"],
  intensity: 2,
  headline: "ws event",
  timestamp: "2026-06-08T00:00:00Z",
  lat: 1,
  lon: 2,
  relevance_window_end: "2026-06-09T00:00:00Z",
  affected_companies: [],
};

beforeEach(() => __test__.reset());

function wrap({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
}

describe("useEventFeed", () => {
  it("seeds events from REST and appends from WS event.created frames", async () => {
    server.use(
      http.get("/api/v1/events", () =>
        HttpResponse.json({ data: [validEvent], meta: {} }),
      ),
    );
    const { result } = renderHook(() => useEventFeed({}), { wrapper: wrap });
    await waitFor(() => expect(result.current.events).toHaveLength(1));

    act(() => {
      __test__.pushMessage({
        type: "event.created",
        event: { ...validEvent, event_id: "evt-ws-2" },
      });
    });

    expect(result.current.events.map((e) => e.event_id)).toEqual([
      "evt-ws-1",
      "evt-ws-2",
    ]);
  });

  it("ignores ping frames", async () => {
    server.use(
      http.get("/api/v1/events", () =>
        HttpResponse.json({ data: [], meta: {} }),
      ),
    );
    const { result } = renderHook(() => useEventFeed({}), { wrapper: wrap });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    act(() => {
      __test__.pushMessage({ type: "ping" });
    });
    expect(result.current.events).toHaveLength(0);
  });

  it("ignores malformed frames silently", async () => {
    server.use(
      http.get("/api/v1/events", () =>
        HttpResponse.json({ data: [], meta: {} }),
      ),
    );
    const { result } = renderHook(() => useEventFeed({}), { wrapper: wrap });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    act(() => {
      __test__.pushMessage({ type: "event.created", event: { bogus: true } });
    });
    expect(result.current.events).toHaveLength(0);
  });

  it("calls close() on unmount", async () => {
    server.use(
      http.get("/api/v1/events", () =>
        HttpResponse.json({ data: [], meta: {} }),
      ),
    );
    const { unmount } = renderHook(() => useEventFeed({}), { wrapper: wrap });
    unmount();
    expect(__test__.getCloseCount()).toBe(1);
  });
});
