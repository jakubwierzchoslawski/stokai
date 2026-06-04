/**
 * HilQueueTable tests — PLAN-F-013 TASK-008
 *
 * Covers:
 *   - Items rendered sorted by scheduled_send_at
 *   - Live countdown is displayed
 *   - Confidence shown colour-coded
 */
import React from "react";
import { render, screen } from "@testing-library/react";
import { HilQueueTable } from "./HilQueueTable";
import type { HILQueueItem } from "./useHilQueue";

function makeItem(overrides: Partial<HILQueueItem> = {}): HILQueueItem {
  const now = new Date();
  const future = new Date(now.getTime() + 3600_000).toISOString();
  return {
    item_id: "item-1",
    workflow_run_id: "wfr-1",
    workflow_type: "on_demand",
    user_id: "user-1",
    tenant_id: "tenant-1",
    confidence: 0.55,
    scheduled_send_at: future,
    status: "pending",
    reviewer_id: null,
    reviewed_at: null,
    lc_checkpoint_id: "hil:wfr-1",
    created_at: now.toISOString(),
    ...overrides,
  };
}

describe("HilQueueTable", () => {
  it("renders items sorted by scheduled_send_at ascending", () => {
    const now = Date.now();
    const item1 = makeItem({
      item_id: "item-1",
      scheduled_send_at: new Date(now + 7200_000).toISOString(),
    });
    const item2 = makeItem({
      item_id: "item-2",
      scheduled_send_at: new Date(now + 3600_000).toISOString(),
    });

    render(
      <HilQueueTable
        items={[item1, item2]}
        selectedItemId={null}
        onSelectItem={() => {}}
      />,
    );

    const rows = screen.getAllByTestId(/hil-row-/);
    expect(rows[0]).toHaveAttribute("data-testid", "hil-row-item-2");
    expect(rows[1]).toHaveAttribute("data-testid", "hil-row-item-1");
  });

  it("displays countdown for each item", () => {
    const item = makeItem({ item_id: "item-1" });
    render(
      <HilQueueTable
        items={[item]}
        selectedItemId={null}
        onSelectItem={() => {}}
      />,
    );

    const countdown = screen.getByTestId("countdown-item-1");
    expect(countdown.textContent).toMatch(/\d+[hms]/);
  });

  it("shows confidence value colour-coded via data-testid", () => {
    const item = makeItem({ item_id: "item-1", confidence: 0.42 });
    render(
      <HilQueueTable
        items={[item]}
        selectedItemId={null}
        onSelectItem={() => {}}
      />,
    );

    const confEl = screen.getByTestId("confidence-item-1");
    expect(confEl.textContent).toBe("42%");
    // Red for low confidence
    expect(confEl).toHaveStyle({ color: "#dc2626" });
  });
});
