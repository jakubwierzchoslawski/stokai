import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "../../../../tests/frontend/msw/server";
import { apiStream, type StreamEvent } from "./stream";
import { setAccessToken, clearAccessToken } from "./client";

describe("apiStream", () => {
  beforeEach(() => clearAccessToken());
  afterEach(() => clearAccessToken());

  it("parses sequential SSE events and calls onEvent for each", async () => {
    const sse = [
      "event: token",
      'data: {"text":"Hi"}',
      "",
      "event: token",
      'data: {"text":" there"}',
      "",
      "event: done",
      'data: {"message_id":"m1"}',
      "",
    ].join("\n");
    server.use(
      http.get("/api/v1/qa/stream", () =>
        new HttpResponse(sse, { headers: { "content-type": "text/event-stream" } }),
      ),
    );
    const events: StreamEvent[] = [];
    await new Promise<void>((resolve) => {
      apiStream("/qa/stream", {
        onEvent: (e) => {
          events.push(e);
          if (e.event === "done") resolve();
        },
        onError: () => resolve(),
      });
    });
    expect(events.map((e) => e.event)).toEqual(["token", "token", "done"]);
    expect(events[0].data).toEqual({ text: "Hi" });
  });

  it("attaches Authorization header when token set", async () => {
    setAccessToken("tok_x");
    let received: string | null = null;
    server.use(
      http.get("/api/v1/stream/check", ({ request }) => {
        received = request.headers.get("authorization");
        return new HttpResponse("", { headers: { "content-type": "text/event-stream" } });
      }),
    );
    const ctrl = apiStream("/stream/check", { onEvent: () => {}, onError: () => {} });
    await new Promise((r) => setTimeout(r, 50));
    ctrl.abort();
    expect(received).toBe("Bearer tok_x");
  });
});
