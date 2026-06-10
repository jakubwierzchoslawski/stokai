import React from 'react';

import { useSidePanelData } from '../hooks/useSidePanelData';
import { ContrarianCallout } from './ContrarianCallout';
import { LowSampleDisclaimer } from './LowSampleDisclaimer';
import { SidePanelAnalogies } from './SidePanelAnalogies';
import { SidePanelSparkline } from './SidePanelSparkline';

function SidePanelSkeleton() {
  return (
    <div data-testid="side-panel-skeleton" className="p-5">
      {[80, 200, 60, 160, 100, 140].map((w, i) => (
        <div
          key={i}
          className="mb-3 rounded bg-surface-2"
          style={{
            height: i === 0 ? '20px' : i === 1 ? '80px' : '14px',
            width: `${w}%`,
            maxWidth: `${w}%`,
          }}
        />
      ))}
    </div>
  );
}

export interface SidePanelProps {
  eventId: string | null;
  isOpen: boolean;
  onClose: () => void;
  onOpenAuditTrail: () => void;
  onOpenDeepDive: () => void;
}

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
      className={`fixed inset-y-0 right-0 z-[200] flex w-[420px] flex-col overflow-y-auto bg-surface-1 shadow-[var(--shadow-popover)] transition-transform duration-[250ms] ease-in-out ${
        isOpen ? 'translate-x-0 pointer-events-auto' : 'translate-x-full pointer-events-none'
      }`}
    >
      {/* Header */}
      <div className="flex shrink-0 items-center justify-between border-b border-border px-[18px] py-4">
        <h2 className="m-0 text-[15px] font-bold text-text">Event Analysis</h2>
        <button
          data-testid="side-panel-close"
          onClick={onClose}
          aria-label="Close side panel"
          className="cursor-pointer border-none bg-transparent p-1 text-lg text-muted"
        >
          ✕
        </button>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto p-[18px]">
        {isOpen && isLoading && <SidePanelSkeleton />}

        {isOpen && data && (
          <>
            {data.is_contrarian && data.contrarian_callout && (
              <ContrarianCallout text={data.contrarian_callout} />
            )}

            <p
              data-testid="side-panel-summary"
              className="mb-3.5 text-[13px] leading-relaxed text-text"
            >
              {data.summary}
            </p>

            {data.sparklines.length > 0 && (
              <div
                data-testid="sparklines-section"
                className="mb-4 grid grid-cols-2 gap-3"
              >
                {data.sparklines.slice(0, 6).map((s) => (
                  <SidePanelSparkline key={s.ticker} ticker={s.ticker} ohlcv_7d={s.ohlcv_7d} />
                ))}
              </div>
            )}

            <div className="mb-2.5">
              <p className="mb-0.5 text-xs text-text">
                Signal:{' '}
                <strong data-testid="side-panel-action-signal">{data.action_signal}</strong>
              </p>
              <p
                data-testid="side-panel-confidence"
                className="mb-0.5 text-xs text-muted"
              >
                Confidence: {(data.confidence * 100).toFixed(0)}% · Sample: {data.sample_size}
              </p>
            </div>

            {data.low_sample && <LowSampleDisclaimer />}

            <div className="mb-4">
              <h3 className="mb-1.5 mt-0 text-xs uppercase tracking-[0.06em] text-muted">
                Rationale
              </h3>
              <p
                data-testid="side-panel-rationale"
                className="m-0 text-[13px] leading-relaxed text-text"
              >
                {data.rationale}
              </p>
            </div>

            <div data-testid="analogies-section" className="mb-4">
              <h3 className="mb-2 mt-0 text-xs uppercase tracking-[0.06em] text-muted">
                Historical Analogies
              </h3>
              <SidePanelAnalogies analogies={data.analogies} />
            </div>

            {data.affected_companies.length > 0 && (
              <div data-testid="affected-companies-section" className="mb-4">
                <h3 className="mb-2 mt-0 text-xs uppercase tracking-[0.06em] text-muted">
                  Affected Holdings
                </h3>
                <table className="w-full border-collapse text-xs">
                  <thead>
                    <tr className="border-b border-border">
                      <th className="px-1.5 py-1 text-left font-semibold text-muted">Company</th>
                      <th className="px-1.5 py-1 text-right font-semibold text-muted">Score</th>
                      <th className="px-1.5 py-1 text-right font-semibold text-muted">Delta</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.affected_companies.map((c) => (
                      <tr
                        key={c.company_id.toString()}
                        data-testid={`company-row-${c.ticker}`}
                        className="border-b border-border-subtle"
                      >
                        <td className="px-1.5 py-1 text-text">
                          <span className="font-semibold">{c.ticker}</span>{' '}
                          <span className="text-muted">{c.name}</span>
                        </td>
                        <td className="px-1.5 py-1 text-right text-text">
                          {c.score.toFixed(1)}
                        </td>
                        <td
                          className={`px-1.5 py-1 text-right ${
                            c.delta >= 0 ? 'text-positive' : 'text-negative'
                          }`}
                        >
                          {c.delta >= 0 ? '+' : ''}{c.delta.toFixed(1)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {data.social_posts && data.social_posts.length > 0 && (
              <div data-testid="social-posts-section" className="mb-4">
                <h3 className="mb-2 mt-0 text-xs uppercase tracking-[0.06em] text-muted">
                  Triggering Posts
                </h3>
                {data.social_posts.map((post) => (
                  <div
                    key={post.post_id}
                    data-testid={`social-post-${post.post_id}`}
                    className="mb-2 rounded bg-surface-2 px-2.5 py-2 text-xs"
                  >
                    <p className="mb-0.5 font-semibold text-muted">
                      {post.source} · {post.timestamp}
                    </p>
                    <p className="m-0 text-text">{post.text}</p>
                  </div>
                ))}
              </div>
            )}

            <div className="mt-4 flex items-center justify-between border-t border-border-subtle pt-3">
              <button
                data-testid="why-this-read-link"
                onClick={onOpenAuditTrail}
                className="cursor-pointer border-none bg-transparent p-0 text-xs font-medium text-signal underline"
              >
                Why this read?
              </button>
              <button
                data-testid="full-analysis-button"
                onClick={onOpenDeepDive}
                className="cursor-pointer rounded-[5px] border-none bg-signal px-4 py-1.5 text-xs font-semibold text-white"
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
