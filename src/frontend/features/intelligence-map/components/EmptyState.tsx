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
      style={{
        position: 'absolute',
        top: '50%',
        left: '50%',
        transform: 'translate(-50%, -50%)',
        background: 'rgba(20, 20, 30, 0.82)',
        color: '#e0e0e0',
        borderRadius: 12,
        padding: '24px 32px',
        maxWidth: 380,
        textAlign: 'center',
        zIndex: 1000,
        backdropFilter: 'blur(6px)',
        boxShadow: '0 4px 24px rgba(0,0,0,0.5)',
        border: '1px solid rgba(255,255,255,0.08)',
      }}
    >
      <p
        style={{ margin: 0, fontSize: 15, lineHeight: 1.5, fontWeight: 400 }}
        data-testid="empty-state-message"
      >
        {message}
      </p>
    </div>
  );
};

export default EmptyState;
