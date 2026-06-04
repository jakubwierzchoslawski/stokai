/**
 * LowSampleDisclaimer.tsx — Inline disclaimer for low-sample recommendations.
 *
 * PLAN-F-020 TASK-007
 *
 * Rendered when PopupData.low_sample=true or SidePanelData.low_sample=true.
 * The frontend does NOT compute the threshold — it renders this component
 * when the backend sets low_sample=true (sample_size < 5).
 *
 * AC-005
 */

import React from 'react';

const DISCLAIMER_TEXT =
  'Low sample — fewer than 5 historical analogies found. Treat this recommendation with caution.';

export function LowSampleDisclaimer() {
  return (
    <div
      data-testid="low-sample-disclaimer"
      role="alert"
      style={{
        display: 'flex',
        alignItems: 'flex-start',
        gap: '8px',
        backgroundColor: '#fffbeb',
        border: '1px solid #fde68a',
        borderLeft: '4px solid #f59e0b',
        borderRadius: '4px',
        padding: '8px 10px',
        marginBottom: '8px',
        fontSize: '12px',
        color: '#92400e',
        lineHeight: 1.5,
      }}
    >
      <span aria-hidden="true" style={{ fontSize: '14px' }}>⚠</span>
      <span>{DISCLAIMER_TEXT}</span>
    </div>
  );
}

export default LowSampleDisclaimer;
