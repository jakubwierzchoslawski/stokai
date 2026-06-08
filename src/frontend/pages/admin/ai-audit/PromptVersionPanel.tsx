/**
 * PromptVersionPanel — prompt version history per agent role.
 *
 * Renders per-agent accordion with a Select control for role,
 * a table of PromptVersionEntry rows, and Rollback buttons.
 *
 * PLAN-F-029 TASK-009
 */
import React, { useState } from 'react';
import { usePromptHistory } from './hooks/usePromptHistory';
import { RollbackConfirmModal } from './RollbackConfirmModal';

const AGENT_ROLES = [
  'narrative_writer',
  'recommendation_synthesizer',
  'classifier',
  'scenario_analyst',
];

interface RollbackTarget {
  agentRole: string;
  sha: string;
}

export function PromptVersionPanel() {
  const [selectedRole, setSelectedRole] = useState(AGENT_ROLES[0]!);
  const [rollbackTarget, setRollbackTarget] = useState<RollbackTarget | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const { data: entries, isLoading, isError } = usePromptHistory(selectedRole);

  function handleRollbackClick(sha: string) {
    setRollbackTarget({ agentRole: selectedRole, sha });
    setSuccessMessage(null);
  }

  function handleRollbackSuccess(effectiveAt: string) {
    setRollbackTarget(null);
    setSuccessMessage(
      `Rollback applied at ${new Date(effectiveAt).toLocaleString()}. Agents will use this version within 60 seconds.`
    );
  }

  return (
    <div className="space-y-4" data-testid="prompt-version-panel">
      <div className="flex items-center gap-4">
        <label className="text-sm font-medium text-gray-700">Agent role</label>
        <select
          value={selectedRole}
          onChange={(e) => {
            setSelectedRole(e.target.value);
            setSuccessMessage(null);
          }}
          className="border rounded px-3 py-1 text-sm"
          data-testid="agent-role-select"
        >
          {AGENT_ROLES.map((r) => (
            <option key={r} value={r}>
              {r}
            </option>
          ))}
        </select>
      </div>

      {successMessage && (
        <div
          className="bg-green-50 border border-green-200 rounded p-3 text-sm text-green-800"
          data-testid="rollback-success-message"
        >
          {successMessage}
        </div>
      )}

      {isLoading && <p className="text-gray-500 text-sm">Loading prompt history...</p>}
      {isError && (
        <p className="text-red-600 text-sm">Failed to load prompt history.</p>
      )}

      {entries && entries.length > 0 && (
        <div className="overflow-x-auto">
          <table
            className="min-w-full divide-y divide-gray-200 text-sm"
            data-testid="prompt-version-table"
          >
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                  SHA
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                  Label
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                  Published
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                  Rolled back
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                  Quality metrics
                </th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {entries.map((entry) => (
                <tr key={entry.version_id} data-testid={`prompt-row-${entry.version_id}`}>
                  <td className="px-4 py-2 font-mono text-xs">
                    {entry.version_id.slice(0, 12)}
                  </td>
                  <td className="px-4 py-2 text-xs">{entry.label_applied}</td>
                  <td className="px-4 py-2 text-xs">
                    {new Date(entry.published_at).toLocaleString()}
                  </td>
                  <td className="px-4 py-2 text-xs">
                    {entry.rolled_back_at
                      ? new Date(entry.rolled_back_at).toLocaleString()
                      : '—'}
                  </td>
                  <td className="px-4 py-2 text-xs" data-testid={`quality-metrics-${entry.version_id}`}>
                    {entry.quality_metrics
                      ? Object.entries(entry.quality_metrics)
                          .map(([k, v]) => `${k}: ${v}`)
                          .join(', ')
                      : '—'}
                  </td>
                  <td className="px-4 py-2">
                    {!entry.rolled_back_at && (
                      <button
                        onClick={() => handleRollbackClick(entry.version_id)}
                        className="px-2 py-1 text-xs bg-amber-100 text-amber-800 rounded hover:bg-amber-200"
                        data-testid={`rollback-btn-${entry.version_id}`}
                      >
                        Rollback
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {entries?.length === 0 && !isLoading && (
        <p className="text-gray-400 text-sm">No prompt versions found.</p>
      )}

      {rollbackTarget && (
        <RollbackConfirmModal
          agentRole={rollbackTarget.agentRole}
          toVersion={rollbackTarget.sha}
          isOpen={true}
          onClose={() => setRollbackTarget(null)}
          onSuccess={handleRollbackSuccess}
        />
      )}
    </div>
  );
}
