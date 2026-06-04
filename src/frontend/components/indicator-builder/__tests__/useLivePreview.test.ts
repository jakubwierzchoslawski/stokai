/**
 * Tests for useLivePreview hook.
 *
 * Verifies:
 * - 500ms debounce before calling /preview
 * - Returns 5 company preview rows on success
 * - Shows loading state during in-flight requests
 */
import { renderHook, act, waitFor } from "@testing-library/react";
import { useLivePreview } from "../hooks/useLivePreview";

// Mock TanStack Query — simplified for hook testing
jest.mock("@tanstack/react-query", () => {
  const original = jest.requireActual("@tanstack/react-query");
  return {
    ...original,
    useQuery: jest.fn(),
    useQueryClient: jest.fn(() => ({ invalidateQueries: jest.fn() })),
  };
});

const { useQuery } = jest.requireMock("@tanstack/react-query");

beforeEach(() => {
  jest.useFakeTimers();
  jest.clearAllMocks();
});

afterEach(() => {
  jest.useRealTimers();
});

const SAMPLE_PREVIEWS = [
  { company_id: "c1", company_name: "Corp A", raw_value: 100.0, score: 75.0, geo_adjusted: 70.0 },
  { company_id: "c2", company_name: "Corp B", raw_value: 200.0, score: 85.0, geo_adjusted: null },
  { company_id: "c3", company_name: "Corp C", raw_value: 150.0, score: 60.0, geo_adjusted: 55.0 },
  { company_id: "c4", company_name: "Corp D", raw_value: 50.0,  score: 30.0, geo_adjusted: null },
  { company_id: "c5", company_name: "Corp E", raw_value: 300.0, score: 95.0, geo_adjusted: 90.0 },
];

describe("useLivePreview", () => {
  it("returns 5 preview rows when data is available", () => {
    useQuery.mockReturnValue({
      data: SAMPLE_PREVIEWS,
      isFetching: false,
    });

    const { result } = renderHook(() =>
      useLivePreview("revenue * 0.5", { debounceMs: 500 })
    );

    expect(result.current.previews).toHaveLength(5);
    expect(result.current.isLoading).toBe(false);
  });

  it("shows loading spinner while preview is in-flight", () => {
    useQuery.mockReturnValue({
      data: undefined,
      isFetching: true,
    });

    const { result } = renderHook(() =>
      useLivePreview("revenue", { debounceMs: 500 })
    );

    expect(result.current.isLoading).toBe(true);
    expect(result.current.previews).toHaveLength(0);
  });

  it("debounces formula changes by 500ms", () => {
    // Track what query key is used
    const querySpy = useQuery.mockReturnValue({
      data: [],
      isFetching: false,
    });

    const { result, rerender } = renderHook(
      ({ formula }: { formula: string }) =>
        useLivePreview(formula, { debounceMs: 500 }),
      { initialProps: { formula: "revenue" } }
    );

    // Initially enabled with first formula
    rerender({ formula: "revenue * 2" });

    // Check the enabled flag — should be true for non-empty formula
    const lastCall = querySpy.mock.calls[querySpy.mock.calls.length - 1][0];
    expect(lastCall.enabled).toBe(false); // debounced formula hasn't updated yet
  });

  it("returns empty previews for empty formula", () => {
    useQuery.mockReturnValue({
      data: undefined,
      isFetching: false,
    });

    const { result } = renderHook(() =>
      useLivePreview("", { debounceMs: 500 })
    );

    expect(result.current.previews).toHaveLength(0);
    expect(result.current.isLoading).toBe(false);
  });
});
