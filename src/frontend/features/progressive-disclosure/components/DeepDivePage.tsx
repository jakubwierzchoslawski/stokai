/**
 * DeepDivePage.tsx — Level 3 full deep-dive analysis page.
 *
 * PLAN-F-020 TASK-011
 *
 * Route: /events/:eventId/deep-dive
 * Auto-retries every 5 seconds when deep-dive workflow is still running (202 pending).
 * Stops polling after 85 attempts (85 × 5s ≈ 7 min) via useDeepDive.
 *
 * AC-002 (full analysis accessible from side panel)
 */

import React, { useState } from 'react';
import { useParams, Link } from 'react-router-dom';

import { useDeepDive } from '../hooks/useDeepDive';
import { isDeepDivePending } from '../types/disclosure.types';
import type { DeepDiveData, ScenarioNode, AnalogSummary } from '../types/disclosure.types';

// ── Scenario tree (recursive collapsible) ─────────────────────────────────────

function ScenarioNodeView({ node, depth = 0 }: { node: ScenarioNode; depth?: number }) {
  const [expanded, setExpanded] = useState(depth === 0);

  return (
    <div
      data-testid={`scenario-node-${node.label.replace(/\s+/g, '-').toLowerCase()}`}
      style={{ marginLeft: depth * 16, marginBottom: '8px' }}
    >
      <button
        onClick={() => setExpanded((e) => !e)}
        aria-expanded={expanded}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '6px',
          background: 'none',
          border: 'none',
          cursor: node.children.length > 0 ? 'pointer' : 'default',
          padding: '6px 8px',
          borderRadius: '4px',
          backgroundColor: depth === 0 ? '#eff6ff' : '#f9fafb',
          width: '100%',
          textAlign: 'left',
          fontSize: '13px',
          color: '#1e3a8a',
        }}
      >
        {node.children.length > 0 && (
          <span aria-hidden="true">{expanded ? '▼' : '▶'}</span>
        )}
        <span style={{ fontWeight: 600 }}>{node.label}</span>
        <span
          style={{
            marginLeft: 'auto',
            backgroundColor: '#bfdbfe',
            color: '#1e3a8a',
            borderRadius: '9999px',
            padding: '0 7px',
            fontSize: '11px',
            fontWeight: 600,
          }}
        >
          {(node.probability * 100).toFixed(0)}%
        </span>
      </button>
      {expanded && (
        <p style={{ margin: '4px 8px 4px 8px', fontSize: '12px', color: '#6b7280', lineHeight: 1.5 }}>
          {node.description}
        </p>
      )}
      {expanded && node.children.length > 0 && (
        <div style={{ marginTop: '4px' }}>
          {node.children.map((child, i) => (
            <ScenarioNodeView key={i} node={child} depth={depth + 1} />
          ))}
        </div>
      )}
    </div>
  );
}

// ── Analogies table ───────────────────────────────────────────────────────────

type SortKey = 'similarity_score' | 'occurred_at';

