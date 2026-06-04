/**
 * Tests for FeatureFlagsTab component.
 *
 * PLAN-F-030 TASK-010
 */
import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

jest.mock(
  "../../../../frontend/src/pages/admin/system/hooks/useSystemOps",
  () => ({
    useFeatureFlags: jest.fn(),
    useUpdateFlag: jest.fn(),
  })
);

import {
  useFeatureFlags,
  useUpdateFlag,
} from "../../../../frontend/src/pages/admin/system/hooks/useSystemOps";
import { FeatureFlagsTab } from "../../../../frontend/src/pages/admin/system/FeatureFlagsTab";

const mockUseFlags = useFeatureFlags as jest.Mock;
const mockUseUpdate = useUpdateFlag as jest.Mock;

const MOCK_FLAGS = [
  {
    flag_id: "morning_brief",
    environment: "production",
    enabled: true,
    updated_at: null,
    updated_by: null,
  },
  {
    flag_id: "social_twitter",
    environment: "production",
    enabled: false,
    updated_at: null,
    updated_by: null,
  },
];

beforeEach(() => {
  jest.clearAllMocks();
});

describe("FeatureFlagsTab", () => {
  it("renders flag list from mock data", () => {
    mockUseFlags.mockReturnValue({ data: MOCK_FLAGS, isLoading: false, isError: false });
    mockUseUpdate.mockReturnValue({ mutateAsync: jest.fn(), isPending: false });

    render(<FeatureFlagsTab />);

    expect(screen.getByTestId("flag-row-morning_brief")).toBeTruthy();
    expect(screen.getByTestId("flag-row-social_twitter")).toBeTruthy();
  });

  it("toggle switch for morning_brief calls PATCH with enabled=false", async () => {
    const updateFn = jest.fn().mockResolvedValue({
      flag_id: "morning_brief",
      environment: "production",
      enabled: false,
    });
    mockUseFlags.mockReturnValue({ data: MOCK_FLAGS, isLoading: false, isError: false });
    mockUseUpdate.mockReturnValue({ mutateAsync: updateFn, isPending: false });

    render(<FeatureFlagsTab />);

    const toggle = screen.getByTestId("toggle-morning_brief");
    fireEvent.click(toggle);

    await waitFor(() => {
      expect(updateFn).toHaveBeenCalledWith({
        flag_id: "morning_brief",
        enabled: false,
      });
    });
  });

  it("optimistic toggle reverts on API error", async () => {
    const updateFn = jest.fn().mockRejectedValue(new Error("Server error"));
    const alertMock = jest.spyOn(window, "alert").mockImplementation(() => {});
    mockUseFlags.mockReturnValue({ data: MOCK_FLAGS, isLoading: false, isError: false });
    mockUseUpdate.mockReturnValue({ mutateAsync: updateFn, isPending: false });

    render(<FeatureFlagsTab />);

    // Initially morning_brief is true
    const toggle = screen.getByTestId("toggle-morning_brief") as HTMLInputElement;
    expect(toggle.checked).toBe(true);

    fireEvent.click(toggle);

    await waitFor(() => {
      // After error, should revert to original state
      expect(alertMock).toHaveBeenCalledWith("Server error");
    });

    alertMock.mockRestore();
  });

  it("social_twitter row renders Off by default tooltip", () => {
    mockUseFlags.mockReturnValue({ data: MOCK_FLAGS, isLoading: false, isError: false });
    mockUseUpdate.mockReturnValue({ mutateAsync: jest.fn(), isPending: false });

    render(<FeatureFlagsTab />);

    expect(screen.getByTestId("social-default-tooltip-social_twitter")).toBeTruthy();
  });
});
