/**
 * RecommendationTrackRecord — AI Recommendation Track Record component.
 *
 * Displays the historical recommendation track record and ex-post accuracy
 * for a company on the Company Detail screen.
 *
 * Features:
 *   - Collapsible section "AI Recommendation Track Record"
 *   - Summary row: direction-correct percentages for T+1d and T+1w
 *   - Table of TrackRecordEntry rows with disclaimer icon for low-sample rows
 *   - Empty, loading, and error states
 *
 * Disclaimer accessibility (AC-003): When disclaimer_required=true, a warning
 * icon with the disclaimer text in its `title` attribute is rendered. This
 * makes the disclaimer visible without user interaction for keyboard and
 * screen reader users.
 *
 * PLAN-N-012 TASK-005
 */
import React, { useState } from 'react';
import {
  useRecommendationTrackRecord,
  TrackRecordEntry,
} from './hooks/useRecommendationTrackRecord';

export interface RecommendationTrackRecordProps {
  companyId: string;
  limit?: number;
}

const DISCLAIMER_TEXT = 'Based on fewer than 5 historical cases — treat with caution';

function formatPct(pct: number | null): string {
  if (pct === null) return '—'; // em dash
  return `${pct.toFixed(1)}%`;
}

function formatDate(isoString: string): string {
  try {
    return new Date(isoString).toLocaleDateString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  } catch {
    return isoString;
  }
}

function ConfidenceCell({ confidence }: { confidence: number }): React.ReactElement {
  const pct = Math.round(confidence * 100);
  const colorClass =
    pct >= 75
      ? 'track-record__confidence--high'
      : pct >= 50
      ? 'track-record__confidence--medium'
      : 'track-record__confidence--low';
  return (
    <span className={`track-record__confidence ${colorClass}`}>{pct}%</span>
  );
}

function DisclaimerIcon(): React.ReactElement {
  return (
    <span
      className="track-record__disclaimer-icon"
      role="img"
      aria-label="Low sample size warning"
      title={DISCLAIMER_TEXT}
      data-testid="disclaimer-icon"
    >
      &#9888;
    </span>
  );
}

function SkeletonRows({ count }: { count: number }): React.ReactElement {
  return (
    <>
      {Array.from({ length: count }).map((_, i) => (
        <tr key={i} className="track-record__skeleton-row" data-testid="skeleton-row">
          {Array.from({ length: 8 }).map((_, j) => (
            <td key={j}>
              <span className="track-record__skeleton-cell" />
            </td>
          ))}
        </tr>
      ))}
    </>
  );
}

function TrackRecordRow({ entry }: { entry: TrackRecordEntry }): React.ReactElement {
  return (
    <tr className="track-record__row" data-testid="track-record-row">
      <td className="track-record__cell track-record__cell--date">
        {formatDate(entry.generated_at)}
      </td>
      <td className="track-record__cell track-record__cell--signal">
        {entry.action_signal}
      </td>
      <td className="track-record__cell track-record__cell--confidence">
        <ConfidenceCell confidence={entry.confidence} />
      </td>
      <td className="track-record__cell track-record__cell--sample">
        {entry.sample_size}
      </td>
      <td className="track-record__cell track-record__cell--t1d">
        {entry.actual_t1d !== null ? `${entry.actual_t1d > 0 ? '+' : ''}${entry.actual_t1d.toFixed(2)}%` : '—'}
      </td>
      <td className="track-record__cell track-record__cell--t1w">
        {entry.actual_t1w !== null ? `${entry.actual_t1w > 0 ? '+' : ''}${entry.actual_t1w.toFixed(2)}%` : '—'}
      </td>
      <td className="track-record__cell track-record__cell--disclaimer">
        {entry.disclaimer_required ? <DisclaimerIcon /> : null}
      </td>
    </tr>
  );
}

export function RecommendationTrackRecord({
  companyId,
  limit = 50,
}: RecommendationTrackRecordProps): React.ReactElement {
  const [isOpen, setIsOpen] = useState(true);
  const { data, isLoading, isError, refetch } = useRecommendationTrackRecord({
    companyId,
    limit,
  });

  return (
    <section
      className="track-record"
      data-testid="recommendation-track-record"
      aria-label="AI Recommendation Track Record"
    >
      <button
        className="track-record__toggle"
        onClick={() => setIsOpen((prev) => !prev)}
        aria-expanded={isOpen}
        data-testid="track-record-toggle"
      >
        AI Recommendation Track Record
        <span className="track-record__toggle-icon">{isOpen ? '▲' : '▼'}</span>
      </button>

      {isOpen && (
        <div className="track-record__content">
          {isLoading && (
            <div data-testid="track-record-loading">
              <table className="track-record__table" aria-label="Loading track record">
                <tbody>
                  <SkeletonRows count={5} />
                </tbody>
              </table>
            </div>
          )}

          {isError && (
            <div
              role="alert"
              className="track-record__error"
              data-testid="track-record-error"
            >
              Could not load track record.{' '}
              <button onClick={() => void refetch()} className="track-record__retry">
                Retry
              </button>
            </div>
          )}

          {!isLoading && !isError && data && (
            <>
              <div
                className="track-record__summary"
                data-testid="track-record-summary"
              >
                <span>
                  Direction correct (T+1d):{' '}
                  <strong data-testid="direction-t1d">
                    {formatPct(data.direction_correct_t1d_pct)}
                  </strong>
                </span>
                {' | '}
                <span>
                  Direction correct (T+1w):{' '}
                  <strong data-testid="direction-t1w">
                    {formatPct(data.direction_correct_t1w_pct)}
                  </strong>
                </span>
              </div>

              {data.entries.length === 0 ? (
                <p
                  className="track-record__empty"
                  data-testid="track-record-empty"
                >
                  No recommendations recorded yet for this company.
                </p>
              ) : (
                <table className="track-record__table">
                  <thead>
                    <tr>
                      <th scope="col">Date</th>
                      <th scope="col">Signal</th>
                      <th scope="col">Confidence</th>
                      <th scope="col">Sample Size</th>
                      <th scope="col">T+1d Actual</th>
                      <th scope="col">T+1w Actual</th>
                      <th scope="col">Disclaimer</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.entries.map((entry) => (
                      <TrackRecordRow key={entry.rec_id} entry={entry} />
                    ))}
                  </tbody>
                </table>
              )}
            </>
          )}
        </div>
      )}
    </section>
  );
}

export default RecommendationTrackRecord;
