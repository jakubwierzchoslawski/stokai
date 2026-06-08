import { describe, it, expect, vi, afterEach , type Mock } from 'vitest';
/**
 * useBreakpoint.test.ts â€” TDD tests for the useBreakpoint hook.
 *
 * Tests are written first (red phase) per PLAN-N-014 TASK-002.
 *
 * Strategy: mock window.matchMedia to control which media queries match,
 * then verify the hook returns the correct breakpoint string.
 */

import { renderHook, act } from "@testing-library/react";
import { useBreakpoint } from "../../../../src/frontend/features/shared/hooks/useBreakpoint";

// â”€â”€ matchMedia mock factory â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

interface MockMQL {
  matches: boolean;
  media: string;
  onchange: null;
  addListener: Mock;
  removeListener: Mock;
  addEventListener: Mock;
  removeEventListener: Mock;
  dispatchEvent: Mock;
  _listeners: Array<(e: { matches: boolean }) => void>;
  _setMatches: (v: boolean) => void;
}

function createMockMQL(matches: boolean, media: string): MockMQL {
  const mql: MockMQL = {
    matches,
    media,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn((event: string, handler: (e: { matches: boolean }) => void) => {
      mql._listeners.push(handler);
    }),
    removeEventListener: vi.fn((event: string, handler: (e: { matches: boolean }) => void) => {
      mql._listeners = mql._listeners.filter((l) => l !== handler);
    }),
    dispatchEvent: vi.fn(),
    _listeners: [],
    _setMatches: (v: boolean) => {
      mql.matches = v;
      mql._listeners.forEach((l) => l({ matches: v }));
    },
  };
  return mql;
}

// â”€â”€ Tests â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

describe("useBreakpoint", () => {
  let mqls: Record<string, MockMQL>;

  function setupMatchMedia(matchingQueries: string[]) {
    const queries = [
      "(min-width: 768px)",
      "(min-width: 1280px)",
      "(min-width: 1440px)",
    ];
    mqls = {};
    queries.forEach((q) => {
      mqls[q] = createMockMQL(matchingQueries.includes(q), q);
    });

    Object.defineProperty(window, "matchMedia", {
      writable: true,
      value: vi.fn((q: string) => mqls[q] ?? createMockMQL(false, q)),
    });
  }

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("returns 'sm' when no media queries match (viewport < 768px)", () => {
    setupMatchMedia([]);
    const { result } = renderHook(() => useBreakpoint());
    expect(result.current).toBe("sm");
  });

  it("returns 'md' when only (min-width: 768px) matches (768pxâ€“1279px)", () => {
    setupMatchMedia(["(min-width: 768px)"]);
    const { result } = renderHook(() => useBreakpoint());
    expect(result.current).toBe("md");
  });

  it("returns 'lg' when (min-width: 768px) and (min-width: 1280px) match (1280pxâ€“1439px)", () => {
    setupMatchMedia(["(min-width: 768px)", "(min-width: 1280px)"]);
    const { result } = renderHook(() => useBreakpoint());
    expect(result.current).toBe("lg");
  });

  it("returns 'xl' when all three queries match (â‰Ą1440px)", () => {
    setupMatchMedia(["(min-width: 768px)", "(min-width: 1280px)", "(min-width: 1440px)"]);
    const { result } = renderHook(() => useBreakpoint());
    expect(result.current).toBe("xl");
  });

  it("re-renders with 'md' after a resize event crosses the md threshold", () => {
    setupMatchMedia([]);
    const { result } = renderHook(() => useBreakpoint());
    expect(result.current).toBe("sm");

    act(() => {
      mqls["(min-width: 768px)"]._setMatches(true);
    });

    expect(result.current).toBe("md");
  });

  it("calls removeEventListener for all three queries on unmount", () => {
    setupMatchMedia(["(min-width: 768px)"]);
    const { unmount } = renderHook(() => useBreakpoint());

    unmount();

    const queries = [
      "(min-width: 768px)",
      "(min-width: 1280px)",
      "(min-width: 1440px)",
    ];
    queries.forEach((q) => {
      expect(mqls[q].removeEventListener).toHaveBeenCalledWith(
        "change",
        expect.any(Function),
      );
    });
  });
});
