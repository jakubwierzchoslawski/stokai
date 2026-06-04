/**
 * QAMessageBubble — single Q&A conversation message bubble.
 *
 * PLAN-F-027 TASK-006
 *
 * For user messages: renders content text only.
 * For assistant messages: renders answer text, confidence badge,
 * collapsible sources list, and optional cost-limit notice.
 */
import React from "react";
import type { QAAnswer } from "../../api/qaApi";
import { QASourcesList } from "./QASourcesList";
import { QACostLimitNotice } from "./QACostLimitNotice";

export interface QAMessageBubbleProps {
  role: "user" | "assistant";
  content: string;
  answer?: QAAnswer | null;
}

export const QAMessageBubble: React.FC<QAMessageBubbleProps> = ({
  role,
  content,
  answer,
}) => {
  const isAssistant = role === "assistant";

  return (
    <div
      className={`qa-message-bubble qa-message-${role}`}
      data-testid={`qa-message-bubble-${role}`}
    >
      <p className="qa-message-content" data-testid="qa-message-content">
        {content}
      </p>

      {isAssistant && answer && (
        <div className="qa-answer-metadata">
          {/* Confidence score badge */}
          <span
            className="qa-confidence-badge"
            data-testid="qa-confidence-badge"
            title="Answer confidence"
          >
            Confidence: {Math.round(answer.confidence * 100)}%
          </span>

          {/* Cited sources (collapsible) */}
          {answer.sources && answer.sources.length > 0 && (
            <QASourcesList sources={answer.sources} />
          )}

          {/* Cost-limit notice */}
          {answer.cost_limited && <QACostLimitNotice />}
        </div>
      )}
    </div>
  );
};
