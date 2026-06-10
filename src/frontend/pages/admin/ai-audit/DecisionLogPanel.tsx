/**
 * DecisionLogPanel — searchable AI decision log table.
 *
 * Columns: timestamp, agent_role, model, prompt_version (7-char SHA),
 * confidence (color-coded), action_signal, company_ticker, Langfuse link.
 * Row click opens DecisionDetailDrawer.
 *
 * PLAN-F-029 TASK-007
 */
import React, { useState, useCallback } from 'react';
import { useDecisionLog, type DecisionLogFilters, type AIDecisionRow } from './hooks/useDecisionLog';
import { useDecisionDetail } from './hooks/useDecisionDetail';
import { DecisionLogFilter } from './DecisionLogFilter';
import { DecisionDetailDrawer, type AIDecisionDetail } from './DecisionDetailDrawer';
import { OverrideModal } from './OverrideModal';

// ── Confidence badge ───────────────────────────────────────────────────────────

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

// ── Main component ─────────────────────────────────────────────────────────────

export function DecisionLogPanel() {
  const [filters, setFilters] = useState<DecisionLogFilters>({});
  const [selectedDecisionId, setSelectedDecisionId] = useState<string | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [overrideDecision, setOverrideDecision] = useState<AIDecisionDetail | null>(null);
  const [overrideOpen, setOverrideOpen] = useState(false);

  const { rows, nextCursor, isLoading, isError, loadNextPage, resetCursor, refetch } =
    useDecisionLog(filters);

  const { data: selectedDetail } = useDecisionDetail(
    selectedDecisionId ?? '',
    !!selectedDecisionId,
  );

  const handleApplyFilters = useCallback(
    (newFilters: DecisionLogFilters) => {
      resetCursor();
      setFilters(newFilters);
    },
    [resetCursor]
  );

  const handleClearFilters = useCallback(() => {
    resetCursor();
    setFilters({});
  }, [resetCursor]);

  const handleRowClick = useCallback((row: AIDecisionRow) => {
    setSelectedDecisionId(row.decision_id);
    setDrawerOpen(true);
  }, []);

  const handleOverride = useCallback((decision: AIDecisionDetail) => {
    setOverrideDecision(decision);
    setOverrideOpen(true);
    setDrawerOpen(false);
  }, []);

  return (
    <div className="space-y-4" data-testid="decision-log-panel">
      <DecisionLogFilter onApply={handleApplyFilters} onClear={handleClearFilters} />

      {isLoading && <p className="text-gray-500 text-sm">Loading decisions...</p>}
      {isError && (
        <p className="text-red-600 text-sm">Failed to load decisions. Please try again.</p>
      )}

      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-gray-200 text-sm" data-testid="decisions-table">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                Timestamp
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                Agent role
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                Model
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                Prompt ver.
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                Confidence
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                Signal
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                Company
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                Langfuse
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {rows.map((row) => (
              <tr
                key={row.decision_id}
                className="hover:bg-gray-50 cursor-pointer"
                onClick={() => handleRowClick(row)}
                data-testid={`decision-row-${row.decision_id}`}
              >
                <td className="px-4 py-2 text-xs text-gray-500">
                  {new Date(row.created_at).toLocaleString()}
                </td>
                <td className="px-4 py-2">{row.agent_role}</td>
                <td className="px-4 py-2 text-xs">{row.model}</td>
                <td className="px-4 py-2 font-mono text-xs">
                  {row.prompt_version.slice(0, 7)}
                </td>
                <td className="px-4 py-2">
                  <ConfidenceBadge value={row.confidence} />
                </td>
                <td className="px-4 py-2 text-xs">{row.action_signal ?? '—'}</td>
                <td className="px-4 py-2 text-xs">{row.company_ticker ?? '—'}</td>
                <td className="px-4 py-2">
                  <a
                    href={row.langfuse_trace_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-blue-500 hover:text-blue-700"
                    onClick={(e) => e.stopPropagation()}
                    aria-label="Langfuse trace"
                    data-testid={`langfuse-link-${row.decision_id}`}
                  >
                    &#x2197;
                  </a>
                </td>
              </tr>
            ))}
            {rows.length === 0 && !isLoading && (
              <tr>
                <td colSpan={8} className="px-4 py-8 text-center text-gray-400">
                  No decisions found
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
          data-testid="next-page-btn"
        >
          Next page
        </button>
      )}

      <DecisionDetailDrawer
        decision={selectedDetail ?? null}
        isOpen={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        onOverride={handleOverride}
      />

      {overrideDecision && (
        <OverrideModal
          decision={overrideDecision}
          isOpen={overrideOpen}
          onClose={() => {
            setOverrideOpen(false);
            setOverrideDecision(null);
          }}
          onSuccess={() => {
            setOverrideOpen(false);
            setOverrideDecision(null);
            refetch();
          }}
        />
      )}
    </div>
  );
}
