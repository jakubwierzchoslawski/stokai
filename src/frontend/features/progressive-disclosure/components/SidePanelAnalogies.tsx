import React from 'react';

import type { AnalogSummary } from '../types/disclosure.types';

export interface SidePanelAnalogiesProps {
  analogies: AnalogSummary[];
}

function truncate(text: string, maxLen: number): string {
  if (text.length <= maxLen) return text;
  return text.slice(0, maxLen - 1) + '…';
}

function formatDate(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
  } catch {
    return iso;
  }
}

export function SidePanelAnalogies({ analogies }: SidePanelAnalogiesProps) {
  if (analogies.length === 0) {
    return (
      <p data-testid="analogies-empty" className="text-xs italic text-muted">
        No historical analogies found.
      </p>
    );
  }

  const topThree = analogies.slice(0, 3);

  return (
    <ul data-testid="analogies-list" className="m-0 flex list-none flex-col gap-2 p-0">
      {topThree.map((a, idx) => (
        <li
          key={`${a.event_id}-${idx}`}
          data-testid={`analogy-item-${idx}`}
          className="flex items-start justify-between gap-2 rounded border border-border-subtle bg-surface-2 px-2.5 py-2"
        >
          <div className="min-w-0 flex-1">
            <p
              data-testid={`analogy-headline-${idx}`}
              className="mb-0.5 text-xs font-medium text-text"
            >
              {truncate(a.headline, 80)}
            </p>
            <p className="m-0 text-[11px] text-muted">{formatDate(a.occurred_at)}</p>
          </div>
          <span
            data-testid={`analogy-score-${idx}`}
            className="inline-block shrink-0 whitespace-nowrap rounded-full bg-signal/20 px-1.5 py-px text-[11px] font-semibold text-signal"
          >
            {Math.round(a.similarity_score * 100)}%
          </span>
        </li>
      ))}
    </ul>
  );
}

export default SidePanelAnalogies;
