import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
/**
 * Tests for useFormulaValidation hook.
 *
 * Verifies:
 * - 300ms debounce before calling /validate
 * - Empty string does NOT trigger a call
 * - Error annotations surfaced correctly
 */
import { renderHook, act, waitFor } from "@testing-library/react";
import { useFormulaValidation } from "../hooks/useFormulaValidation";

// Mock global fetch
const mockFetch = vi.fn();
global.fetch = mockFetch;

beforeEach(() => {
  vi.useFakeTimers();
  mockFetch.mockClear();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("useFormulaValidation", () => {
  it("does not call /validate on empty string", () => {
    const { result } = renderHook(() => useFormulaValidation());

    act(() => {
      result.current.validate("");
    });

    // Advance timers past debounce window
    act(() => {
      vi.advanceTimersByTime(500);
    });

    expect(mockFetch).not.toHaveBeenCalled();
  });

  it("does not call /validate on whitespace-only string", () => {
    const { result } = renderHook(() => useFormulaValidation());

    act(() => {
      result.current.validate("   ");
    });

    act(() => {
      vi.advanceTimersByTime(500);
    });

    expect(mockFetch).not.toHaveBeenCalled();
  });

  it("calls /validate after 300ms debounce with a valid formula", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ data: { valid: true, errors: [] } }),
    } as Response);

    const { result } = renderHook(() =>
      useFormulaValidation({ debounceMs: 300 })
    );

    act(() => {
      result.current.validate("revenue * 0.5");
    });

    // Not called before debounce window
    expect(mockFetch).not.toHaveBeenCalled();

    // Advance past 300ms
    act(() => {
      vi.advanceTimersByTime(350);
    });

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledTimes(1);
    });

    expect(mockFetch).toHaveBeenCalledWith(
      "/api/v1/indicators/validate",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ formula_dsl: "revenue * 0.5" }),
      })
    );
  });

  it("debounces rapid calls â€” only the last call is made", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({ data: { valid: true, errors: [] } }),
    } as Response);

    const { result } = renderHook(() =>
      useFormulaValidation({ debounceMs: 300 })
    );

    act(() => {
      result.current.validate("r");
      result.current.validate("re");
      result.current.validate("rev");
      result.current.validate("reve");
      result.current.validate("reven");
      result.current.validate("revenue");
    });

    act(() => {
      vi.advanceTimersByTime(400);
    });

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledTimes(1);
    });
  });

  it("returns validationResult with errors when formula is invalid", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        data: {
          valid: false,
          errors: ["Unknown parameter: foo"],
        },
      }),
    } as Response);

    const { result } = renderHook(() =>
      useFormulaValidation({ debounceMs: 100 })
    );

    act(() => {
      result.current.validate("foo * 2");
    });

    act(() => {
      vi.advanceTimersByTime(150);
    });

    await waitFor(() => {
      expect(result.current.validationResult).not.toBeNull();
    });

    expect(result.current.validationResult?.valid).toBe(false);
    expect(result.current.validationResult?.errors).toContain(
      "Unknown parameter: foo"
    );
  });
});
