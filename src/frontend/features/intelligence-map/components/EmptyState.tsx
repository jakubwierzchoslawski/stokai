/**
 * EmptyState.tsx — Centered, floating translucent card rendered over the map.
 *
 * Shown only when events.length === 0 after filtering.
 * Uses absolute positioning to float over the MapLibre canvas.
 *
 * PLAN-F-019 TASK-010
 */

import React from 'react';

// ── Props ─────────────────────────────────────────────────────────────────────

export interface EmptyStateProps {
  message: string;
}

// ── Component ─────────────────────────────────────────────────────────────────

export const EmptyState: React.FC<EmptyStateProps> = ({ message }) => {
  return (
    <div
      data-testid="empty-state"
      role="status"
      aria-live="polite"
      className="absolute left-1/2 top-1/2 z-[1000] max-w-[380px] -translate-x-1/2 -translate-y-1/2 rounded-xl border border-subtle bg-surface-1/85 px-8 py-6 text-center text-text shadow-2xl backdrop-blur"
    >
      <p
        className="m-0 text-[15px] leading-relaxed"
        data-testid="empty-state-message"
      >
        {message}
      </p>
    </div>
  );
};

export default EmptyState;
