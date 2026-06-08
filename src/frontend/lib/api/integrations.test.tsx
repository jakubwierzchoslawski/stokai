import { describe, it, expect } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import React from "react";

import { server } from "../../../../tests/frontend/msw/server";
import { useIntegrations } from "@/lib/api/integrations";

function wrapper({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
}

describe("useIntegrations", () => {
  it("returns the integrations map from the envelope", async () => {
    server.use(
      http.get("/api/v1/system/integrations", () =>
        HttpResponse.json({
          data: {
            llm: { provider: "openai", mode: "live" },
            market_data: {
              provider: "polygon",
              mode: "stub",
              reason: "API key not configured",
            },
            news: { provider: "gdelt", mode: "live" },
          },
          meta: { request_id: "test", elapsed_ms: 1 },
        }),
      ),
    );

    const { result } = renderHook(() => useIntegrations(), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.data?.market_data?.mode).toBe("stub");
    expect(result.current.data?.market_data?.reason).toBe(
      "API key not configured",
    );
    expect(result.current.data?.llm?.mode).toBe("live");
  });

  it("exposes typed isStub(integration) helper", async () => {
    server.use(
      http.get("/api/v1/system/integrations", () =>
        HttpResponse.json({
          data: {
            llm: { provider: "openai", mode: "live" },
            market_data: { provider: "polygon", mode: "stub" },
            news: { provider: "gdelt", mode: "live" },
          },
          meta: { request_id: "test", elapsed_ms: 1 },
        }),
      ),
    );

    const { result } = renderHook(() => useIntegrations(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.isStub("market_data")).toBe(true);
    expect(result.current.isStub("llm")).toBe(false);
  });

  it("isStub returns false when data is not yet loaded", () => {
    server.use(
      http.get("/api/v1/system/integrations", async () => {
        await new Promise((r) => setTimeout(r, 100));
        return HttpResponse.json({
          data: { llm: { provider: "openai", mode: "stub" } },
          meta: {},
        });
      }),
    );

    const { result } = renderHook(() => useIntegrations(), { wrapper });
    expect(result.current.isStub("llm")).toBe(false);
  });
});
