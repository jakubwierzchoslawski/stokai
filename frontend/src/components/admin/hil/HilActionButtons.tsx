/**
 * HilActionButtons — four reviewer action buttons with inline inputs.
 *
 * Actions:
 *   Approve             — immediate submit
 *   Edit & Approve      — reveals inline textarea (pre-filled with report text)
 *   Reject              — immediate submit
 *   Reject with feedback — reveals feedback textarea
 *
 * Calls onAction({ action, edited_text?, feedback_text? }) on submit.
 *
 * PLAN-F-013 TASK-008
 */
import React, { useState } from "react";
import type { HILQueueItem } from "./useHilQueue";

export interface HilActionButtonsProps {
  item: HILQueueItem;
  onAction: (
    action: "approve" | "edit_approve" | "reject" | "reject_with_feedback",
    extras?: { edited_text?: string; feedback_text?: string },
  ) => Promise<void>;
}

export const HilActionButtons: React.FC<HilActionButtonsProps> = ({
  item,
  onAction,
}) => {
  const [mode, setMode] = useState<
    null | "edit_approve" | "reject_with_feedback"
  >(null);
  const [editedText, setEditedText] = useState(
    (item.report?.content as string | undefined) ?? "",
  );
  const [feedbackText, setFeedbackText] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(
    action: "approve" | "edit_approve" | "reject" | "reject_with_feedback",
    extras?: { edited_text?: string; feedback_text?: string },
  ) {
    setSubmitting(true);
    try {
      await onAction(action, extras);
    } finally {
      setSubmitting(false);
      setMode(null);
    }
  }

  return (
    <div
      className="hil-action-buttons"
      data-testid="hil-action-buttons"
    >
      {/* ── Primary action row ─────────────────────────────────────────── */}
      <div className="hil-action-row" style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <button
          data-testid="btn-approve"
          disabled={submitting}
          onClick={() => handleSubmit("approve")}
          style={{ backgroundColor: "#16a34a", color: "#fff", padding: "8px 16px", borderRadius: 4, border: "none", cursor: "pointer" }}
        >
          Approve
        </button>

        <button
          data-testid="btn-edit-approve"
          disabled={submitting}
          onClick={() => setMode(mode === "edit_approve" ? null : "edit_approve")}
          style={{ backgroundColor: "#2563eb", color: "#fff", padding: "8px 16px", borderRadius: 4, border: "none", cursor: "pointer" }}
        >
          Edit &amp; Approve
        </button>

        <button
          data-testid="btn-reject"
          disabled={submitting}
          onClick={() => handleSubmit("reject")}
          style={{ backgroundColor: "#dc2626", color: "#fff", padding: "8px 16px", borderRadius: 4, border: "none", cursor: "pointer" }}
        >
          Reject
        </button>

        <button
          data-testid="btn-reject-feedback"
          disabled={submitting}
          onClick={() =>
            setMode(mode === "reject_with_feedback" ? null : "reject_with_feedback")
          }
          style={{ backgroundColor: "#b91c1c", color: "#fff", padding: "8px 16px", borderRadius: 4, border: "none", cursor: "pointer" }}
        >
          Reject with Feedback
        </button>
      </div>

      {/* ── Edit & Approve inline textarea ────────────────────────────────── */}
      {mode === "edit_approve" && (
        <div
          className="hil-edit-panel"
          data-testid="edit-approve-panel"
          style={{ marginTop: 12 }}
        >
          <label htmlFor="edited-text" style={{ fontSize: 13, fontWeight: 600 }}>
            Edit report before approving
          </label>
          <textarea
            id="edited-text"
            data-testid="edited-text-input"
            rows={8}
            value={editedText}
            onChange={(e) => setEditedText(e.target.value)}
            style={{
              width: "100%",
              marginTop: 4,
              padding: 8,
              border: "1px solid #d1d5db",
              borderRadius: 4,
              fontFamily: "monospace",
              fontSize: 12,
            }}
          />
          <button
            data-testid="btn-submit-edit-approve"
            disabled={submitting || !editedText.trim()}
            onClick={() =>
              handleSubmit("edit_approve", { edited_text: editedText })
            }
            style={{ marginTop: 8, backgroundColor: "#2563eb", color: "#fff", padding: "8px 16px", borderRadius: 4, border: "none", cursor: "pointer" }}
          >
            {submitting ? "Submitting…" : "Submit Edit & Approve"}
          </button>
        </div>
      )}

      {/* ── Reject with feedback inline textarea ─────────────────────────── */}
      {mode === "reject_with_feedback" && (
        <div
          className="hil-feedback-panel"
          data-testid="reject-feedback-panel"
          style={{ marginTop: 12 }}
        >
          <label
            htmlFor="feedback-text"
            style={{ fontSize: 13, fontWeight: 600 }}
          >
            Rejection reason (sent to improvement loop)
          </label>
          <textarea
            id="feedback-text"
            data-testid="feedback-text-input"
            rows={4}
            placeholder="Describe why this report should be rejected…"
            value={feedbackText}
            onChange={(e) => setFeedbackText(e.target.value)}
            style={{
              width: "100%",
              marginTop: 4,
              padding: 8,
              border: "1px solid #d1d5db",
              borderRadius: 4,
              fontSize: 13,
            }}
          />
          <button
            data-testid="btn-submit-reject-feedback"
            disabled={submitting || !feedbackText.trim()}
            onClick={() =>
              handleSubmit("reject_with_feedback", {
                feedback_text: feedbackText,
              })
            }
            style={{ marginTop: 8, backgroundColor: "#b91c1c", color: "#fff", padding: "8px 16px", borderRadius: 4, border: "none", cursor: "pointer" }}
          >
            {submitting ? "Submitting…" : "Submit Rejection"}
          </button>
        </div>
      )}
    </div>
  );
};
