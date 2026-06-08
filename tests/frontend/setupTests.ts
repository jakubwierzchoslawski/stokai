import "@testing-library/jest-dom/vitest";
import { afterEach, vi, beforeAll, afterAll } from "vitest";
import { cleanup } from "@testing-library/react";
import { server } from "./msw/server";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterAll(() => server.close());
afterEach(() => server.resetHandlers());

// jsdom does not implement matchMedia — required by next-themes
if (typeof window !== "undefined" && !window.matchMedia) {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }),
  });
}
