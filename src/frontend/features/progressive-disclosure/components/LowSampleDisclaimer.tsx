import React from 'react';

const DISCLAIMER_TEXT =
  'Low sample — fewer than 5 historical analogies found. Treat this recommendation with caution.';

export function LowSampleDisclaimer() {
  return (
    <div
      data-testid="low-sample-disclaimer"
      role="alert"
      className="mb-2 flex items-start gap-2 rounded border border-warning/30 border-l-4 border-l-warning bg-warning/10 px-2.5 py-2 text-xs leading-[1.5] text-warning"
    >
      <span aria-hidden="true" className="text-sm shrink-0">⚠</span>
      <span>{DISCLAIMER_TEXT}</span>
    </div>
  );
}

export default LowSampleDisclaimer;
