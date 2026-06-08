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

  it("defaults VITE_MAP_STYLE_URL to CARTO dark-matter when unset", async () => {
    vi.stubEnv("VITE_API_BASE_URL", "/api/v1");
    vi.stubEnv("VITE_APP_NAME", "StokAI");
    vi.stubEnv("VITE_MAP_STYLE_URL", "");
    const { env } = await import("./env");
    expect(env.mapStyleUrl).toBe(
      "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
    );
  });

  it("accepts a VITE_MAP_STYLE_URL override", async () => {
    vi.stubEnv("VITE_API_BASE_URL", "/api/v1");
    vi.stubEnv("VITE_APP_NAME", "StokAI");
    vi.stubEnv("VITE_MAP_STYLE_URL", "https://tiles.example.com/style.json");
    const { env } = await import("./env");
    expect(env.mapStyleUrl).toBe("https://tiles.example.com/style.json");
  });

  it("rejects a non-URL VITE_MAP_STYLE_URL", async () => {
    vi.stubEnv("VITE_API_BASE_URL", "/api/v1");
    vi.stubEnv("VITE_APP_NAME", "StokAI");
    vi.stubEnv("VITE_MAP_STYLE_URL", "not-a-url");
    await expect(import("./env")).rejects.toThrow(/VITE_MAP_STYLE_URL/);
  });
});
