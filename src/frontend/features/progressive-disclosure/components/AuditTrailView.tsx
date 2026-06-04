/**
 * AuditTrailView.tsx — "Why this read?" audit trail overlay panel.
 *
 * PLAN-F-020 TASK-010
 *
 * Full-width overlay (z-index: 300, above side panel at z-index: 200).
 * Shows: historical analogs, prompt SHA, reasoning chain, Langfuse trace link.
 *
 * AC-003
 */

import React from 'react';

import { useAuditTrail } from '../hooks/useAuditTrail';

export interface AuditTrailViewProps {
  eventId: string | null;
  isOpen: boolean;
  onClose: () => void;
}

export function AuditTrailView({ eventId, isOpen, onClose }: AuditTrailViewProps) {
  const { data, isLoading } = useAuditTrail(eventId, isOpen);

  if (!isOpen) {
    return null;
  }

  return (
    <div
      data-testid="audit-trail-view"
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        backgroundColor: 'rgba(0,0,0,0.5)',
        zIndex: 300,
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'flex-start',
        paddingTop: '48px',
        overflowY: 'auto',
      }}
    >
      <div
        style={{
          backgroundColor: '#fff',
          borderRadius: '8px',
          boxShadow: '0 20px 60px rgba(0,0,0,0.2)',
          width: '640px',
          maxWidth: '90vw',
          maxHeight: '80vh',
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        {/* Header */}
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            padding: '16px 20px',
            borderBottom: '1px solid #e5e7eb',
            flexShrink: 0,
          }}
        >
          <h2
            data-testid="audit-trail-title"
            style={{ margin: 0, fontSize: '16px', fontWeight: 700, color: '#111827' }}
          >
            Why this read?
          </h2>
          <button
            data-testid="audit-trail-close"
            onClick={onClose}
            aria-label="Close audit trail"
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
        <div style={{ padding: '20px', overflowY: 'auto', flex: 1 }}>
          {isLoading && (
            <p style={{ color: '#9ca3af', fontSize: '13px' }}>Loading audit trail…</p>
          )}

          {data && (
            <>
              {/* Historical analogies */}
              {data.analogies.length > 0 && (
                <section data-testid="audit-analogies-section" style={{ marginBottom: '20px' }}>
                  <h3
                    style={{
                      margin: '0 0 10px 0',
                      fontSize: '12px',
                      textTransform: 'uppercase',
                      color: '#6b7280',
                      letterSpacing: '0.06em',
                    }}
                  >
                    Historical Analogies
                  </h3>
                  <ol style={{ margin: 0, padding: '0 0 0 18px' }}>
                    {[...data.analogies]
                      .sort((a, b) => b.similarity_score - a.similarity_score)
                      .map((a, idx) => (
                        <li
                          key={`${a.event_id}-${idx}`}
                          data-testid={`audit-analogy-${idx}`}
                          style={{ marginBottom: '8px', fontSize: '13px' }}
                        >
                          <span style={{ fontWeight: 500 }}>{a.headline}</span>{' '}
                          <span style={{ color: '#9ca3af', fontSize: '11px' }}>
                            ({a.occurred_at})
                          </span>{' '}
                          <span
                            data-testid={`audit-analogy-score-${idx}`}
                            style={{
                              display: 'inline-block',
                              backgroundColor: '#dbeafe',
                              color: '#1d4ed8',
                              borderRadius: '9999px',
                              padding: '0 6px',
                              fontSize: '11px',
                              fontWeight: 600,
                            }}
                          >
                            {Math.round(a.similarity_score * 100)}%
                          </span>
                        </li>
                      ))}
                  </ol>
                </section>
              )}

              {/* Prompt SHA */}
              <section data-testid="audit-prompt-section" style={{ marginBottom: '20px' }}>
                <h3
                  style={{
                    margin: '0 0 6px 0',
                    fontSize: '12px',
                    textTransform: 'uppercase',
                    color: '#6b7280',
                    letterSpacing: '0.06em',
                  }}
                >
                  Prompt Version
                </h3>
                <code
                  data-testid="audit-prompt-version"
                  style={{
                    display: 'inline-block',
                    fontFamily: 'monospace',
                    fontSize: '12px',
                    backgroundColor: '#f3f4f6',
                    padding: '4px 8px',
                    borderRadius: '4px',
                    color: '#374151',
                  }}
                >
                  {data.prompt_version || '(not available)'}
                </code>
              </section>

              {/* Reasoning chain */}
              <section data-testid="audit-reasoning-section" style={{ marginBottom: '20px' }}>
                <h3
                  style={{
                    margin: '0 0 10px 0',
                    fontSize: '12px',
                    textTransform: 'uppercase',
                    color: '#6b7280',
                    letterSpacing: '0.06em',
                  }}
                >
                  Agent Reasoning Chain
                </h3>
                {data.reasoning_steps.length === 0 ? (
                  <p
                    data-testid="no-reasoning-chain"
                    style={{ color: '#9ca3af', fontSize: '13px', fontStyle: 'italic' }}
                  >
                    No reasoning chain available for this event.
                  </p>
                ) : (
                  <ol style={{ margin: 0, padding: '0 0 0 18px' }}>
                    {data.reasoning_steps.map((step, idx) => (
                      <li
                        key={idx}
                        data-testid={`reasoning-step-${idx}`}
                        style={{
                          marginBottom: '12px',
                          fontSize: '13px',
                          lineHeight: 1.5,
                        }}
                      >
                        <span
                          data-testid={`step-agent-role-${idx}`}
                          style={{
                            display: 'inline-block',
                            backgroundColor: '#ede9fe',
                            color: '#5b21b6',
                            borderRadius: '4px',
                            padding: '1px 6px',
                            fontSize: '11px',
                            fontWeight: 600,
                            marginBottom: '4px',
                          }}
                        >
                          {step.agent_role}
                        </span>
                        <p style={{ margin: '4px 0 2px 0', color: '#374151' }}>{step.content}</p>
                        {step.tool_calls.length > 0 && (
                          <p
                            style={{ margin: 0, fontSize: '11px', color: '#9ca3af' }}
                          >
                            Tools: {step.tool_calls.join(', ')}
                          </p>
                        )}
                      </li>
                    ))}
                  </ol>
                )}
              </section>

              {/* Langfuse trace link */}
              {data.langfuse_trace_url && (
                <section data-testid="langfuse-section">
                  <a
                    data-testid="langfuse-trace-link"
                    href={data.langfuse_trace_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{
                      color: '#2563eb',
                      fontSize: '13px',
                      textDecoration: 'underline',
                    }}
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

export default AuditTrailView;
