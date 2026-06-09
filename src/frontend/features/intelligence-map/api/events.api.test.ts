import { describe, it, expect } from "vitest";
import { http, HttpResponse } from "msw";

import { server } from "../../../../../tests/frontend/msw/server";
import { fetchEvents } from "@/features/intelligence-map/api/events.api";

const validEvent = {
  event_id: "evt-1",
  category: ["geopolitical"],
  intensity: 2,
  headline: "Test",
  timestamp: "2026-06-08T00:00:00Z",
  lat: 0,
  lon: 0,
  relevance_window_end: "2026-06-09T00:00:00Z",
  affected_companies: [],
};

describe("fetchEvents", () => {
  it("calls GET /api/v1/events with the supplied params and unwraps data", async () => {
    let capturedUrl = "";
    server.use(
      http.get("/api/v1/events", ({ request }) => {
        capturedUrl = request.url;
        return HttpResponse.json({
          data: [validEvent],
          meta: { request_id: "x", elapsed_ms: 1, count: 1, truncated: false },
        });
      }),
    );

    const result = await fetchEvents({
      bbox: "-180,-85,180,85",
      zoom: 2,
      context: "global",
    });
    expect(result).toHaveLength(1);
    expect(result[0]?.event_id).toBe("evt-1");
    expect(capturedUrl).toMatch(/bbox=-180%2C-85%2C180%2C85/);
    expect(capturedUrl).toMatch(/zoom=2/);
    expect(capturedUrl).toMatch(/context=global/);
  });

  it("throws ApiError with CONTRACT_MISMATCH on bad schema", async () => {
    server.use(
      http.get("/api/v1/events", () =>
        HttpResponse.json({
          data: [{ ...validEvent, intensity: 99 }],
          meta: { request_id: "x", elapsed_ms: 1 },
        }),
      ),
    );

    await expect(fetchEvents({})).rejects.toMatchObject({
      code: "CONTRACT_MISMATCH",
    });
  });

  it("propagates ApiError on non-2xx", async () => {
    server.use(
      http.get("/api/v1/events", () =>
        HttpResponse.json(
          {
            error: {
              code: "VALIDATION_FIELD_REQUIRED",
              message: "bbox malformed",
              request_id: "x",
            },
          },
          { status: 400 },
        ),
      ),
    );

    await expect(fetchEvents({ bbox: "garbage" })).rejects.toMatchObject({
      status: 400,
      code: "VALIDATION_FIELD_REQUIRED",
    });
  });
});
