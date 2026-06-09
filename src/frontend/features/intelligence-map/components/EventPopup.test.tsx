import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { EventPopup } from "@/features/intelligence-map/components/EventPopup";
import type { EventPulse } from "@/features/intelligence-map/types/map.types";

const event: EventPulse = {
  event_id: "evt-1",
  category: ["geopolitical"],
  intensity: 4,
  headline: "Sanctions imposed",
  timestamp: "2026-06-08T00:00:00Z",
  lat: 0,
  lon: 0,
  relevance_window_end: "2026-06-09T00:00:00Z",
  affected_companies: [
    { company_id: "co-1", ticker: "AAPL", score_delta: -2 },
    { company_id: "co-2", ticker: "MSFT", score_delta: -1 },
  ],
};

describe("EventPopup", () => {
  it("renders headline, intensity, and affected company count", () => {
    render(<EventPopup event={event} onViewDetails={vi.fn()} />);
    expect(screen.getByText("Sanctions imposed")).toBeInTheDocument();
    expect(screen.getByText(/intensity[^a-z]*4/i)).toBeInTheDocument();
    expect(screen.getByText(/2 affected/i)).toBeInTheDocument();
  });

  it("fires onViewDetails(eventId) when the button is clicked", async () => {
    const cb = vi.fn();
    render(<EventPopup event={event} onViewDetails={cb} />);
    await userEvent.click(
      screen.getByRole("button", { name: /view details/i }),
    );
    expect(cb).toHaveBeenCalledWith("evt-1");
  });
});
