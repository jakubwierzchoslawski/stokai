import { describe, it, expect, vi, beforeEach } from "vitest";

describe("env", () => {
  beforeEach(() => { vi.resetModules(); });

  it("parses required vars with defaults", async () => {
    vi.stubEnv("VITE_API_BASE_URL", "/api/v1");
    vi.stubEnv("VITE_APP_NAME", "StokAI");
    vi.stubEnv("VITE_ENABLE_DEVTOOLS", "false");
    const { env } = await import("./env");
    expect(env.apiBaseUrl).toBe("/api/v1");
    expect(env.appName).toBe("StokAI");
    expect(env.enableDevtools).toBe(false);
  });

  it("coerces VITE_ENABLE_DEVTOOLS=true to boolean true", async () => {
    vi.stubEnv("VITE_API_BASE_URL", "/api/v1");
    vi.stubEnv("VITE_APP_NAME", "StokAI");
    vi.stubEnv("VITE_ENABLE_DEVTOOLS", "true");
    const { env } = await import("./env");
    expect(env.enableDevtools).toBe(true);
  });
});
