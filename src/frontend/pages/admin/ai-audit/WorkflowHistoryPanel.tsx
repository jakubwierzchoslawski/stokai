/**
 * WorkflowHistoryPanel — paginated workflow run history with Re-run.
 *
 * Columns: type, status, started_at, duration, cost_usd, Re-run button.
 * Row click opens WorkflowDetailDrawer.
 * Re-run: confirmation popover → mutation → toast → refresh.
 *
 * PLAN-F-029 TASK-011
 */
import React, { useState, useCallback } from 'react';
import {
  useWorkflowHistory,
  useRerunWorkflow,
  type WorkflowRunSummary,
} from './hooks/useWorkflowHistory';
import { useWorkflowDetail } from './hooks/useWorkflowDetail';
import { WorkflowDetailDrawer } from './WorkflowDetailDrawer';

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

function formatDuration(startedAt: string, completedAt: string | null): string {
  if (!completedAt) return '—';
  const diff = new Date(completedAt).getTime() - new Date(startedAt).getTime();
  return `${(diff / 1000).toFixed(1)}s`;
}

export function WorkflowHistoryPanel() {
  const { runs, nextCursor, isLoading, isError, loadNextPage, refetch } =
    useWorkflowHistory();
  const rerunMutation = useRerunWorkflow();

  const [selectedWorkflowId, setSelectedWorkflowId] = useState<string | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [rerunConfirm, setRerunConfirm] = useState<string | null>(null); // workflow_id
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  const { data: selectedDetail } = useWorkflowDetail(
    selectedWorkflowId ?? '',
    !!selectedWorkflowId,
  );

  const handleRowClick = useCallback((run: WorkflowRunSummary) => {
    setSelectedWorkflowId(run.workflow_id);
    setDrawerOpen(true);
  }, []);

  const handleRerunClick = useCallback(
    (e: React.MouseEvent, workflowId: string) => {
      e.stopPropagation();
      setRerunConfirm(workflowId);
    },
    []
  );

  const handleRerunConfirm = useCallback(() => {
    if (!rerunConfirm) return;
    rerunMutation.mutate(rerunConfirm, {
      onSuccess: (data) => {
        setToastMessage(`New run ${data.new_workflow_id} dispatched`);
        setRerunConfirm(null);
        setTimeout(() => {
          refetch();
          setToastMessage(null);
        }, 1000);
      },
    });
  }, [rerunConfirm, rerunMutation, refetch]);

  return (
    <div className="space-y-4" data-testid="workflow-history-panel">
      {/* Toast */}
      {toastMessage && (
        <div
          className="bg-green-100 border border-green-300 rounded p-3 text-sm text-green-800"
          data-testid="rerun-toast"
        >
          {toastMessage}
        </div>
      )}

      {isLoading && <p className="text-gray-500 text-sm">Loading workflows...</p>}
      {isError && <p className="text-red-600 text-sm">Failed to load workflows.</p>}

      <div className="overflow-x-auto">
        <table
          className="min-w-full divide-y divide-gray-200 text-sm"
          data-testid="workflow-table"
        >
          <thead className="bg-gray-50">
            <tr>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                Type
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                Status
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                Started at
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                Duration
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                Cost (USD)
              </th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {runs.map((run) => (
              <tr
                key={run.workflow_id}
                className="hover:bg-gray-50 cursor-pointer"
                onClick={() => handleRowClick(run)}
                data-testid={`workflow-row-${run.workflow_id}`}
              >
                <td className="px-4 py-2">{run.workflow_type}</td>
                <td className="px-4 py-2">
                  <StatusBadge status={run.status} />
                </td>
                <td className="px-4 py-2 text-xs">
                  {new Date(run.started_at).toLocaleString()}
                </td>
                <td className="px-4 py-2 text-xs">
                  {formatDuration(run.started_at, run.completed_at)}
                </td>
                <td className="px-4 py-2 font-mono text-xs">
                  ${run.cost_usd.toFixed(4)}
                </td>
                <td className="px-4 py-2">
                  <button
                    onClick={(e) => handleRerunClick(e, run.workflow_id)}
                    className="px-2 py-1 text-xs bg-blue-100 text-blue-800 rounded hover:bg-blue-200"
                    data-testid={`rerun-btn-${run.workflow_id}`}
                  >
                    Re-run
                  </button>
                </td>
              </tr>
            ))}
            {runs.length === 0 && !isLoading && (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-gray-400">
                  No workflows found
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {nextCursor && (
        <button
          onClick={loadNextPage}
          className="px-4 py-2 text-sm text-blue-600 hover:text-blue-800"
          data-testid="next-page-workflows"
        >
          Next page
        </button>
      )}

      {/* Re-run confirmation popover */}
      {rerunConfirm && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
          data-testid="rerun-confirm-popover"
        >
          <div className="bg-white rounded-xl shadow-2xl p-6 max-w-sm space-y-4">
            <p className="text-sm">
              Re-run this workflow with current production prompts?
            </p>
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setRerunConfirm(null)}
                className="px-3 py-1 bg-gray-200 text-gray-700 text-sm rounded"
                data-testid="cancel-rerun"
              >
                Cancel
              </button>
              <button
                onClick={handleRerunConfirm}
                disabled={rerunMutation.isPending}
                className="px-3 py-1 bg-blue-600 text-white text-sm rounded disabled:opacity-50"
                data-testid="confirm-rerun"
              >
                {rerunMutation.isPending ? 'Dispatching...' : 'Confirm'}
              </button>
            </div>
          </div>
        </div>
      )}

      <WorkflowDetailDrawer
        detail={selectedDetail ?? null}
        isOpen={drawerOpen}
        onClose={() => setDrawerOpen(false)}
      />
    </div>
  );
}
