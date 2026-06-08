import { describe, it, expect, vi } from 'vitest';
/**
 * HilActionButtons tests â€” PLAN-F-013 TASK-008
 *
 * Covers:
 *   - Approve button calls onAction with action='approve'
 *   - Edit & Approve reveals textarea
 *   - Reject with feedback reveals feedback input
 */
import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { HilActionButtons } from "./HilActionButtons";
import type { HILQueueItem } from "./useHilQueue";

function makeItem(): HILQueueItem {
  return {
    item_id: "item-1",
    workflow_run_id: "wfr-1",
    workflow_type: "on_demand",
    user_id: "user-1",
    tenant_id: "tenant-1",
    confidence: 0.55,
    scheduled_send_at: new Date(Date.now() + 3600_000).toISOString(),
    status: "pending",
    reviewer_id: null,
    reviewed_at: null,
    lc_checkpoint_id: "hil:wfr-1",
    created_at: new Date().toISOString(),
    report: { content: "Test report content." },
  };
}

describe("HilActionButtons", () => {
  it("calls onAction with action='approve' when Approve button clicked", async () => {
    const mockAction = vi.fn().mockResolvedValue(undefined);
    render(<HilActionButtons item={makeItem()} onAction={mockAction} />);

    fireEvent.click(screen.getByTestId("btn-approve"));

    await waitFor(() => {
      expect(mockAction).toHaveBeenCalledWith("approve", undefined);
    });
  });

  it("reveals textarea when Edit & Approve button clicked", () => {
    render(
      <HilActionButtons item={makeItem()} onAction={vi.fn().mockResolvedValue(undefined)} />,
    );

    expect(screen.queryByTestId("edit-approve-panel")).toBeNull();
    fireEvent.click(screen.getByTestId("btn-edit-approve"));
    expect(screen.getByTestId("edit-approve-panel")).toBeTruthy();
    expect(screen.getByTestId("edited-text-input")).toBeTruthy();
  });

  it("pre-fills edit textarea with report content", () => {
    render(
      <HilActionButtons item={makeItem()} onAction={vi.fn().mockResolvedValue(undefined)} />,
    );

    fireEvent.click(screen.getByTestId("btn-edit-approve"));
    const textarea = screen.getByTestId("edited-text-input") as HTMLTextAreaElement;
    expect(textarea.value).toBe("Test report content.");
  });

  it("reveals feedback input when Reject with feedback clicked", () => {
    render(
      <HilActionButtons item={makeItem()} onAction={vi.fn().mockResolvedValue(undefined)} />,
    );

    expect(screen.queryByTestId("reject-feedback-panel")).toBeNull();
    fireEvent.click(screen.getByTestId("btn-reject-feedback"));
    expect(screen.getByTestId("reject-feedback-panel")).toBeTruthy();
    expect(screen.getByTestId("feedback-text-input")).toBeTruthy();
  });
});
