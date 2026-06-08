/**
 * useHilQueue tests — PLAN-F-013 TASK-008
 *
 * Covers:
 *   - executeAction calls the correct API endpoint
 *   - executeAction invalidates queries on success
 */
import { renderHook, act, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";

// Mock WebSocket globally before importing the hook
class MockWebSocket {
  static OPEN = 1;
  readyState = MockWebSocket.OPEN;
  onmessage: ((e: MessageEvent) => void) | null = null;
  onerror: ((e: Event) => void) | null = null;
  close = jest.fn();
}
(global as unknown as { WebSocket: typeof MockWebSocket }).WebSocket = MockWebSocket;

// Mock fetch globally
const mockFetch = jest.fn();
(global as unknown as { fetch: typeof mockFetch }).fetch = mockFetch;

import { useHilQueue, HIL_ITEMS_QUERY_KEY, HIL_COUNT_QUERY_KEY } from "./useHilQueue";

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  function Wrapper({ children }: { children: React.ReactNode }) {
    return React.createElement(
      QueryClientProvider,
      { client: queryClient },
      children,
    );
  }
  return { Wrapper, queryClient };
}

describe("useHilQueue", () => {
  beforeEach(() => {
    mockFetch.mockClear();
  });

  it("executeAction calls POST API with correct payload", async () => {
    // Setup fetch for list and count queries
    mockFetch.mockImplementation((url: string) => {
      if (url.includes("/count")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ data: { pending_count: 0 } }),
        });
      }
      if (url.includes("/action")) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              data: {
                item_id: "item-1",
                status: "approved",
                workflow_resumed: true,
                feedback_id: "fb-1",
              },
            }),
        });
      }
      // list
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ data: [] }),
      });
    });

    const { Wrapper } = createWrapper();
    const { result } = renderHook(() => useHilQueue(), { wrapper: Wrapper });

    await act(async () => {
      await result.current.executeAction({
        itemId: "item-1",
        action: "approve",
      });
    });

    const actionCall = mockFetch.mock.calls.find((c: string[]) =>
      String(c[0]).includes("/action"),
    );
    expect(actionCall).toBeDefined();
    const body = JSON.parse(actionCall![1].body as string);
    expect(body.action).toBe("approve");
  });

  it("executeAction invalidates hil queries on success", async () => {
    mockFetch.mockImplementation((url: string) => {
      if (url.includes("/count")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ data: { pending_count: 1 } }),
        });
      }
      if (url.includes("/action")) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              data: {
                item_id: "item-1",
                status: "approved",
                workflow_resumed: true,
                feedback_id: "fb-1",
              },
            }),
        });
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ data: [] }),
      });
    });

    const { Wrapper, queryClient } = createWrapper();
    const invalidateSpy = jest.spyOn(queryClient, "invalidateQueries");

    const { result } = renderHook(() => useHilQueue(), { wrapper: Wrapper });

    await act(async () => {
      await result.current.executeAction({
        itemId: "item-1",
        action: "reject",
      });
    });

    // After successful action, invalidateQueries should have been called
    // for both HIL_ITEMS_QUERY_KEY and HIL_COUNT_QUERY_KEY
    await waitFor(() => {
      expect(invalidateSpy).toHaveBeenCalled();
    });
  });
});
