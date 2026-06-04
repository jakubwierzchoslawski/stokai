/**
 * SidePanel.tsx — Level 2 CSS drawer overlay for full event analysis.
 *
 * PLAN-F-020 TASK-009
 *
 * CSS drawer: position fixed, right-anchored, slides in on isOpen=true.
 * Renders over the map without blocking pointer events on the left viewport.
 *
 * Content order (when data available):
 *  1. ContrarianCallout (when is_contrarian=true) — first visible content block
 *  2. Event summary
 *  3. Sparklines grid (2-column, max 6)
 *  4. Action signal + confidence + sample_size
 *  5. LowSampleDisclaimer (when low_sample=true)
 *  6. Rationale
 *  7. SidePanelAnalogies (top 3)
 *  8. Affected companies table
 *  9. Triggering posts (when social_posts is non-null and non-empty)
 * 10. "Why this read?" link → onOpenAuditTrail
 * 11. "Full Analysis" button → onOpenDeepDive
 *
 * AC-002, AC-004, AC-005
 */

import React from 'react';

import { useSidePanelData } from '../hooks/useSidePanelData';
import { ContrarianCallout } from './ContrarianCallout';
import { LowSampleDisclaimer } from './LowSampleDisclaimer';
import { SidePanelAnalogies } from './SidePanelAnalogies';
import { SidePanelSparkline } from './SidePanelSparkline';

// ── Skeleton ──────────────────────────────────────────────────────────────────

function SidePanelSkeleton() {
  return (
    <div data-testid="side-panel-skeleton" style={{ padding: '20px' }}>
      {[80, 200, 60, 160, 100, 140].map((w, i) => (
        <div
          key={i}
          style={{
            height: i === 0 ? '20px' : i === 1 ? '80px' : '14px',
            width: `${w}%`,
            maxWidth: `${w}%`,
            backgroundColor: '#e5e7eb',
            borderRadius: '4px',
            marginBottom: '12px',
          }}
        />
      ))}
    </div>
  );
}

// ── Props ─────────────────────────────────────────────────────────────────────

export interface SidePanelProps {
  eventId: string | null;
  isOpen: boolean;
  onClose: () => void;
  onOpenAuditTrail: () => void;
  onOpenDeepDive: () => void;
}

// ── Component ─────────────────────────────────────────────────────────────────

