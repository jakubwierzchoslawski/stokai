/**
 * DecisionDetailDrawer — side drawer showing full AIDecisionDetail.
 *
 * Opens when a decision log row is clicked.
 * Shows: all fields of AIDecisionDetail, retrieved_analogs as collapsible JSON,
 * langfuse_trace_url as clickable link, and 'Override' button.
 *
 * PLAN-F-029 TASK-007
 */
import React, { useState } from 'react';

export interface AIDecisionDetail {
  decision_id: string;
  agent_role: string;
  model: string;
  prompt_version: string;
  confidence: number;
  inputs_summary: string;
  inputs_full: string;
  retrieved_analogs: unknown[];
  action_signal: string | null;
  company_ticker: string | null;
  output_text: string;
  langfuse_trace_url: string;
  workflow_run_id: string | null;
  created_at: string;
}

interface Props {
  decision: AIDecisionDetail | null;
  isOpen: boolean;
  onClose: () => void;
  onOverride: (decision: AIDecisionDetail) => void;
}

function ConfidenceBadge({ value }: { value: number }) {
  const color =
    value >= 0.7
      ? 'bg-green-100 text-green-800'
      : value >= 0.4
      ? 'bg-amber-100 text-amber-800'
      : 'bg-red-100 text-red-800';

  return (
    <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${color}`}>
      {(value * 100).toFixed(1)}%
    </span>
  );
}

export function DecisionDetailDrawer({ decision, isOpen, onClose, onOverride }: Props) {
  const [analogsExpanded, setAnalogsExpanded] = useState(false);

  if (!isOpen || !decision) return null;

  return (
    <div
      className="fixed inset-y-0 right-0 w-1/2 bg-white shadow-xl z-50 flex flex-col"
      data-testid="decision-detail-drawer"
      role="dialog"
      aria-modal="true"
    >
      <div className="flex items-center justify-between px-6 py-4 border-b">
        <h2 className="text-lg font-semibold">Decision Detail</h2>
        <button
          onClick={onClose}
          className="text-gray-500 hover:text-gray-800"
          data-testid="close-drawer"
          aria-label="Close"
        >
          &times;
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
        <div className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <span className="font-medium text-gray-500">Agent role</span>
            <p>{decision.agent_role}</p>
          </div>
          <div>
            <span className="font-medium text-gray-500">Model</span>
            <p>{decision.model}</p>
          </div>
          <div>
            <span className="font-medium text-gray-500">Prompt version</span>
            <p className="font-mono text-xs">{decision.prompt_version}</p>
          </div>
          <div>
            <span className="font-medium text-gray-500">Confidence</span>
            <ConfidenceBadge value={decision.confidence} />
          </div>
          <div>
            <span className="font-medium text-gray-500">Action signal</span>
            <p>{decision.action_signal ?? '—'}</p>
          </div>
          <div>
            <span className="font-medium text-gray-500">Company</span>
            <p>{decision.company_ticker ?? '—'}</p>
          </div>
          <div>
            <span className="font-medium text-gray-500">Created at</span>
            <p>{new Date(decision.created_at).toLocaleString()}</p>
          </div>
          <div>
            <span className="font-medium text-gray-500">Langfuse trace</span>
            <a
              href={decision.langfuse_trace_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-blue-600 underline text-xs break-all"
              data-testid="langfuse-trace-link"
            >
              {decision.langfuse_trace_url}
            </a>
          </div>
        </div>

        <div>
          <p className="font-medium text-gray-500 text-sm mb-1">Inputs (full)</p>
          <pre className="bg-gray-50 border rounded p-3 text-xs overflow-x-auto whitespace-pre-wrap">
            {decision.inputs_full}
          </pre>
        </div>

        <div>
          <button
            className="flex items-center gap-1 text-sm font-medium text-gray-600 hover:text-gray-900"
            onClick={() => setAnalogsExpanded((v) => !v)}
            data-testid="analogs-toggle"
          >
            {analogsExpanded ? '▲' : '▼'} Retrieved analogues (
            {decision.retrieved_analogs.length})
          </button>
          {analogsExpanded && (
            <pre className="bg-gray-50 border rounded p-3 text-xs mt-2 overflow-x-auto whitespace-pre-wrap">
              {JSON.stringify(decision.retrieved_analogs, null, 2)}
            </pre>
          )}
        </div>

        <div>
          <p className="font-medium text-gray-500 text-sm mb-1">Output</p>
          <div className="bg-gray-50 border rounded p-3 text-sm whitespace-pre-wrap">
            {decision.output_text}
          </div>
        </div>
      </div>

      <div className="px-6 py-4 border-t">
        <button
          onClick={() => onOverride(decision)}
          className="px-4 py-2 bg-red-600 text-white text-sm rounded hover:bg-red-700"
          data-testid="override-button"
        >
          Override
        </button>
      </div>
    </div>
  );
}
