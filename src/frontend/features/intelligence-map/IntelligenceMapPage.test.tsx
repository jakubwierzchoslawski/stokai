import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import React from "react";

import { server } from "../../../../tests/frontend/msw/server";
import { ProgressiveDisclosureProvider } from "@/features/progressive-disclosure/ProgressiveDisclosureProvider";

// ── Mock IntelligenceMap — avoids maplibre-gl / WebGL hang in jsdom threads pool.
// IntelligenceMapPage only wires onExpandEvent and renders StubModeBadge on top;
// the map internals are covered by IntelligenceMap.test.tsx.
vi.mock("./IntelligenceMap", () => ({
  IntelligenceMap: ({ onExpandEvent }: { onExpandEvent?: (e: unknown) => void }) =>
    React.createElement("div", {
      "data-testid": "intelligence-map-root",
      onClick: () => onExpandEvent?.({ event_id: "test-evt", lat: 0, lon: 0 }),
    }),
}));
vi.mock("@/features/progressive-disclosure/components/EventPopup", () => ({ EventPopup: () => null }));
vi.mock("@/features/progressive-disclosure/components/SidePanel", () => ({ SidePanel: () => null }));
vi.mock("@/features/progressive-disclosure/components/AuditTrailView", () => ({ AuditTrailView: () => null }));

import { IntelligenceMapPage } from "@/features/intelligence-map/IntelligenceMapPage";

function Wrap({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route
            path="/"
            element={
              <ProgressiveDisclosureProvider>
                {children}
              </ProgressiveDisclosureProvider>
            }
          />
          <Route
            path="/events/:eventId/deep-dive"
            element={<div data-testid="deep-dive" />}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("IntelligenceMapPage", () => {
  it("renders the intelligence map root", async () => {
    server.use(
      http.get("/api/v1/system/integrations", () =>
        HttpResponse.json({
          data: {
            llm: { provider: "openai", mode: "live" },
            market_data: { provider: "polygon", mode: "live" },
            news: { provider: "gdelt", mode: "live" },
          },
          meta: {},
        }),
      ),
    );
    render(
      <Wrap>
        <IntelligenceMapPage />
      </Wrap>,
    );
    expect(
      await screen.findByTestId("intelligence-map-root"),
    ).toBeInTheDocument();
  });

  it("does not render StubModeBadge when all watched integrations are live", async () => {
    server.use(
      http.get("/api/v1/system/integrations", () =>
        HttpResponse.json({
          data: {
            llm: { provider: "openai", mode: "live" },
            market_data: { provider: "polygon", mode: "live" },
            news: { provider: "gdelt", mode: "live" },
          },
          meta: {},
        }),
      ),
    );
    render(
      <Wrap>
        <IntelligenceMapPage />
      </Wrap>,
    );
    await waitFor(() => {
      expect(screen.queryByTestId("stub-mode-badge")).toBeNull();
    });
  });
});