export function SidePanel({
  eventId,
  isOpen,
  onClose,
  onOpenAuditTrail,
  onOpenDeepDive,
}: SidePanelProps) {
  const { data, isLoading } = useSidePanelData(eventId, isOpen);

  return (
    <div
      data-testid="side-panel"
      data-open={isOpen}
      style={{
        position: 'fixed',
        right: 0,
        top: 0,
        height: '100vh',
        width: '420px',
        backgroundColor: '#fff',
        boxShadow: '-4px 0 20px rgba(0,0,0,0.12)',
        zIndex: 200,
        transform: isOpen ? 'translateX(0)' : 'translateX(100%)',
        transition: 'transform 0.25s ease-in-out',
        display: 'flex',
        flexDirection: 'column',
        overflowY: 'auto',
        // Pointer-events: none on left margin zone handled via CSS class in real app;
        // here we allow all pointer events on the panel content area.
        pointerEvents: isOpen ? 'auto' : 'none',
      }}
    >
      {/* Header */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          padding: '16px 18px 12px',
          borderBottom: '1px solid #e5e7eb',
          flexShrink: 0,
        }}
      >
        <h2 style={{ margin: 0, fontSize: '15px', fontWeight: 700, color: '#111827' }}>
          Event Analysis
        </h2>
        <button
          data-testid="side-panel-close"
          onClick={onClose}
          aria-label="Close side panel"
          style={{
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            color: '#6b7280',
            fontSize: '18px',
            padding: '4px',
          }}
        >
          ✕
        </button>
      </div>

      {/* Body */}
      <div style={{ padding: '18px', flex: 1, overflowY: 'auto' }}>
        {isOpen && isLoading && <SidePanelSkeleton />}

        {isOpen && data && (
          <>
            {/* 1. Contrarian callout (first visible content block) */}
            {data.is_contrarian && data.contrarian_callout && (
              <ContrarianCallout text={data.contrarian_callout} />
            )}

            {/* 2. Summary */}
            <p
              data-testid="side-panel-summary"
              style={{ margin: '0 0 14px 0', fontSize: '13px', color: '#374151', lineHeight: 1.6 }}
            >
              {data.summary}
            </p>

            {/* 3. Sparklines grid */}
            {data.sparklines.length > 0 && (
              <div
                data-testid="sparklines-section"
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(2, 1fr)',
                  gap: '12px',
                  marginBottom: '16px',
                }}
              >
                {data.sparklines.slice(0, 6).map((s) => (
                  <SidePanelSparkline key={s.ticker} ticker={s.ticker} ohlcv_7d={s.ohlcv_7d} />
                ))}
              </div>
            )}

            {/* 4. Action signal + confidence */}
            <div style={{ marginBottom: '10px' }}>
              <p style={{ margin: '0 0 2px 0', fontSize: '12px' }}>
                Signal:{' '}
                <strong data-testid="side-panel-action-signal">{data.action_signal}</strong>
              </p>
              <p
                data-testid="side-panel-confidence"
                style={{ margin: '0 0 2px 0', fontSize: '12px', color: '#6b7280' }}
              >
                Confidence: {(data.confidence * 100).toFixed(0)}% · Sample: {data.sample_size}
              </p>
            </div>

            {/* 5. Low sample disclaimer */}
            {data.low_sample && <LowSampleDisclaimer />}

            {/* 6. Rationale */}
            <div style={{ marginBottom: '16px' }}>
              <h3 style={{ margin: '0 0 6px 0', fontSize: '12px', textTransform: 'uppercase', color: '#6b7280', letterSpacing: '0.06em' }}>
                Rationale
              </h3>
              <p
                data-testid="side-panel-rationale"
                style={{ margin: 0, fontSize: '13px', color: '#374151', lineHeight: 1.6 }}
              >
                {data.rationale}
              </p>
            </div>

            {/* 7. Analogies */}
            <div data-testid="analogies-section" style={{ marginBottom: '16px' }}>
              <h3 style={{ margin: '0 0 8px 0', fontSize: '12px', textTransform: 'uppercase', color: '#6b7280', letterSpacing: '0.06em' }}>
                Historical Analogies
              </h3>
              <SidePanelAnalogies analogies={data.analogies} />
            </div>

            {/* 8. Affected companies table */}
            {data.affected_companies.length > 0 && (
              <div data-testid="affected-companies-section" style={{ marginBottom: '16px' }}>
                <h3 style={{ margin: '0 0 8px 0', fontSize: '12px', textTransform: 'uppercase', color: '#6b7280', letterSpacing: '0.06em' }}>
                  Affected Holdings
                </h3>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid #e5e7eb' }}>
                      <th style={{ textAlign: 'left', padding: '4px 6px', fontWeight: 600, color: '#6b7280' }}>Company</th>
                      <th style={{ textAlign: 'right', padding: '4px 6px', fontWeight: 600, color: '#6b7280' }}>Score</th>
                      <th style={{ textAlign: 'right', padding: '4px 6px', fontWeight: 600, color: '#6b7280' }}>Delta</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.affected_companies.map((c) => (
                      <tr
                        key={c.company_id.toString()}
                        data-testid={`company-row-${c.ticker}`}
                        style={{ borderBottom: '1px solid #f9fafb' }}
                      >
                        <td style={{ padding: '4px 6px', color: '#374151' }}>
                          <span style={{ fontWeight: 600 }}>{c.ticker}</span>{' '}
                          <span style={{ color: '#9ca3af' }}>{c.name}</span>
                        </td>
                        <td style={{ textAlign: 'right', padding: '4px 6px', color: '#374151' }}>
                          {c.score.toFixed(1)}
                        </td>
                        <td style={{ textAlign: 'right', padding: '4px 6px', color: c.delta >= 0 ? '#16a34a' : '#dc2626' }}>
                          {c.delta >= 0 ? '+' : ''}{c.delta.toFixed(1)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {/* 9. Triggering posts */}
            {data.social_posts && data.social_posts.length > 0 && (
              <div data-testid="social-posts-section" style={{ marginBottom: '16px' }}>
                <h3 style={{ margin: '0 0 8px 0', fontSize: '12px', textTransform: 'uppercase', color: '#6b7280', letterSpacing: '0.06em' }}>
                  Triggering Posts
                </h3>
                {data.social_posts.map((post) => (
                  <div
                    key={post.post_id}
                    data-testid={`social-post-${post.post_id}`}
                    style={{
                      marginBottom: '8px',
                      padding: '8px 10px',
                      backgroundColor: '#f9fafb',
                      borderRadius: '4px',
                      fontSize: '12px',
                    }}
                  >
                    <p style={{ margin: '0 0 3px 0', fontWeight: 600, color: '#6b7280' }}>
                      {post.source} · {post.timestamp}
                    </p>
                    <p style={{ margin: 0, color: '#374151' }}>{post.text}</p>
                  </div>
                ))}
              </div>
            )}

            {/* 10 & 11. Footer links */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '16px', paddingTop: '12px', borderTop: '1px solid #f3f4f6' }}>
              <button
                data-testid="why-this-read-link"
                onClick={onOpenAuditTrail}
                style={{
                  background: 'none',
                  border: 'none',
                  cursor: 'pointer',
                  color: '#2563eb',
                  fontSize: '12px',
                  fontWeight: 500,
                  padding: 0,
                  textDecoration: 'underline',
                }}
              >
                Why this read?
              </button>
              <button
                data-testid="full-analysis-button"
                onClick={onOpenDeepDive}
                style={{
                  padding: '7px 16px',
                  backgroundColor: '#1d4ed8',
                  color: '#fff',
                  border: 'none',
                  borderRadius: '5px',
                  cursor: 'pointer',
                  fontSize: '12px',
                  fontWeight: 600,
                }}
              >
                Full Analysis
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

export default SidePanel;
