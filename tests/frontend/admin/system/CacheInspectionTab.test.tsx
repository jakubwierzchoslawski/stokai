/**
 * Tests for CacheInspectionTab component.
 *
 * PLAN-F-030 TASK-010
 */
import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

jest.mock(
  "../../../../frontend/src/pages/admin/system/hooks/useSystemOps",
  () => ({
    useCacheStats: jest.fn(),
    useRefreshCache: jest.fn(),
  })
);

import {
  useCacheStats,
  useRefreshCache,
} from "../../../../frontend/src/pages/admin/system/hooks/useSystemOps";
import { CacheInspectionTab } from "../../../../frontend/src/pages/admin/system/CacheInspectionTab";

const mockUseStats = useCacheStats as jest.Mock;
const mockUseRefresh = useRefreshCache as jest.Mock;

const MOCK_STATS = {
  price_bars_count: 12,
  embeddings_count: 7,
  event_data_count: 3,
  total_redis_memory_bytes: 4096,
};

beforeEach(() => {
  jest.clearAllMocks();
});

describe("CacheInspectionTab", () => {
  it("renders key counts for all data types", () => {
    mockUseStats.mockReturnValue({ data: MOCK_STATS, isLoading: false, isError: false });
    mockUseRefresh.mockReturnValue({ mutateAsync: jest.fn(), isPending: false });

    render(<CacheInspectionTab />);

    expect(screen.getByTestId("key-count-price_bars").textContent).toBe("12");
    expect(screen.getByTestId("key-count-embeddings").textContent).toBe("7");
    expect(screen.getByTestId("key-count-event_data").textContent).toBe("3");
  });

  it("Force Refresh button for price_bars calls cache/refresh with correct payload", async () => {
    const refreshFn = jest.fn().mockResolvedValue({ data_type: "price_bars", keys_deleted: 12 });
    const alertMock = jest.spyOn(window, "alert").mockImplementation(() => {});

    mockUseStats.mockReturnValue({ data: MOCK_STATS, isLoading: false, isError: false });
    mockUseRefresh.mockReturnValue({ mutateAsync: refreshFn, isPending: false });

    render(<CacheInspectionTab />);

    const btn = screen.getByTestId("refresh-btn-price_bars");
    fireEvent.click(btn);

    await waitFor(() => {
      expect(refreshFn).toHaveBeenCalledWith({ data_type: "price_bars" });
    });

    alertMock.mockRestore();
  });

  it("Force Refresh for embeddings uses correct pattern", async () => {
    const refreshFn = jest.fn().mockResolvedValue({ data_type: "embeddings", keys_deleted: 7 });
    const alertMock = jest.spyOn(window, "alert").mockImplementation(() => {});

    mockUseStats.mockReturnValue({ data: MOCK_STATS, isLoading: false, isError: false });
    mockUseRefresh.mockReturnValue({ mutateAsync: refreshFn, isPending: false });

    render(<CacheInspectionTab />);

    const btn = screen.getByTestId("refresh-btn-embeddings");
    fireEvent.click(btn);

    await waitFor(() => {
      expect(refreshFn).toHaveBeenCalledWith({ data_type: "embeddings" });
    });

    alertMock.mockRestore();
  });
});
