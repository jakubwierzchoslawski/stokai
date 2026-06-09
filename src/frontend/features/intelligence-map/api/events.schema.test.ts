import { describe, it, expect } from "vitest";

import {
  EventPulseSchema,
  EventsArraySchema,
} from "@/features/intelligence-map/api/events.schema";

const validPulse = {
  event_id: "evt-1",
  category: ["geopolitical"],
  intensity: 3,
  headline: "Test event",
  timestamp: "2026-06-08T12:00:00Z",
  lat: 40.7,
  lon: -74.0,
  relevance_window_end: "2026-06-09T12:00:00Z",
  affected_companies: [
    { company_id: "co-1", ticker: "AAPL", score_delta: -2.5 },
  ],
};

describe("EventPulseSchema", () => {
  it("parses a valid event", () => {
    expect(EventPulseSchema.parse(validPulse).event_id).toBe("evt-1");
  });

  it("rejects intensity outside 1-5", () => {
    expect(() =>
      EventPulseSchema.parse({ ...validPulse, intensity: 6 }),
    ).toThrow();
    expect(() =>
      EventPulseSchema.parse({ ...validPulse, intensity: 0 }),
    ).toThrow();
  });

  it("rejects missing required fields", () => {
    const { headline: _omit, ...rest } = validPulse;
    void _omit;
    expect(() => EventPulseSchema.parse(rest)).toThrow();
  });

  it("rejects non-array category", () => {
    expect(() =>
      EventPulseSchema.parse({ ...validPulse, category: "geopolitical" }),
    ).toThrow();
  });

  it("parses an array of events", () => {
    const parsed = EventsArraySchema.parse([validPulse, validPulse]);
    expect(parsed).toHaveLength(2);
  });

  it("rejects an array with one bad event", () => {
    expect(() =>
      EventsArraySchema.parse([validPulse, { ...validPulse, intensity: 99 }]),
    ).toThrow();
  });
});
