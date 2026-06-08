/**
 * ScoreBreakdownPanel — displays per-indicator score cards with sparklines.
 *
 * Each indicator renders as a card with:
 *   - Indicator name and formula summary
 *   - Weight, raw value, score, geo-adjusted score
 *   - Sub-score contribution
 *   - Sparkline (30 daily values, oldest-first)
 *
 * PLAN-F-023 TASK-005
 */
import React from 'react';
import type { ScoreBreakdownItem } from './types';

export interface ScoreBreakdownPanelProps {
  scores: ScoreBreakdownItem[];
}

function ScoreCard({ item }: { item: ScoreBreakdownItem }): React.ReactElement {
  return (
    <div
      className="score-card"
      data-testid={`score-card-${item.indicator_id}`}
      role="article"
      aria-label={item.indicator_name}
    >
      <div className="score-card__header">
        <span className="score-card__name">{item.indicator_name}</span>
        <span className="score-card__score" data-testid="score-value">
          {item.score.toFixed(1)}
        </span>
      </div>
      <p className="score-card__formula" title={item.formula_summary}>
        {item.formula_summary}
      </p>
      <dl className="score-card__details">
        <dt>Weight</dt>
        <dd>{(item.weight * 100).toFixed(0)}%</dd>

        <dt>Raw value</dt>
        <dd>{item.raw_value !== null ? item.raw_value.toFixed(4) : '—'}</dd>

        <dt>Geo-adjusted</dt>
        <dd>{item.geo_adjusted !== null ? item.geo_adjusted.toFixed(1) : '—'}</dd>

        <dt>Contribution</dt>
        <dd>{item.sub_score_contribution.toFixed(2)}</dd>
      </dl>
      {item.sparkline.length > 0 && (
        <div className="score-card__sparkline" data-testid="sparkline" aria-hidden="true">
          {item.sparkline.map((v, i) => (
            <span
              key={i}
              className="score-card__sparkline-point"
              style={{ height: `${Math.max(2, v / 100 * 40)}px` }}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export function ScoreBreakdownPanel({ scores }: ScoreBreakdownPanelProps): React.ReactElement {
  return (
    <div className="score-breakdown-panel" data-testid="score-breakdown-panel">
      <h3 className="score-breakdown-panel__title">Score Breakdown</h3>
      {scores.length === 0 ? (
        <p data-testid="score-breakdown-empty">No score data available.</p>
      ) : (
        <div className="score-breakdown-panel__grid">
          {scores.map((item) => (
            <ScoreCard key={item.indicator_id} item={item} />
          ))}
        </div>
      )}
    </div>
  );
}
