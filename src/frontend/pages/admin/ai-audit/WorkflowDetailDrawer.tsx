/**
 * WorkflowDetailDrawer — drawer for full workflow run detail.
 *
 * Shows: summary fields, collapsed accordion per agent invocation,
 * nested tool calls, total cost breakdown footer.
 *
 * PLAN-F-029 TASK-011
 */
import React, { useState } from 'react';
import type { WorkflowRunDetail, AgentInvocationSummary } from './hooks/useWorkflowHistory';

interface Props {
  detail: WorkflowRunDetail | null;
  isOpen: boolean;
  onClose: () => void;
}

function StatusBadge({ status }: { status: string }) {
  const colorMap: Record<string, string> = {
    completed: 'bg-green-100 text-green-800',
    running: 'bg-blue-100 text-blue-800',
    failed: 'bg-red-100 text-red-800',
    cancelled: 'bg-gray-100 text-gray-800',
  };
  const color = colorMap[status.toLowerCase()] ?? 'bg-gray-100 text-gray-800';
  return (
    <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${color}`}>
      {status}
    </span>
  );
}

function InvocationAccordion({ inv }: { inv: AgentInvocationSummary }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div
      className="border rounded"
      data-testid={`invocation-accordion-${inv.invocation_id}`}
    >
      <button
        className="w-full flex items-center justify-between px-4 py-2 bg-gray-50 hover:bg-gray-100 text-sm"
        onClick={() => setExpanded((v) => !v)}
      >
        <span>
          <span className="font-medium">{inv.agent_role_id}</span>
          <span className="text-gray-400 mx-2">|</span>
          <span>{inv.model_used}</span>
          <span className="text-gray-400 mx-2">|</span>
          <span>{inv.duration_ms}ms</span>
          <span className="text-gray-400 mx-2">|</span>
          <span>${inv.cost_usd.toFixed(6)}</span>
        </span>
        <span>{expanded ? '▲' : '▼'}</span>
      </button>

      {expanded && (
        <div className="px-4 py-3 text-xs space-y-2 border-t">
          <div className="grid grid-cols-3 gap-2">
            <div>
              <span className="text-gray-500">Prompt version</span>
              <p className="font-mono">{inv.prompt_version.slice(0, 12)}</p>
            </div>
            <div>
              <span className="text-gray-500">Confidence</span>
              <p>{inv.confidence != null ? `${(inv.confidence * 100).toFixed(1)}%` : '—'}</p>
            </div>
            <div>
              <span className="text-gray-500">Tokens in / out</span>
              <p>
                {inv.input_tokens} / {inv.output_tokens}
              </p>
            </div>
          </div>

          {inv.tool_calls.length > 0 && (
            <div>
              <p className="text-gray-500 font-medium mb-1">Tool calls</p>
              <div className="space-y-1">
                {inv.tool_calls.map((tc) => (
                  <div
                    key={tc.tool_call_id}
                    className="flex items-center gap-3 bg-gray-50 rounded px-2 py-1"
                    data-testid={`tool-call-${tc.tool_call_id}`}
                  >
                    <span className="font-mono">{tc.tool_name}</span>
                    <span className="text-gray-400">{tc.duration_ms}ms</span>
                    {tc.cached && (
                      <span className="text-blue-600 text-xs">cached</span>
                    )}
                    {tc.cost_tier && (
                      <span className="text-gray-400">[{tc.cost_tier}]</span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function WorkflowDetailDrawer({ detail, isOpen, onClose }: Props) {
  if (!isOpen || !detail) return null;

  const totalCost = detail.cost_usd;

  return (
    <div
      className="fixed inset-y-0 right-0 w-2/3 bg-white shadow-xl z-50 flex flex-col"
      data-testid="workflow-detail-drawer"
      role="dialog"
      aria-modal="true"
    >
      <div className="flex items-center justify-between px-6 py-4 border-b">
        <h2 className="text-lg font-semibold">Workflow Detail</h2>
        <button
          onClick={onClose}
          className="text-gray-500 hover:text-gray-800"
          data-testid="close-workflow-drawer"
        >
          &times;
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
        {/* Summary */}
        <div className="grid grid-cols-3 gap-4 text-sm">
          <div>
            <span className="text-gray-500">Type</span>
            <p>{detail.workflow_type}</p>
          </div>
          <div>
            <span className="text-gray-500">Status</span>
            <StatusBadge status={detail.status} />
          </div>
          <div>
            <span className="text-gray-500">Started at</span>
            <p>{new Date(detail.started_at).toLocaleString()}</p>
          </div>
          {detail.completed_at && (
            <div>
              <span className="text-gray-500">Completed at</span>
              <p>{new Date(detail.completed_at).toLocaleString()}</p>
            </div>
          )}
          <div>
            <span className="text-gray-500">Cost</span>
            <p>${detail.cost_usd.toFixed(6)}</p>
          </div>
        </div>

        {/* Agent invocations */}
        <div>
          <h3 className="text-sm font-medium text-gray-700 mb-2">
            Agent Invocations ({detail.agent_invocations.length})
          </h3>
          <div className="space-y-2" data-testid="invocations-list">
            {detail.agent_invocations.map((inv) => (
              <InvocationAccordion key={inv.invocation_id} inv={inv} />
            ))}
          </div>
        </div>
      </div>

      {/* Cost footer */}
      <div className="px-6 py-4 border-t bg-gray-50 text-sm">
        <span className="font-medium">Total cost:</span> ${totalCost.toFixed(6)}
      </div>
    </div>
  );
}
