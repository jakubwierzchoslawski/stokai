import { describe, it, expect } from "vitest";
import { renderHook } from "@testing-library/react";
import { useBreakpoint, BREAKPOINTS } from "./useBreakpoint";

describe("useBreakpoint", () => {
  it("exports the canonical breakpoints", () => {
    expect(BREAKPOINTS).toEqual({ sm: 375, md: 768, lg: 1280, xl: 1440 });
  });

  it("returns the current bucket based on innerWidth", () => {
    Object.defineProperty(window, "innerWidth", { writable: true, configurable: true, value: 900 });
    const { result } = renderHook(() => useBreakpoint());
    expect(result.current).toBe("md");
  });
});
