/**
 * FundamentalsPanel — displays key financial fundamentals.
 *
 * Null values are rendered as "—" per spec.
 *
 * PLAN-F-023 TASK-005
 */
import React from 'react';
import type { FundamentalsPanel as FundamentalsPanelData } from './types';

export interface FundamentalsPanelProps {
  fundamentals: FundamentalsPanelData;
}

function fmt(value: number | null, prefix?: string): string {
  if (value === null || value === undefined) return '—';
  const formatted = value.toLocaleString('en-US', { maximumFractionDigits: 2 });
  return prefix ? `${prefix}${formatted}` : formatted;
}

export function FundamentalsPanel({ fundamentals }: FundamentalsPanelProps): React.ReactElement {
  return (
    <div className="fundamentals-panel" data-testid="fundamentals-panel">
      <h3 className="fundamentals-panel__title">Fundamentals</h3>
      <dl className="fundamentals-panel__list">
        <dt>P/E Ratio</dt>
        <dd data-testid="pe-ratio">{fmt(fundamentals.pe_ratio)}</dd>

        <dt>EPS</dt>
        <dd data-testid="eps">{fmt(fundamentals.eps)}</dd>

        <dt>Revenue</dt>
        <dd data-testid="revenue">{fmt(fundamentals.revenue, '$')}</dd>

        <dt>Debt / Equity</dt>
        <dd data-testid="debt-to-equity">{fmt(fundamentals.debt_to_equity)}</dd>

        <dt>Source</dt>
        <dd data-testid="source">{fundamentals.source}</dd>

        <dt>As of</dt>
        <dd data-testid="as-of">
          {new Date(fundamentals.as_of).toLocaleDateString('en-US')}
        </dd>
      </dl>
    </div>
  );
}
