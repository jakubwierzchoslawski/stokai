import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "../../../../tests/frontend/msw/server";
import { api, setAccessToken, clearAccessToken } from "./client";
import { ApiError } from "./errors";

describe("api()", () => {
  beforeEach(() => clearAccessToken());
  afterEach(() => clearAccessToken());

  it("unwraps the envelope and returns data on 200", async () => {
    server.use(
      http.get("/api/v1/ping", () =>
        HttpResponse.json({ data: { pong: true } }),
      ),
    );
    const res = await api<{ pong: boolean }>("/ping");
    expect(res).toEqual({ pong: true });
  });

  it("attaches Authorization header when access token set", async () => {
    setAccessToken("tok_123");
    let received: string | null = null;
    server.use(
      http.get("/api/v1/secret", ({ request }) => {
        received = request.headers.get("authorization");
        return HttpResponse.json({ data: { ok: true } });
      }),
    );
    await api("/secret");
    expect(received).toBe("Bearer tok_123");
  });

  it("omits Authorization when skipAuth=true", async () => {
    setAccessToken("tok_123");
    let received: string | null = "PRESENT";
    server.use(
      http.get("/api/v1/public", ({ request }) => {
        received = request.headers.get("authorization");
        return HttpResponse.json({ data: { ok: true } });
      }),
    );
    await api("/public", { skipAuth: true });
    expect(received).toBeNull();
  });

  it("throws ApiError with status/code/message on 4xx", async () => {
    server.use(
      http.get("/api/v1/bad", () =>
        HttpResponse.json(
          { error: { code: "VALIDATION_FORMAT", message: "bad input", details: { field: "x" }, request_id: "r1" } },
          { status: 400 },
        ),
      ),
    );
    await expect(api("/bad")).rejects.toMatchObject({
      name: "ApiError",
      status: 400,
      code: "VALIDATION_FORMAT",
      message: "bad input",
      details: { field: "x" },
      requestId: "r1",
    });
  });

  it("retries exactly once after a silent refresh on 401, then succeeds", async () => {
    setAccessToken("expired");
    let calls = 0;
    server.use(
      http.get("/api/v1/me", ({ request }) => {
        calls += 1;
        const auth = request.headers.get("authorization");
        if (auth === "Bearer expired") {
          return HttpResponse.json(
            { error: { code: "AUTH_TOKEN_EXPIRED", message: "expired" } },
            { status: 401 },
          );
        }
        return HttpResponse.json({ data: { id: "u1" } });
      }),
      http.post("/api/v1/auth/refresh", () =>
        HttpResponse.json({ data: { access_token: "fresh", exp: Math.floor(Date.now() / 1000) + 3600 } }),
      ),
    );
    const res = await api<{ id: string }>("/me");
    expect(res).toEqual({ id: "u1" });
    expect(calls).toBe(2);
  });

  it("dedupes concurrent refresh requests", async () => {
    setAccessToken("expired");
    let refreshCalls = 0;
    server.use(
      http.get("/api/v1/me", ({ request }) => {
        const auth = request.headers.get("authorization");
        if (auth === "Bearer expired") {
          return HttpResponse.json(
            { error: { code: "AUTH_TOKEN_EXPIRED", message: "x" } },
            { status: 401 },
          );
        }
        return HttpResponse.json({ data: { id: "u1" } });
      }),
      http.post("/api/v1/auth/refresh", async () => {
        refreshCalls += 1;
        await new Promise((r) => setTimeout(r, 20));
        return HttpResponse.json({ data: { access_token: "fresh", exp: 9999 } });
      }),
    );
    await Promise.all([api("/me"), api("/me"), api("/me")]);
    expect(refreshCalls).toBe(1);
  });

  it("emits auth:expired and throws when refresh fails", async () => {
    setAccessToken("expired");
    server.use(
      http.get("/api/v1/me", () =>
        HttpResponse.json(
          { error: { code: "AUTH_TOKEN_EXPIRED", message: "x" } },
          { status: 401 },
        ),
      ),
      http.post("/api/v1/auth/refresh", () =>
        HttpResponse.json(
          { error: { code: "AUTH_REFRESH_FAILED", message: "no cookie" } },
          { status: 401 },
        ),
      ),
    );
    const handler = vi.fn();
    window.addEventListener("auth:expired", handler);
    await expect(api("/me")).rejects.toBeInstanceOf(ApiError);
    expect(handler).toHaveBeenCalledOnce();
    window.removeEventListener("auth:expired", handler);
  });

  it("throws NETWORK_ERROR for fetch failures", async () => {
    server.use(http.get("/api/v1/down", () => HttpResponse.error()));
    await expect(api("/down")).rejects.toMatchObject({ code: "NETWORK_ERROR" });
  });
});
