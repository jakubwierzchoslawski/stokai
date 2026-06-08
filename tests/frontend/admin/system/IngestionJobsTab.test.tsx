import { describe, it, expect, vi, beforeEach , type Mock } from 'vitest';
/**
 * Tests for IngestionJobsTab component.
 *
 * PLAN-F-030 TASK-009
 */
import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

// Mock the hooks module
vi.mock(
  "@/pages/admin/system/hooks/useSystemOps",
  () => ({
    useIngestionJobs: vi.fn(),
    useTriggerJob: vi.fn(),
  })
);

import { useIngestionJobs, useTriggerJob } from "@/pages/admin/system/hooks/useSystemOps";
import { IngestionJobsTab } from "@/pages/admin/system/IngestionJobsTab";

const mockUseIngestionJobs = useIngestionJobs as Mock;
const mockUseTriggerJob = useTriggerJob as Mock;

const MOCK_JOBS = [
  {
    job_id: "job-001",
    name: "Edgar Ingest",
    schedule: "0 * * * *",
    last_run: null,
    next_run: null,
    status: "idle" as const,
    error_count: 0,
    last_error_trace: null,
    updated_at: new Date().toISOString(),
  },
  {
    job_id: "job-002",
    name: "Price Bar Fetch",
    schedule: "*/15 * * * *",
    last_run: null,
    next_run: null,
    status: "failed" as const,
    error_count: 3,
    last_error_trace: "Connection timeout",
    updated_at: new Date().toISOString(),
  },
];

const mockTriggerFn = vi.fn();

beforeEach(() => {
  vi.clearAllMocks();
  mockUseTriggerJob.mockReturnValue({
    mutateAsync: mockTriggerFn,
    isPending: false,
  });
});

describe("IngestionJobsTab", () => {
  it("renders job list from mock data", () => {
    mockUseIngestionJobs.mockReturnValue({
      data: MOCK_JOBS,
      isLoading: false,
      isError: false,
    });

    render(<IngestionJobsTab />);

    expect(screen.getByText("Edgar Ingest")).toBeTruthy();
    expect(screen.getByText("Price Bar Fetch")).toBeTruthy();
  });

  it("renders Manual Trigger button visible per row", () => {
    mockUseIngestionJobs.mockReturnValue({
      data: MOCK_JOBS,
      isLoading: false,
      isError: false,
    });

    render(<IngestionJobsTab />);

    const triggerButtons = screen.getAllByText("Manual Trigger");
    expect(triggerButtons.length).toBe(MOCK_JOBS.length);
  });

  it("clicking trigger calls POST trigger endpoint", async () => {
    mockUseIngestionJobs.mockReturnValue({
      data: [MOCK_JOBS[0]],
      isLoading: false,
      isError: false,
    });

    mockTriggerFn.mockResolvedValue({ job_id: "job-001", task_id: "task-abc", status: "running" });
    // mock alert
    const alertMock = vi.spyOn(window, "alert").mockImplementation(() => {});

    render(<IngestionJobsTab />);

    const triggerBtn = screen.getByTestId("trigger-btn-job-001");
    fireEvent.click(triggerBtn);

    await waitFor(() => {
      expect(mockTriggerFn).toHaveBeenCalledWith("job-001");
    });

    alertMock.mockRestore();
  });

  it("trigger button is disabled when status is running", () => {
    const runningJob = { ...MOCK_JOBS[0], status: "running" as const };
    mockUseIngestionJobs.mockReturnValue({
      data: [runningJob],
      isLoading: false,
      isError: false,
    });

    render(<IngestionJobsTab />);

    const btn = screen.getByTestId("trigger-btn-job-001");
    expect(btn).toBeDisabled();
  });

  it("status=failed row shows red badge", () => {
    mockUseIngestionJobs.mockReturnValue({
      data: [MOCK_JOBS[1]],
      isLoading: false,
      isError: false,
    });

    render(<IngestionJobsTab />);

    expect(screen.getByTestId("status-badge-failed")).toBeTruthy();
    expect(screen.getByTestId("error-count-job-002").textContent).toBe("3");
  });
});
