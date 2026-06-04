/**
 * Jest setup file — extends expect with @testing-library/jest-dom matchers.
 * Imported by jest.config.js setupFilesAfterEnv.
 */
import "@testing-library/jest-dom";

// Polyfill ResizeObserver for jsdom — required by Recharts ResponsiveContainer
if (typeof ResizeObserver === "undefined") {
  global.ResizeObserver = class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}
