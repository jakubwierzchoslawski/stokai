/**
 * HilQueueTable — sortable queue list with live countdown.
 *
 * Displays items sorted by scheduled_send_at ascending.
 * Columns: workflow type, user email/ID, confidence (colour-coded),
 * scheduled delivery time, live time-to-send countdown, status badge.
 * Clicking a row selects it and expands HilItemDetail.
 *
 * PLAN-F-013 TASK-008
 */
import React, { useEffect, useState } from "react";
import type { HILQueueItem } from "./useHilQueue";

// Confidence colour thresholds
const CONFIDENCE_HIGH = 0.65;
const CONFIDENCE_MID = 0.55;

function confidenceColour(confidence: number): string {
  if (confidence >= CONFIDENCE_HIGH) return "#e6a817"; // amber — borderline
  if (confidence >= CONFIDENCE_MID) return "#d97706";  // orange — moderate concern
  return "#dc2626";                                     // red — significant concern
}

function formatCountdown(targetIso: string): string {
  const target = new Date(targetIso).getTime();
  const now = Date.now();
  const diff = Math.max(0, target - now);
  if (diff === 0) return "OVERDUE";
  const totalSeconds = Math.floor(diff / 1000);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  if (hours > 0) return `${hours}h ${minutes}m ${seconds}s`;
  if (minutes > 0) return `${minutes}m ${seconds}s`;
  return `${seconds}s`;
}

function statusBadge(status: string): React.ReactElement {
  const colours: Record<string, string> = {
    pending: "#3b82f6",
    approved: "#16a34a",
    edited_approved: "#059669",
    rejected: "#dc2626",
    timed_out: "#6b7280",
  };
  return (
    <span
      style={{
        backgroundColor: colours[status] ?? "#6b7280",
        color: "#fff",
        padding: "2px 8px",
        borderRadius: 4,
        fontSize: 12,
        fontWeight: 600,
        textTransform: "uppercase",
      }}
    >
      {status.replace("_", " ")}
    </span>
  );
}

export interface HilQueueTableProps {
  items: HILQueueItem[];
  selectedItemId: string | null;
  onSelectItem: (itemId: string | null) => void;
}

export const HilQueueTable: React.FC<HilQueueTableProps> = ({
  items,
  selectedItemId,
  onSelectItem,
}) => {
  const [, setTick] = useState(0);

  // Live countdown: re-render every second
  useEffect(() => {
    const interval = setInterval(() => setTick((t) => t + 1), 1000);
    return () => clearInterval(interval);
  }, []);

  // Sort by scheduled_send_at ascending (most urgent first)
  const sorted = [...items].sort(
    (a, b) =>
      new Date(a.scheduled_send_at).getTime() -
      new Date(b.scheduled_send_at).getTime(),
  );

  if (sorted.length === 0) {
    return (
      <div className="hil-empty" data-testid="hil-empty">
        No items pending review.
      </div>
    );
  }

  return (
    <table
      className="hil-queue-table"
      data-testid="hil-queue-table"
      style={{ width: "100%", borderCollapse: "collapse" }}
    >
      <thead>
        <tr>
          <th>Type</th>
          <th>User</th>
          <th>Confidence</th>
          <th>Scheduled Send</th>
          <th>Time Remaining</th>
          <th>Status</th>
        </tr>
      </thead>
      <tbody>
        {sorted.map((item) => (
          <tr
            key={item.item_id}
            data-testid={`hil-row-${item.item_id}`}
            onClick={() =>
              onSelectItem(item.item_id === selectedItemId ? null : item.item_id)
            }
            style={{
              cursor: "pointer",
              backgroundColor:
                item.item_id === selectedItemId ? "#eff6ff" : "transparent",
            }}
          >
            <td>{item.workflow_type.replace("_", " ")}</td>
            <td style={{ fontSize: 12, color: "#6b7280" }}>
              {item.user_id.slice(0, 8)}…
            </td>
            <td>
              <span
                data-testid={`confidence-${item.item_id}`}
                style={{
                  color: confidenceColour(item.confidence),
                  fontWeight: 700,
                }}
              >
                {(item.confidence * 100).toFixed(0)}%
              </span>
            </td>
            <td style={{ fontSize: 12 }}>
              {new Date(item.scheduled_send_at).toLocaleTimeString()}
            </td>
            <td
              data-testid={`countdown-${item.item_id}`}
              style={{
                fontFamily: "monospace",
                color:
                  new Date(item.scheduled_send_at).getTime() <= Date.now()
                    ? "#dc2626"
                    : "inherit",
              }}
            >
              {formatCountdown(item.scheduled_send_at)}
            </td>
            <td>{statusBadge(item.status)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
};
