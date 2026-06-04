/**
 * ContrarianCallout.tsx — Highlighted "history says" callout block.
 *
 * PLAN-F-020 TASK-007
 *
 * Rendered as the first visible content block in the side panel when
 * SidePanelData.is_contrarian=true. Uses a distinctive left-border color
 * (blue, distinct from the warning amber of LowSampleDisclaimer).
 *
 * AC-004
 */

import React from 'react';

export interface ContrarianCalloutProps {
  /** Contrarian callout text from the AI recommendation */
  text: string;
}

export function ContrarianCallout({ text }: ContrarianCalloutProps) {
  return (
    <div
      data-testid="contrarian-callout"
      role="note"
      style={{
        display: 'flex',
        alignItems: 'flex-start',
        gap: '10px',
        backgroundColor: '#eff6ff',
        border: '1px solid #bfdbfe',
        borderLeft: '4px solid #2563eb',
        borderRadius: '4px',
        padding: '12px 14px',
        marginBottom: '14px',
        fontSize: '13px',
        color: '#1e3a8a',
        lineHeight: 1.5,
        zIndex: 1,
        position: 'relative',
      }}
    >
      <span
        aria-hidden="true"
        style={{ fontSize: '16px', flexShrink: 0 }}
      >
        📜
      </span>
      <div>
        <p
          style={{ margin: '0 0 4px 0', fontWeight: 700, fontSize: '12px', textTransform: 'uppercase', letterSpacing: '0.05em' }}
        >
          History says
        </p>
        <p style={{ margin: 0 }}>{text}</p>
      </div>
    </div>
  );
}

export default ContrarianCallout;
