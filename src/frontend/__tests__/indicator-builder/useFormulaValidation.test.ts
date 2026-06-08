/**
 * Tests for useFormulaValidation hook (TDD â€” written before implementation).
 *
 * Uses vitest + @testing-library/react-hooks.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { useFormulaValidation } from "../../features/indicator-builder/hooks/useFormulaValidation";

// Mock fetch globally
const mockFetch = vi.fn();
globalThis.fetch = mockFetch;

describe("useFormulaValidation", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    mockFetch.mockClear();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("does not call /validate on empty string", async () => {
    const { result } = renderHook(() =>
      useFormulaValidation({ debounceMs: 300 })
    );

    act(() => {
      result.current.validate("");
    });

    // Advance past debounce window
    await act(async () => {
      vi.advanceTimersByTime(400);
    });

    expect(mockFetch).not.toHaveBeenCalled();
  });

  it("does not call /validate on whitespace-only string", async () => {
    const { result } = renderHook(() =>
      useFormulaValidation({ debounceMs: 300 })
    );

    act(() => {
      result.current.validate("   ");
    });

    await act(async () => {
      vi.advanceTimersByTime(400);
    });

    expect(mockFetch).not.toHaveBeenCalled();
  });

  it("calls /validate with 300ms debounce on non-empty formula", async () => {
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

    // Before debounce â€” should not have called yet
    expect(mockFetch).not.toHaveBeenCalled();

    // Advance past debounce window
    await act(async () => {
      vi.advanceTimersByTime(350);
    });

    expect(mockFetch).toHaveBeenCalledWith(
      "/api/v1/indicators/validate",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ formula_dsl: "revenue * 0.5" }),
      })
    );
  });

  it("debounces rapid consecutive calls â€” only last call fires", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ data: { valid: true, errors: [] } }),
    } as Response);

    const { result } = renderHook(() =>
      useFormulaValidation({ debounceMs: 300 })
    );

    // Rapid-fire updates
    act(() => {
      result.current.validate("r");
    });
    vi.advanceTimersByTime(100);

    act(() => {
      result.current.validate("re");
    });
    vi.advanceTimersByTime(100);

    act(() => {
      result.current.validate("revenue");
    });

    // Advance past debounce
    await act(async () => {
      vi.advanceTimersByTime(350);
    });

    // Only one call â€” the last one
    expect(mockFetch).toHaveBeenCalledTimes(1);
    expect(mockFetch).toHaveBeenCalledWith(
      "/api/v1/indicators/validate",
      expect.objectContaining({
        body: JSON.stringify({ formula_dsl: "revenue" }),
      })
    );
  });

  it("sets validationResult to valid=true on successful response", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ data: { valid: true, errors: [] } }),
    } as Response);

    const { result } = renderHook(() =>
      useFormulaValidation({ debounceMs: 300 })
    );

    act(() => {
      result.current.validate("revenue");
    });

    await act(async () => {
      vi.advanceTimersByTime(400);
    });

    await waitFor(() => {
      expect(result.current.validationResult?.valid).toBe(true);
    });
    expect(result.current.validationResult?.errors).toEqual([]);
  });

  it("sets validationResult with errors on failed validation", async () => {
    const errors = ["Unknown parameter: bad_param"];
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ data: { valid: false, errors } }),
    } as Response);

    const { result } = renderHook(() =>
      useFormulaValidation({ debounceMs: 300 })
    );

    act(() => {
      result.current.validate("bad_param * 0.5");
    });

    await act(async () => {
      vi.advanceTimersByTime(400);
    });

    await waitFor(() => {
      expect(result.current.validationResult?.valid).toBe(false);
    });
    expect(result.current.validationResult?.errors).toEqual(errors);
  });
});
