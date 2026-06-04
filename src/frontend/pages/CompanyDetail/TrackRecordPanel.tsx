/**
 * TrackRecordPanel — displays recommendation track record with accuracy line.
 *
 * The directional accuracy line is hidden when directional_accuracy_t1d is null
 * (no filled records).
 *
 * PLAN-F-023 TASK-005
 */
import React from 'react';
import type { TrackRecordItem } from './types';

export interface TrackRecordPanelProps {
  trackRecord: TrackRecordItem[];
  directionalAccuracyT1d: number | null;
}

function directionClass(direction: string): string {
  if (direction === 'bullish') return 'track-record__direction track-record__direction--bullish';
  if (direction === 'bearish') return 'track-record__direction track-record__direction--bearish';
  return 'track-record__direction track-record__direction--neutral';
}

function correctnessIcon(correct: boolean | null): string {
  if (correct === true) return '✓';
  if (correct === false) return '✗';
  return '—';
}

export function TrackRecordPanel({
  trackRecord,
  directionalAccuracyT1d,
}: TrackRecordPanelProps): React.ReactElement {
  return (
    <div className="track-record-panel" data-testid="track-record-panel">
      <h3 className="track-record-panel__title">Track Record</h3>

      {directionalAccuracyT1d !== null && (
        <div
          className="track-record-panel__accuracy"
          data-testid="accuracy-line"
          aria-label={`Directional accuracy (1-day): ${(directionalAccuracyT1d * 100).toFixed(1)}%`}
        >
          <span className="track-record-panel__accuracy-label">T+1d Accuracy</span>
          <span className="track-record-panel__accuracy-value">
            {(directionalAccuracyT1d * 100).toFixed(1)}%
          </span>
        </div>
      )}

      {trackRecord.length === 0 ? (
        <p data-testid="track-record-empty">No track record available.</p>
      ) : (
        <table className="track-record-panel__table" data-testid="track-record-table">
          <thead>
            <tr>
              <th>Date</th>
              <th>Signal</th>
              <th>Direction</th>
              <th>Confidence</th>
              <th>T+1d Return</th>
              <th>T+1d Correct</th>
            </tr>
          </thead>
          <tbody>
            {trackRecord.map((item) => (
              <tr
                key={item.rec_id}
                data-testid={`track-record-row-${item.rec_id}`}
              >
                <td>{new Date(item.generated_at).toLocaleDateString('en-US')}</td>
                <td>{item.action_signal}</td>
                <td>
                  <span className={directionClass(item.direction)}>
                    {item.direction}
                  </span>
                </td>
                <td>{(item.confidence * 100).toFixed(0)}%</td>
                <td>
                  {item.actual_t1d !== null
                    ? `${(item.actual_t1d * 100).toFixed(2)}%`
                    : '—'}
                </td>
                <td
                  data-testid={`correct-t1d-${item.rec_id}`}
                  aria-label={
                    item.correct_t1d === true
                      ? 'Correct'
                      : item.correct_t1d === false
                      ? 'Incorrect'
                      : 'Pending'
                  }
                >
                  {correctnessIcon(item.correct_t1d)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
