/**
 * SidePanelAnalogies.tsx — Historical analogy list (top 3).
 *
 * PLAN-F-020 TASK-008
 *
 * Renders up to 3 analogies with headline (truncated to 80 chars),
 * occurred_at as a short date, and similarity_score as a percentage.
 *
 * AC-002
 */

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
      <p
        data-testid="analogies-empty"
        style={{ color: '#9ca3af', fontSize: '12px', fontStyle: 'italic' }}
      >
        No historical analogies found.
      </p>
    );
  }

  const topThree = analogies.slice(0, 3);

  return (
    <ul
      data-testid="analogies-list"
      style={{
        listStyle: 'none',
        margin: 0,
        padding: 0,
        display: 'flex',
        flexDirection: 'column',
        gap: '8px',
      }}
    >
      {topThree.map((a, idx) => (
        <li
          key={`${a.event_id}-${idx}`}
          data-testid={`analogy-item-${idx}`}
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'flex-start',
            gap: '8px',
            padding: '8px 10px',
            backgroundColor: '#f9fafb',
            border: '1px solid #f3f4f6',
            borderRadius: '4px',
          }}
        >
          <div style={{ flex: 1, minWidth: 0 }}>
            <p
              data-testid={`analogy-headline-${idx}`}
              style={{ margin: '0 0 2px 0', fontSize: '12px', fontWeight: 500, color: '#374151' }}
            >
              {truncate(a.headline, 80)}
            </p>
            <p
              style={{ margin: 0, fontSize: '11px', color: '#9ca3af' }}
            >
              {formatDate(a.occurred_at)}
            </p>
          </div>
          <span
            data-testid={`analogy-score-${idx}`}
            style={{
              flexShrink: 0,
              display: 'inline-block',
              backgroundColor: '#dbeafe',
              color: '#1d4ed8',
              borderRadius: '9999px',
              padding: '1px 7px',
              fontSize: '11px',
              fontWeight: 600,
              whiteSpace: 'nowrap',
            }}
          >
            {Math.round(a.similarity_score * 100)}%
          </span>
        </li>
      ))}
    </ul>
  );
}

export default SidePanelAnalogies;
