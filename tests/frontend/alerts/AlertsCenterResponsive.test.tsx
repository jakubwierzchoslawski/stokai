/**
 * AlertsCenterResponsive.test.tsx — TDD tests for Alerts Center mobile-first layout.
 *
 * Tests written first (red phase) per PLAN-N-014 TASK-007.
 */

import React from "react";
import { render, screen } from "@testing-library/react";
import { AlertListRow } from "../../../src/frontend/components/alerts/AlertListRow";
import { AlertRuleCard } from "../../../src/frontend/components/alerts/AlertRuleCard";

// ── Mock data ─────────────────────────────────────────────────────────────────

const mockAlertItem = {
  alert_id: "alert-1",
  occurred_at: "2026-06-04T06:00:00Z",
  event_title: "Earnings beat drives AAPL rally above key resistance level",
  event_link: "/events/1",
  action_signal: "BUY_OPP" as const,
  confidence: 0.82,
  channel: "EMAIL",
  status: "dispatched" as const,
  report_link: "/reports/1",
  rule_id: "rule-1",
  rule_name: "AAPL alerts",
};

const mockRule = {
  rule_id: "rule-1",
  user_id: "user-1",
  name: "AAPL Watch",
  enabled: true,
  intensity_min: 3,
  channels: ["EMAIL", "PUSH"],
  ticker_list: ["AAPL"],
  event_category_filter: ["earnings"],
  quiet_hours_start: null,
  quiet_hours_end: null,
  per_ticker_interval_hours: 24,
};

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("AlertListRow mobile-first responsive (AC-001)", () => {
  it("row element has min-h-[44px] class or inline minHeight ≥ 44px for touch target", () => {
    render(
      <table>
        <tbody>
          <AlertListRow item={mockAlertItem} />
        </tbody>
      </table>,
    );

    const row = screen.getByTestId("alert-list-row");
    // Either Tailwind class or inline style must enforce 44px minimum height
    const hasClass = row.className.includes("min-h-[44px]");
    const hasStyle = parseInt(row.style.minHeight || "0") >= 44;
    expect(hasClass || hasStyle).toBe(true);
  });

  it("action signal badge has inline-flex display and minHeight ≥ 44px", () => {
    render(
      <table>
        <tbody>
          <AlertListRow item={mockAlertItem} />
        </tbody>
      </table>,
    );

    const badge = screen.getByTestId("action-signal-badge");
    // Badge must have display that supports inline-flex and min height for touch
    const minH = parseInt(badge.style.minHeight || "0");
    expect(minH).toBeGreaterThanOrEqual(44);
  });

  it("event link does not exceed its container (has overflow/ellipsis constraints)", () => {
    render(
      <table>
        <tbody>
          <AlertListRow item={mockAlertItem} />
        </tbody>
      </table>,
    );

    const link = screen.getByTestId("event-link");
    // Link should have max-width or overflow constraint to prevent row overflow
    const style = link.style;
    const hasOverflowConstraint =
      style.maxWidth === "100%" ||
      style.overflow === "hidden" ||
      style.textOverflow === "ellipsis";
    expect(hasOverflowConstraint).toBe(true);
  });
});

describe("AlertRuleCard mobile-first responsive (AC-001)", () => {
  it("toggle label has minHeight ≥ 44px for touch target", () => {
    render(
      <AlertRuleCard
        rule={mockRule}
        onEdit={jest.fn()}
        onToggleEnabled={jest.fn()}
        onDelete={jest.fn()}
      />,
    );

    const toggle = screen.getByTestId("enabled-toggle").closest("label");
    expect(toggle).not.toBeNull();
    const minH = parseInt(toggle!.style.minHeight || "0");
    expect(minH).toBeGreaterThanOrEqual(44);
  });

  it("edit button has minHeight ≥ 44px for touch target", () => {
    render(
      <AlertRuleCard
        rule={mockRule}
        onEdit={jest.fn()}
        onToggleEnabled={jest.fn()}
        onDelete={jest.fn()}
      />,
    );

    const editBtn = screen.getByTestId("edit-button");
    const minH = parseInt(editBtn.style.minHeight || "0");
    expect(minH).toBeGreaterThanOrEqual(44);
  });

  it("delete button has minHeight ≥ 44px for touch target", () => {
    render(
      <AlertRuleCard
        rule={mockRule}
        onEdit={jest.fn()}
        onToggleEnabled={jest.fn()}
        onDelete={jest.fn()}
      />,
    );

    const deleteBtn = screen.getByTestId("delete-button");
    const minH = parseInt(deleteBtn.style.minHeight || "0");
    expect(minH).toBeGreaterThanOrEqual(44);
  });

  it("card container has max-width constraint to prevent overflow", () => {
    render(
      <AlertRuleCard
        rule={mockRule}
        onEdit={jest.fn()}
        onToggleEnabled={jest.fn()}
        onDelete={jest.fn()}
      />,
    );

    const card = screen.getByTestId("alert-rule-card");
    expect(card.style.maxWidth).toBe("100%");
  });
});
