/**
 * QACostLimitNotice â€” inline notice shown when cost_limited=true.
 *
 * PLAN-F-027 TASK-006
 *
 * Displayed as an inline banner below the answer text.
 */
import React from "react";

export const QACostLimitNotice: React.FC = () => {
  return (
    <div
      className="qa-cost-limit-notice"
      role="alert"
      data-testid="qa-cost-limit-notice"
    >
      Cost limit reached â€” this answer may be incomplete.
    </div>
  );
};
