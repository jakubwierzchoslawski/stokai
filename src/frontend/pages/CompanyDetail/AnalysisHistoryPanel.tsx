/**
 * AnalysisHistoryPanel — displays AI analysis history with colored signal badges.
 *
 * Signal badge colors:
 *   BUY_OPP → green
 *   REDUCE_RISK | HEDGE → red
 *   HOLD | WATCH | CONTRARIAN → gray
 *
 * PLAN-F-023 TASK-005
 */
import React from 'react';
import type { AnalysisHistoryItem } from './types';

export interface AnalysisHistoryPanelProps {
  history: AnalysisHistoryItem[];
}

function signalBadgeClass(signal: string): string {
  if (signal === 'BUY_OPP') return 'signal-badge signal-badge--bullish';
  if (signal === 'REDUCE_RISK' || signal === 'HEDGE') return 'signal-badge signal-badge--bearish';
  return 'signal-badge signal-badge--neutral';
}

function signalLabel(signal: string): string {
  const labels: Record<string, string> = {
    BUY_OPP: 'Buy',
    REDUCE_RISK: 'Reduce Risk',
    HEDGE: 'Hedge',
    HOLD: 'Hold',
    WATCH: 'Watch',
    CONTRARIAN: 'Contrarian',
  };
  return labels[signal] ?? signal;
}

export function AnalysisHistoryPanel({ history }: AnalysisHistoryPanelProps): React.ReactElement {
  return (
    <div className="analysis-history-panel" data-testid="analysis-history-panel">
      <h3 className="analysis-history-panel__title">Analysis History</h3>
      {history.length === 0 ? (
        <p data-testid="analysis-history-empty">No analysis history available.</p>
      ) : (
        <ul className="analysis-history-panel__list">
          {history.map((item) => (
            <li
              key={item.rec_id}
              className="analysis-history-panel__item"
              data-testid={`analysis-item-${item.rec_id}`}
            >
              <span
                className={signalBadgeClass(item.action_signal)}
                data-testid={`signal-badge-${item.rec_id}`}
                aria-label={`Signal: ${signalLabel(item.action_signal)}`}
              >
                {signalLabel(item.action_signal)}
              </span>
              <span className="analysis-history-panel__date">
                {new Date(item.generated_at).toLocaleDateString('en-US')}
              </span>
              <span className="analysis-history-panel__confidence">
                {(item.confidence * 100).toFixed(0)}% confidence
              </span>
              <p className="analysis-history-panel__rationale">
                {item.rationale_summary}
              </p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
