import React from 'react';

import { usePopupData } from '../hooks/usePopupData';
import { LowSampleDisclaimer } from './LowSampleDisclaimer';

const INTENSITY_BG: Record<number, string> = {
  1: 'var(--neutral)',
  2: 'var(--signal)',
  3: 'var(--warning)',
  4: 'var(--pulse-high)',
  5: 'var(--pulse-extreme)',
};

function IntensityBadge({ intensity }: { intensity: number }) {
  return (
    <span
      data-testid="intensity-badge"
      className="ml-1 inline-block rounded px-1.5 py-px text-[11px] font-bold text-white"
      style={{ backgroundColor: INTENSITY_BG[intensity] ?? 'var(--neutral)' }}
    >
      {intensity}
    </span>
  );
}

function PopupSkeleton() {
  return (
    <div data-testid="popup-skeleton" className="w-[280px] p-3">
      <div className="mb-2 h-3 w-[60px] rounded bg-surface-2" />
      <div className="mb-1.5 h-4 w-[200px] rounded bg-surface-2" />
      <div className="h-3 w-[120px] rounded bg-surface-2" />
    </div>
  );
}

export interface EventPopupProps {
  eventId: string;
  onExpand: () => void;
  onClose: () => void;
}

export function EventPopup({ eventId, onExpand, onClose }: EventPopupProps) {
  const { data, isLoading } = usePopupData(eventId);

  if (isLoading || !data) {
    return <PopupSkeleton />;
  }

  return (
    <div
      data-testid="event-popup"
      className="w-[280px] max-w-[300px] p-3 text-[13px] leading-[1.5] text-text"
    >
      <div className="mb-1.5 flex items-center">
        <span data-testid="category" className="text-[11px] uppercase text-muted">
          {data.category.join(' · ')}
        </span>
        <IntensityBadge intensity={data.intensity} />
      </div>

      <p data-testid="headline" className="mb-1 text-[13px] font-semibold text-text">
        {data.headline}
      </p>

      <p data-testid="time-ago" className="mb-0.5 text-[11px] text-muted">
        {data.time_ago}
      </p>
      <p data-testid="location" className="mb-2 text-[11px] text-muted">
        {data.location}
      </p>

      <p className="mb-1.5 text-xs text-text">
        <span data-testid="exposed-holdings-count" className="font-semibold">
          {data.exposed_holdings_count}
        </span>{' '}
        {data.exposed_holdings_count === 1 ? 'holding' : 'holdings'} exposed
      </p>

      {data.tickers_with_delta.length > 0 && (
        <div data-testid="tickers-list" className="mb-2 flex flex-wrap gap-1">
          {data.tickers_with_delta.map((t) => {
            const positive = t.score_delta >= 0;
            return (
              <span
                key={t.ticker}
                data-testid={`ticker-${t.ticker}`}
                className={`inline-flex items-center gap-0.5 rounded px-1 py-px text-[11px] font-semibold ${
                  positive ? 'bg-positive/10 text-positive' : 'bg-negative/10 text-negative'
                }`}
              >
                {t.ticker}
                <span>{positive ? '+' : '−'}{Math.abs(t.score_delta).toFixed(1)}</span>
              </span>
            );
          })}
        </div>
      )}

      <p className="mb-0.5 text-xs text-text">
        Signal: <strong data-testid="action-signal">{data.action_signal}</strong>
      </p>

      <p data-testid="confidence" className="mb-2 text-xs text-muted">
        Confidence: {(data.confidence * 100).toFixed(0)}%
      </p>

      {data.low_sample && <LowSampleDisclaimer />}

      <div className="mt-2.5 flex justify-between">
        <button
          data-testid="expand-button"
          onClick={onExpand}
          className="cursor-pointer rounded-[5px] bg-signal px-3.5 py-1.5 text-xs font-semibold text-white"
        >
          Expand
        </button>
        <button
          data-testid="close-button"
          onClick={onClose}
          aria-label="Close popup"
          className="cursor-pointer rounded-[5px] border border-border px-2.5 py-1.5 text-xs text-muted"
        >
          ✕
        </button>
      </div>
    </div>
  );
}

export default EventPopup;
