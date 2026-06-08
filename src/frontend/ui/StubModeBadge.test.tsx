import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router-dom";
import React from "react";

import { server } from "../../../tests/frontend/msw/server";
import { StubModeBadge } from "@/ui/StubModeBadge";

function integrationsHandler(overrides: Record<string, unknown> = {}) {
  return http.get("/api/v1/system/integrations", () =>
    HttpResponse.json({
      data: {
        llm: { provider: "openai", mode: "live" },
        market_data: { provider: "polygon", mode: "live" },
        news: { provider: "gdelt", mode: "live" },
        ...overrides,
      },
      meta: { request_id: "t", elapsed_ms: 1 },
    }),
  );
}

function Wrap({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

describe("StubModeBadge", () => {
  it("renders nothing when all watched integrations are live", async () => {
    server.use(integrationsHandler());
    render(
      <Wrap>
        <StubModeBadge watch={["market_data", "news"]} />
      </Wrap>,
    );
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.queryByTestId("stub-mode-badge")).toBeNull();
  });

  it("renders with affected integration names when one is stub", async () => {
    server.use(
      integrationsHandler({
        market_data: {
          provider: "polygon",
          mode: "stub",
          reason: "API key not configured",
        },
      }),
    );
    render(
      <Wrap>
        <StubModeBadge watch={["market_data", "news"]} />
      </Wrap>,
    );
    const badge = await screen.findByTestId("stub-mode-badge");
    expect(badge.textContent).toMatch(/stub mode/i);
    expect(badge.textContent).toMatch(/market_data/i);
  });

  it("opens a popover with the reason on click", async () => {
    server.use(
      integrationsHandler({
        news: { provider: "gdelt", mode: "stub", reason: "License pending" },
      }),
    );
    render(
      <Wrap>
        <StubModeBadge watch={["news"]} />
      </Wrap>,
    );
    const badge = await screen.findByTestId("stub-mode-badge");
    await userEvent.click(badge);
    expect(await screen.findByText(/license pending/i)).toBeInTheDocument();
  });
});
