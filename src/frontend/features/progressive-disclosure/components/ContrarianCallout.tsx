import React from 'react';

export interface ContrarianCalloutProps {
  text: string;
}

export function ContrarianCallout({ text }: ContrarianCalloutProps) {
  return (
    <div
      data-testid="contrarian-callout"
      role="note"
      className="relative mb-3.5 flex items-start gap-2.5 rounded border border-signal/30 border-l-4 border-l-signal bg-signal/10 px-3.5 py-3 text-[13px] leading-[1.5] text-text"
    >
      <span aria-hidden="true" className="shrink-0 text-base">📜</span>
      <div>
        <p className="mb-1 text-xs font-bold uppercase tracking-[0.05em] text-text">
          History says
        </p>
        <p className="m-0">{text}</p>
      </div>
    </div>
  );
}

export default ContrarianCallout;
