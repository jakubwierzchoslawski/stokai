/**
 * EventPopup.tsx — Level 1 popup for map pulse clicks.
 *
 * PLAN-F-020 TASK-006
 *
 * Renders inside a MapLibre GL JS Popup via a React portal. Shows event essentials
 * (category, intensity, headline, time_ago, location, exposed_holdings, tickers,
 * action_signal, confidence) and an "Expand" button that opens the side panel.
 *
 * Low-sample disclaimer is rendered inline when PopupData.low_sample=true.
 *
 * AC-001, AC-005
 */

import React from 'react';

import { usePopupData } from '../hooks/usePopupData';
import { LowSampleDisclaimer } from './LowSampleDisclaimer';

// ── Intensity color map (1–5) ─────────────────────────────────────────────────

const INTENSITY_COLORS: Record<number, string> = {
  1: '#6b7280', // gray-500
  2: '#3b82f6', // blue-500
  3: '#f59e0b', // amber-500
  4: '#f97316', // orange-500
  5: '#ef4444', // red-500
};

function IntensityBadge({ intensity }: { intensity: number }) {
  const color = INTENSITY_COLORS[intensity] ?? '#6b7280';
  return (
    <span
      data-testid="intensity-badge"
      style={{
        display: 'inline-block',
        backgroundColor: color,
        color: '#fff',
        borderRadius: '4px',
        padding: '1px 6px',
        fontSize: '11px',
        fontWeight: 700,
        marginLeft: '4px',
      }}
    >
      {intensity}
    </span>
  );
}

// ── Skeleton ──────────────────────────────────────────────────────────────────

function PopupSkeleton() {
  return (
    <div
      data-testid="popup-skeleton"
      style={{ width: '280px', padding: '12px', fontFamily: 'sans-serif' }}
    >
      <div
        style={{
          height: '12px',
          width: '60px',
          backgroundColor: '#e5e7eb',
          borderRadius: '4px',
          marginBottom: '8px',
        }}
      />
      <div
        style={{
          height: '16px',
          width: '200px',
          backgroundColor: '#e5e7eb',
          borderRadius: '4px',
          marginBottom: '6px',
        }}
      />
      <div
        style={{
          height: '12px',
          width: '120px',
          backgroundColor: '#e5e7eb',
          borderRadius: '4px',
        }}
      />
    </div>
  );
}

// ── Props ─────────────────────────────────────────────────────────────────────

export interface EventPopupProps {
  eventId: string;
  onExpand: () => void;
  onClose: () => void;
}

// ── Component ─────────────────────────────────────────────────────────────────

export function EventPopup({ eventId, onExpand, onClose }: EventPopupProps) {
  const { data, isLoading } = usePopupData(eventId);

  if (isLoading || !data) {
    return <PopupSkeleton />;
  }

  return (
    <div
      data-testid="event-popup"
      style={{
        width: '280px',
        maxWidth: '300px',
        padding: '12px',
        fontFamily: 'sans-serif',
        fontSize: '13px',
        lineHeight: 1.5,
      }}
    >
      {/* Header: category + intensity */}
      <div style={{ display: 'flex', alignItems: 'center', marginBottom: '6px' }}>
        <span
          data-testid="category"
          style={{ fontSize: '11px', color: '#6b7280', textTransform: 'uppercase' }}
        >
          {data.category.join(' · ')}
        </span>
        <IntensityBadge intensity={data.intensity} />
      </div>

      {/* Headline */}
      <p
        data-testid="headline"
        style={{ margin: '0 0 4px 0', fontWeight: 600, fontSize: '13px' }}
      >
        {data.headline}
      </p>

      {/* Time + location */}
      <p data-testid="time-ago" style={{ margin: '0 0 2px 0', color: '#9ca3af', fontSize: '11px' }}>
        {data.time_ago}
      </p>
      <p data-testid="location" style={{ margin: '0 0 8px 0', color: '#6b7280', fontSize: '11px' }}>
        {data.location}
      </p>

      {/* Exposed holdings */}
      <p style={{ margin: '0 0 6px 0', fontSize: '12px' }}>
        <span data-testid="exposed-holdings-count" style={{ fontWeight: 600 }}>
          {data.exposed_holdings_count}
        </span>{' '}
        {data.exposed_holdings_count === 1 ? 'holding' : 'holdings'} exposed
      </p>

      {/* Tickers with delta */}
      {data.tickers_with_delta.length > 0 && (
        <div
          data-testid="tickers-list"
          style={{ display: 'flex', flexWrap: 'wrap', gap: '4px', marginBottom: '8px' }}
        >
          {data.tickers_with_delta.map((t) => {
            const positive = t.score_delta >= 0;
            return (
              <span
                key={t.ticker}
                data-testid={`ticker-${t.ticker}`}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '2px',
                  backgroundColor: positive ? '#dcfce7' : '#fee2e2',
                  color: positive ? '#166534' : '#991b1b',
                  borderRadius: '4px',
                  padding: '1px 5px',
                  fontSize: '11px',
                  fontWeight: 600,
                }}
              >
                {t.ticker}
                <span>{positive ? '+' : '−'}{Math.abs(t.score_delta).toFixed(1)}</span>
              </span>
            );
          })}
        </div>
      )}

      {/* Action signal */}
      <p style={{ margin: '0 0 2px 0', fontSize: '12px' }}>
        Signal:{' '}
        <strong data-testid="action-signal">{data.action_signal}</strong>
      </p>

      {/* Confidence */}
      <p data-testid="confidence" style={{ margin: '0 0 8px 0', fontSize: '12px', color: '#6b7280' }}>
        Confidence: {(data.confidence * 100).toFixed(0)}%
      </p>

      {/* Low sample disclaimer */}
      {data.low_sample && <LowSampleDisclaimer />}

      {/* Actions */}
      <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '10px' }}>
        <button
          data-testid="expand-button"
          onClick={onExpand}
          style={{
            padding: '6px 14px',
            backgroundColor: '#2563eb',
            color: '#fff',
            border: 'none',
            borderRadius: '5px',
            cursor: 'pointer',
            fontSize: '12px',
            fontWeight: 600,
          }}
        >
          Expand
        </button>
        <button
          data-testid="close-button"
          onClick={onClose}
          aria-label="Close popup"
          style={{
            padding: '6px 10px',
            backgroundColor: 'transparent',
            color: '#6b7280',
            border: '1px solid #e5e7eb',
            borderRadius: '5px',
            cursor: 'pointer',
            fontSize: '12px',
          }}
        >
          ✕
        </button>
      </div>
    </div>
  );
}

export default EventPopup;
