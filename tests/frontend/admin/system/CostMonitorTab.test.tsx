/**
 * Tests for CostMonitorTab component.
 *
 * PLAN-F-030 TASK-009
 */
import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

jest.mock(
  "../../../../frontend/src/pages/admin/system/hooks/useSystemOps",
  () => ({
    useCostSummary: jest.fn(),
    useUpdateThreshold: jest.fn(),
  })
);

import { useCostSummary, useUpdateThreshold } from "../../../../frontend/src/pages/admin/system/hooks/useSystemOps";
import { CostMonitorTab } from "../../../../frontend/src/pages/admin/system/CostMonitorTab";

const mockUseCostSummary = useCostSummary as jest.Mock;
const mockUseUpdateThreshold = useUpdateThreshold as jest.Mock;

const mockUpdateFn = jest.fn();

beforeEach(() => {
  jest.clearAllMocks();
  mockUseUpdateThreshold.mockReturnValue({
    mutateAsync: mockUpdateFn,
    isPending: false,
  });
});

const MOCK_COST = {
  spend_usd: 42.5,
  threshold_usd: 100.0,
  pct_used: 42.5,
  warning_active: false,
  hard_stop_active: false,
  by_source: [{ source: "openai", total_cost_usd: 42.5 }],
  by_model: [],
  by_workflow: [],
  daily_totals: [],
};

describe("CostMonitorTab", () => {
  it("renders budget gauge with correct percentage from mock data", () => {
    mockUseCostSummary.mockReturnValue({
      data: MOCK_COST,
      isLoading: false,
      isError: false,
    });

    render(<CostMonitorTab />);

    expect(screen.getByTestId("budget-pct").textContent).toContain("42.5");
  });

  it("renders hard-stop banner when hard_stop_active is true", () => {
    mockUseCostSummary.mockReturnValue({
      data: { ...MOCK_COST, hard_stop_active: true, pct_used: 100 },
      isLoading: false,
      isError: false,
    });

    render(<CostMonitorTab />);

    expect(screen.getByTestId("hard-stop-banner")).toBeTruthy();
  });

  it("does not render hard-stop banner when hard_stop_active is false", () => {
    mockUseCostSummary.mockReturnValue({
      data: MOCK_COST,
      isLoading: false,
      isError: false,
    });

    render(<CostMonitorTab />);

    expect(screen.queryByTestId("hard-stop-banner")).toBeNull();
  });

  it("updating threshold calls PATCH /cost/threshold with new value", async () => {
    mockUseCostSummary.mockReturnValue({
      data: MOCK_COST,
      isLoading: false,
      isError: false,
    });

    mockUpdateFn.mockResolvedValue({ threshold_usd: 80.0 });
    const alertMock = jest.spyOn(window, "alert").mockImplementation(() => {});

    render(<CostMonitorTab />);

    const input = screen.getByTestId("threshold-input");
    fireEvent.change(input, { target: { value: "80" } });

    const saveBtn = screen.getByTestId("save-threshold-btn");
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(mockUpdateFn).toHaveBeenCalledWith(80);
    });

    alertMock.mockRestore();
  });
});
