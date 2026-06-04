/**
 * QASourcesList — collapsible list of cited sources for a Q&A answer.
 *
 * PLAN-F-027 TASK-006
 *
 * Displays the list of QASource items in a collapsible section.
 * Collapsed by default; expands on click.
 */
import React, { useState } from "react";
import type { QASource } from "../../api/qaApi";

export interface QASourcesListProps {
  sources: QASource[];
}

const SOURCE_TYPE_ICONS: Record<string, string> = {
  event: "📅",
  filing: "📄",
  price_bar: "📈",
  recommendation: "💡",
  semantic_fact: "🔍",
};

function getIcon(type: string): string {
  return SOURCE_TYPE_ICONS[type] ?? "📌";
}

export const QASourcesList: React.FC<QASourcesListProps> = ({ sources }) => {
  const [expanded, setExpanded] = useState(false);

  if (!sources || sources.length === 0) {
    return null;
  }

  return (
    <div className="qa-sources-list" data-testid="qa-sources-list">
      <button
        className="qa-sources-toggle"
        onClick={() => setExpanded((prev) => !prev)}
        aria-expanded={expanded}
        aria-controls="qa-sources-content"
        data-testid="qa-sources-toggle"
      >
        {expanded ? "▼" : "▶"} Sources ({sources.length})
      </button>

      {expanded && (
        <ul
          id="qa-sources-content"
          className="qa-sources-content"
          data-testid="qa-sources-content"
        >
          {sources.map((source) => (
            <li key={`${source.type}-${source.id}`} className="qa-source-item">
              <span className="qa-source-icon" aria-hidden="true">
                {getIcon(source.type)}
              </span>
              <span className="qa-source-description">{source.description}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};