function AnalogiesTable({ analogies }: { analogies: AnalogSummary[] }) {
  const [sortKey, setSortKey] = useState<SortKey>('similarity_score');
  const [sortAsc, setSortAsc] = useState(false);

  const sorted = [...analogies].sort((a, b) => {
    const av = a[sortKey];
    const bv = b[sortKey];
    const cmp = av < bv ? -1 : av > bv ? 1 : 0;
    return sortAsc ? cmp : -cmp;
  });

  function handleSort(key: SortKey) {
    if (sortKey === key) {
      setSortAsc((a) => !a);
    } else {
      setSortKey(key);
      setSortAsc(false);
    }
  }

  return (
    <table
      data-testid="analogies-table"
      style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}
    >
      <thead>
        <tr style={{ borderBottom: '2px solid #e5e7eb' }}>
          <th style={{ textAlign: 'left', padding: '6px 8px', color: '#6b7280', fontWeight: 600 }}>
            Headline
          </th>
          <th
            onClick={() => handleSort('occurred_at')}
            data-testid="sort-by-date"
            style={{ textAlign: 'left', padding: '6px 8px', color: '#6b7280', fontWeight: 600, cursor: 'pointer' }}
          >
            Date {sortKey === 'occurred_at' ? (sortAsc ? '↑' : '↓') : ''}
          </th>
          <th
            onClick={() => handleSort('similarity_score')}
            data-testid="sort-by-score"
            style={{ textAlign: 'right', padding: '6px 8px', color: '#6b7280', fontWeight: 600, cursor: 'pointer' }}
          >
            Similarity {sortKey === 'similarity_score' ? (sortAsc ? '↑' : '↓') : ''}
          </th>
        </tr>
      </thead>
      <tbody>
        {sorted.map((a, idx) => (
          <tr
            key={`${a.event_id}-${idx}`}
            data-testid={`analogy-row-${idx}`}
            style={{ borderBottom: '1px solid #f3f4f6' }}
          >
            <td style={{ padding: '6px 8px', color: '#374151' }}>{a.headline}</td>
            <td style={{ padding: '6px 8px', color: '#6b7280', fontSize: '12px' }}>{a.occurred_at}</td>
            <td style={{ textAlign: 'right', padding: '6px 8px' }}>
              <span
                style={{
                  backgroundColor: '#dbeafe',
                  color: '#1d4ed8',
                  borderRadius: '9999px',
                  padding: '1px 7px',
                  fontSize: '11px',
                  fontWeight: 600,
                }}
              >
                {Math.round(a.similarity_score * 100)}%
              </span>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export function DeepDivePage() {
  const { eventId } = useParams<{ eventId: string }>();
  const { data, isLoading } = useDeepDive(eventId ?? null, true);

  // Loading / pending state
  if (isLoading || !data || isDeepDivePending(data)) {
    return (
      <div
        data-testid="deep-dive-loading"
        style={{
          minHeight: '100vh',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          backgroundColor: '#f9fafb',
          fontFamily: 'sans-serif',
        }}
      >
        <div
          style={{
            width: '48px',
            height: '48px',
            border: '4px solid #e5e7eb',
            borderTopColor: '#2563eb',
            borderRadius: '50%',
            animation: 'spin 1s linear infinite',
            marginBottom: '20px',
          }}
          role="progressbar"
          aria-label="Loading"
        />
        <p
          data-testid="deep-dive-loading-text"
          style={{ fontSize: '16px', color: '#374151', textAlign: 'center', maxWidth: '360px' }}
        >
          Generating deep-dive analysis… This may take up to 5 minutes.
        </p>
      </div>
    );
  }

  const deepDive = data as DeepDiveData;

  return (
    <div
      data-testid="deep-dive-page"
      style={{
        minHeight: '100vh',
        backgroundColor: '#f9fafb',
        fontFamily: 'sans-serif',
        padding: '32px',
      }}
    >
      <div style={{ maxWidth: '900px', margin: '0 auto' }}>
        {/* Back link */}
        <Link
          data-testid="back-to-map-link"
          to="/"
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '6px',
            color: '#2563eb',
            fontSize: '13px',
            textDecoration: 'none',
            marginBottom: '24px',
          }}
        >
          ← Back to Intelligence Map
        </Link>

        {/* Memo */}
        <section data-testid="deep-dive-memo" style={{ marginBottom: '32px' }}>
          <h1 style={{ fontSize: '22px', fontWeight: 700, color: '#111827', marginBottom: '16px' }}>
            Deep-Dive Analysis
          </h1>
          <div
            style={{
              backgroundColor: '#fff',
              borderRadius: '8px',
              padding: '24px',
              boxShadow: '0 1px 3px rgba(0,0,0,0.08)',
              fontSize: '14px',
              lineHeight: 1.7,
              color: '#374151',
              whiteSpace: 'pre-wrap',
            }}
          >
            {deepDive.memo}
          </div>
        </section>

        {/* Scenario tree */}
        <section data-testid="scenario-tree-section" style={{ marginBottom: '32px' }}>
          <h2 style={{ fontSize: '16px', fontWeight: 700, color: '#111827', marginBottom: '12px' }}>
            Scenario Analysis
          </h2>
          <div
            style={{
              backgroundColor: '#fff',
              borderRadius: '8px',
              padding: '16px',
              boxShadow: '0 1px 3px rgba(0,0,0,0.08)',
            }}
          >
            {deepDive.scenario_tree === null ? (
              <p
                data-testid="no-scenario-analysis"
                style={{ color: '#9ca3af', fontSize: '13px', fontStyle: 'italic' }}
              >
                No scenario analysis available.
              </p>
            ) : (
              <ScenarioNodeView node={deepDive.scenario_tree} />
            )}
          </div>
        </section>

        {/* Analogies table */}
        {deepDive.analogies.length > 0 && (
          <section data-testid="deep-dive-analogies-section" style={{ marginBottom: '32px' }}>
            <h2 style={{ fontSize: '16px', fontWeight: 700, color: '#111827', marginBottom: '12px' }}>
              Historical Analogies
            </h2>
            <div
              style={{
                backgroundColor: '#fff',
                borderRadius: '8px',
                padding: '16px',
                boxShadow: '0 1px 3px rgba(0,0,0,0.08)',
                overflowX: 'auto',
              }}
            >
              <AnalogiesTable analogies={deepDive.analogies} />
            </div>
          </section>
        )}

        {/* Per-company breakdowns */}
        {deepDive.affected_companies.length > 0 && (
          <section data-testid="deep-dive-companies-section" style={{ marginBottom: '32px' }}>
            <h2 style={{ fontSize: '16px', fontWeight: 700, color: '#111827', marginBottom: '12px' }}>
              Affected Holdings
            </h2>
            <div
              style={{
                backgroundColor: '#fff',
                borderRadius: '8px',
                padding: '16px',
                boxShadow: '0 1px 3px rgba(0,0,0,0.08)',
                overflowX: 'auto',
              }}
            >
              <table
                data-testid="companies-table"
                style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}
              >
                <thead>
                  <tr style={{ borderBottom: '2px solid #e5e7eb' }}>
                    <th style={{ textAlign: 'left', padding: '6px 8px', color: '#6b7280', fontWeight: 600 }}>Company</th>
                    <th style={{ textAlign: 'left', padding: '6px 8px', color: '#6b7280', fontWeight: 600 }}>Ticker</th>
                    <th style={{ textAlign: 'right', padding: '6px 8px', color: '#6b7280', fontWeight: 600 }}>Score</th>
                    <th style={{ textAlign: 'right', padding: '6px 8px', color: '#6b7280', fontWeight: 600 }}>Delta</th>
                  </tr>
                </thead>
                <tbody>
                  {deepDive.affected_companies.map((c, idx) => (
                    <tr
                      key={`${c.company_id}-${idx}`}
                      data-testid={`company-row-${c.ticker}`}
                      style={{ borderBottom: '1px solid #f3f4f6' }}
                    >
                      <td style={{ padding: '6px 8px', color: '#374151' }}>{c.name}</td>
                      <td style={{ padding: '6px 8px', fontWeight: 600, color: '#374151' }}>{c.ticker}</td>
                      <td style={{ textAlign: 'right', padding: '6px 8px', color: '#374151' }}>{c.score.toFixed(1)}</td>
                      <td style={{ textAlign: 'right', padding: '6px 8px', color: c.delta >= 0 ? '#16a34a' : '#dc2626' }}>
                        {c.delta >= 0 ? '+' : ''}{c.delta.toFixed(1)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}
      </div>
    </div>
  );
}

export default DeepDivePage;
