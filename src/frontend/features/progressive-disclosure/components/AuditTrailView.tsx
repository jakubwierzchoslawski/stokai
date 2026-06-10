import React from 'react';

import { useAuditTrail } from '../hooks/useAuditTrail';

export interface AuditTrailViewProps {
  eventId: string | null;
  isOpen: boolean;
  onClose: () => void;
}

function AuditTrailContent({ eventId, onClose }: { eventId: string | null; onClose: () => void }) {
  const { data, isLoading } = useAuditTrail(eventId, true);

  return (
    <div
      data-testid="audit-trail-view"
      className="fixed inset-0 z-[300] flex items-start justify-center overflow-y-auto bg-black/50 pt-12"
    >
      <div className="flex max-h-[80vh] w-[640px] max-w-[90vw] flex-col overflow-hidden rounded-lg bg-surface-1 shadow-[var(--shadow-popover)]">
        {/* Header */}
        <div className="flex shrink-0 items-center justify-between border-b border-border px-5 py-4">
          <h2
            data-testid="audit-trail-title"
            className="m-0 text-base font-bold text-text"
          >
            Why this read?
          </h2>
          <button
            data-testid="audit-trail-close"
            onClick={onClose}
            aria-label="Close audit trail"
            className="cursor-pointer border-none bg-transparent p-1 text-lg text-muted"
          >
            ✕
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-5">
          {isLoading && (
            <p className="text-[13px] text-muted">Loading audit trail…</p>
          )}

          {data && (
            <>
              {data.analogies.length > 0 && (
                <section data-testid="audit-analogies-section" className="mb-5">
                  <h3 className="mb-2.5 mt-0 text-xs uppercase tracking-[0.06em] text-muted">
                    Historical Analogies
                  </h3>
                  <ol className="m-0 pl-4">
                    {[...data.analogies]
                      .sort((a, b) => b.similarity_score - a.similarity_score)
                      .map((a, idx) => (
                        <li
                          key={`${a.event_id}-${idx}`}
                          data-testid={`audit-analogy-${idx}`}
                          className="mb-2 text-[13px]"
                        >
                          <span className="font-medium text-text">{a.headline}</span>{' '}
                          <span className="text-[11px] text-muted">
                            ({a.occurred_at})
                          </span>{' '}
                          <span
                            data-testid={`audit-analogy-score-${idx}`}
                            className="inline-block rounded-full bg-signal/20 px-1.5 py-px text-[11px] font-semibold text-signal"
                          >
                            {Math.round(a.similarity_score * 100)}%
                          </span>
                        </li>
                      ))}
                  </ol>
                </section>
              )}

              <section data-testid="audit-prompt-section" className="mb-5">
                <h3 className="mb-1.5 mt-0 text-xs uppercase tracking-[0.06em] text-muted">
                  Prompt Version
                </h3>
                <code
                  data-testid="audit-prompt-version"
                  className="inline-block rounded bg-surface-2 px-2 py-1 font-mono text-xs text-text"
                >
                  {data.prompt_version || '(not available)'}
                </code>
              </section>

              <section data-testid="audit-reasoning-section" className="mb-5">
                <h3 className="mb-2.5 mt-0 text-xs uppercase tracking-[0.06em] text-muted">
                  Agent Reasoning Chain
                </h3>
                {data.reasoning_steps.length === 0 ? (
                  <p
                    data-testid="no-reasoning-chain"
                    className="text-[13px] italic text-muted"
                  >
                    No reasoning chain available for this event.
                  </p>
                ) : (
                  <ol className="m-0 pl-4">
                    {data.reasoning_steps.map((step, idx) => (
                      <li
                        key={idx}
                        data-testid={`reasoning-step-${idx}`}
                        className="mb-3 text-[13px] leading-[1.5]"
                      >
                        <span
                          data-testid={`step-agent-role-${idx}`}
                          className="mb-1 inline-block rounded px-1.5 py-px text-[11px] font-semibold bg-signal-soft text-signal"
                        >
                          {step.agent_role}
                        </span>
                        <p className="my-1 text-text">{step.content}</p>
                        {step.tool_calls.length > 0 && (
                          <p className="m-0 text-[11px] text-muted">
                            Tools: {step.tool_calls.join(', ')}
                          </p>
                        )}
                      </li>
                    ))}
                  </ol>
                )}
              </section>

              {data.langfuse_trace_url && (
                <section data-testid="langfuse-section">
                  <a
                    data-testid="langfuse-trace-link"
                    href={data.langfuse_trace_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-[13px] text-signal underline"
                  >
                    View full trace in Langfuse
                  </a>
                </section>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

export function AuditTrailView({ eventId, isOpen, onClose }: AuditTrailViewProps) {
  if (!isOpen) {
    return null;
  }

  return <AuditTrailContent eventId={eventId} onClose={onClose} />;
}

export default AuditTrailView;
