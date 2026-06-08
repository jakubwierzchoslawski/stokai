/**
 * HilItemDetail — expandable item detail panel.
 *
 * Shows:
 *   - Full report preview (WorkflowState.report.content)
 *   - Per-node confidence breakdown (state.confidence_scores)
 *   - Key concerns from WorkflowState.hil_reason
 *
 * PLAN-F-013 TASK-008
 */
import React from "react";
import type { HILQueueItem } from "./useHilQueue";

export interface HilItemDetailProps {
  item: HILQueueItem;
}

export const HilItemDetail: React.FC<HilItemDetailProps> = ({ item }) => {
  const reportContent =
    (item.report?.content as string | undefined) ??
    "(No report preview available)";

  const confidenceScores = item.confidence_scores ?? {};
  const hasScores = Object.keys(confidenceScores).length > 0;

  return (
    <div
      className="hil-item-detail"
      data-testid={`hil-item-detail-${item.item_id}`}
    >
      {/* Key concerns */}
      {item.hil_reason && (
        <section className="hil-detail-section" aria-label="Key concerns">
          <h3>Key Concerns</h3>
          <p
            className="hil-hil-reason"
            data-testid="hil-reason"
            style={{
              color: "#b45309",
              backgroundColor: "#fffbeb",
              padding: "8px 12px",
              borderLeft: "4px solid #d97706",
              borderRadius: 4,
            }}
          >
            {item.hil_reason}
          </p>
        </section>
      )}

      {/* Per-node confidence breakdown */}
      {hasScores && (
        <section
          className="hil-detail-section"
          aria-label="Confidence breakdown"
        >
          <h3>Confidence Breakdown</h3>
          <table
            style={{ width: "100%", fontSize: 13 }}
            data-testid="confidence-breakdown"
          >
            <tbody>
              {Object.entries(confidenceScores).map(([node, score]) => (
                <tr key={node}>
                  <td style={{ paddingRight: 16, color: "#6b7280" }}>{node}</td>
                  <td
                    style={{
                      fontWeight: 600,
                      color: score < 0.5 ? "#dc2626" : "#d97706",
                    }}
                  >
                    {(score * 100).toFixed(0)}%
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {/* Full report preview */}
      <section className="hil-detail-section" aria-label="Report preview">
        <h3>Report Preview</h3>
        <pre
          className="hil-report-preview"
          data-testid="report-preview"
          style={{
            backgroundColor: "#f9fafb",
            border: "1px solid #e5e7eb",
            borderRadius: 6,
            padding: 12,
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
            fontSize: 13,
            maxHeight: 400,
            overflowY: "auto",
          }}
        >
          {reportContent}
        </pre>
      </section>
    </div>
  );
};
