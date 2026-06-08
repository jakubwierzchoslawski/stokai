/**
 * RollbackConfirmModal — confirmation dialog for prompt rollback.
 *
 * Shows: rollback target SHA and 60-second SLA callout.
 * Confirm and Cancel buttons.
 *
 * PLAN-F-029 TASK-009
 */
import React from 'react';
import { useRollback } from './hooks/useRollback';

interface Props {
  agentRole: string;
  toVersion: string;
  isOpen: boolean;
  onClose: () => void;
  onSuccess: (effectiveAt: string) => void;
}

export function RollbackConfirmModal({
  agentRole,
  toVersion,
  isOpen,
  onClose,
  onSuccess,
}: Props) {
  const rollback = useRollback();

  if (!isOpen) return null;

  function handleConfirm() {
    rollback.mutate(
      { agent_role: agentRole, to_version: toVersion },
      {
        onSuccess: (data) => {
          onSuccess(data.effective_at);
        },
      }
    );
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
      data-testid="rollback-confirm-modal"
      role="dialog"
      aria-modal="true"
    >
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-md p-6 space-y-4">
        <h2 className="text-lg font-semibold">Confirm Prompt Rollback</h2>

        <p className="text-sm text-gray-700">
          You are rolling back{' '}
          <span className="font-mono font-medium">{agentRole}</span> to version{' '}
          <span className="font-mono text-blue-700">{toVersion.slice(0, 12)}...</span>.
        </p>

        <div
          className="bg-amber-50 border border-amber-300 rounded p-3 text-sm text-amber-800"
          data-testid="sla-callout"
        >
          This will take effect within{' '}
          <span className="font-semibold">60 seconds</span>. Subsequent agent
          invocations will use the rolled-back prompt version.
        </div>

        {rollback.isError && (
          <div
            className="bg-red-50 border border-red-200 rounded p-3 text-sm text-red-700"
            data-testid="rollback-error"
          >
            {rollback.error.message}
          </div>
        )}

        <div className="flex justify-end gap-2 pt-2">
          <button
            onClick={onClose}
            disabled={rollback.isPending}
            className="px-4 py-2 bg-gray-200 text-gray-700 text-sm rounded hover:bg-gray-300 disabled:opacity-50"
            data-testid="cancel-rollback"
          >
            Cancel
          </button>
          <button
            onClick={handleConfirm}
            disabled={rollback.isPending}
            className="px-4 py-2 bg-blue-600 text-white text-sm rounded hover:bg-blue-700 disabled:opacity-50"
            data-testid="confirm-rollback"
          >
            {rollback.isPending ? 'Rolling back...' : 'Confirm Rollback'}
          </button>
        </div>
      </div>
    </div>
  );
}
