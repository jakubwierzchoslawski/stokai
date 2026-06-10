import React, { useState } from 'react';
import { useParams, Link } from 'react-router-dom';

import { useDeepDive } from '../hooks/useDeepDive';
import { isDeepDivePending } from '../types/disclosure.types';
import type { DeepDiveData, ScenarioNode, AnalogSummary } from '../types/disclosure.types';

function ScenarioNodeView({ node, depth = 0 }: { node: ScenarioNode; depth?: number }) {
  const [expanded, setExpanded] = useState(depth === 0);

  return (
    <div
      data-testid={`scenario-node-${node.label.replace(/\s+/g, '-').toLowerCase()}`}
      className="mb-2"
      style={{ marginLeft: depth * 16 }}
    >
      <button
        onClick={() => setExpanded((e) => !e)}
        aria-expanded={expanded}
        className={`flex w-full cursor-pointer items-center gap-1.5 rounded border-none px-2 py-1.5 text-left text-[13px] text-text ${
          depth === 0 ? 'bg-signal/10' : 'bg-surface-2'
        } ${node.children.length > 0 ? 'cursor-pointer' : 'cursor-default'}`}
      >
        {node.children.length > 0 && (
          <span aria-hidden="true">{expanded ? '▼' : '▶'}</span>
        )}
        <span className="font-semibold">{node.label}</span>
        <span className="ml-auto rounded-full bg-signal/20 px-1.5 py-px text-[11px] font-semibold text-signal">
          {(node.probability * 100).toFixed(0)}%
        </span>
      </button>
      {expanded && (
        <p className="mx-2 my-1 text-xs leading-[1.5] text-muted">{node.description}</p>
      )}
      {expanded && node.children.length > 0 && (
        <div className="mt-1">
          {node.children.map((child, i) => (
            <ScenarioNodeView key={i} node={child} depth={depth + 1} />
          ))}
        </div>
      )}
    </div>
  );
}

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
    <table data-testid="analogies-table" className="w-full border-collapse text-[13px]">
      <thead>
        <tr className="border-b-2 border-border">
          <th className="px-2 py-1.5 text-left font-semibold text-muted">Headline</th>
          <th
            onClick={() => handleSort('occurred_at')}
            data-testid="sort-by-date"
            className="cursor-pointer px-2 py-1.5 text-left font-semibold text-muted"
          >
            Date {sortKey === 'occurred_at' ? (sortAsc ? '↑' : '↓') : ''}
          </th>
          <th
            onClick={() => handleSort('similarity_score')}
            data-testid="sort-by-score"
            className="cursor-pointer px-2 py-1.5 text-right font-semibold text-muted"
          >
            Similarity {sortKey === 'similarity_score' ? (sortAsc ? '↑' : '↓') : ''}
          </th>
        </tr>
      </thead>
      <tbody>
        {sorted.map((a, idx) => (
          <tr key={`${a.event_id}-${idx}`} data-testid={`analogy-row-${idx}`} className="border-b border-border-subtle">
            <td className="px-2 py-1.5 text-text">{a.headline}</td>
            <td className="px-2 py-1.5 text-xs text-muted">{a.occurred_at}</td>
            <td className="px-2 py-1.5 text-right">
              <span className="rounded-full bg-signal/20 px-1.5 py-px text-[11px] font-semibold text-signal">
                {Math.round(a.similarity_score * 100)}%
              </span>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function DeepDivePage() {
  const { eventId } = useParams<{ eventId: string }>();
  const { data, isLoading } = useDeepDive(eventId ?? null, true);

  if (isLoading || !data || isDeepDivePending(data)) {
    return (
      <div
        data-testid="deep-dive-loading"
        className="flex min-h-screen flex-col items-center justify-center bg-surface-0"
      >
        <div
          className="mb-5 h-12 w-12 animate-spin rounded-full border-4 border-surface-3 border-t-signal"
          role="progressbar"
          aria-label="Loading"
        />
        <p
          data-testid="deep-dive-loading-text"
          className="max-w-[360px] text-center text-base text-text"
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
      className="min-h-screen bg-surface-0 p-8"
    >
      <div className="mx-auto max-w-[900px]">
        <Link
          data-testid="back-to-map-link"
          to="/"
          className="mb-6 inline-flex items-center gap-1.5 text-[13px] text-signal no-underline"
        >
          ← Back to Intelligence Map
        </Link>

        <section data-testid="deep-dive-memo" className="mb-8">
          <h1 className="mb-4 text-[22px] font-bold text-text">Deep-Dive Analysis</h1>
          <div className="rounded-lg bg-surface-1 p-6 text-sm leading-[1.7] text-text shadow-[var(--shadow-md)] whitespace-pre-wrap">
            {deepDive.memo}
          </div>
        </section>

        <section data-testid="scenario-tree-section" className="mb-8">
          <h2 className="mb-3 text-base font-bold text-text">Scenario Analysis</h2>
          <div className="rounded-lg bg-surface-1 p-4 shadow-[var(--shadow-md)]">
            {deepDive.scenario_tree === null ? (
              <p data-testid="no-scenario-analysis" className="text-[13px] italic text-muted">
                No scenario analysis available.
              </p>
            ) : (
              <ScenarioNodeView node={deepDive.scenario_tree} />
            )}
          </div>
        </section>

        {deepDive.analogies.length > 0 && (
          <section data-testid="deep-dive-analogies-section" className="mb-8">
            <h2 className="mb-3 text-base font-bold text-text">Historical Analogies</h2>
            <div className="overflow-x-auto rounded-lg bg-surface-1 p-4 shadow-[var(--shadow-md)]">
              <AnalogiesTable analogies={deepDive.analogies} />
            </div>
          </section>
        )}

        {deepDive.affected_companies.length > 0 && (
          <section data-testid="deep-dive-companies-section" className="mb-8">
            <h2 className="mb-3 text-base font-bold text-text">Affected Holdings</h2>
            <div className="overflow-x-auto rounded-lg bg-surface-1 p-4 shadow-[var(--shadow-md)]">
              <table data-testid="companies-table" className="w-full border-collapse text-[13px]">
                <thead>
                  <tr className="border-b-2 border-border">
                    <th className="px-2 py-1.5 text-left font-semibold text-muted">Company</th>
                    <th className="px-2 py-1.5 text-left font-semibold text-muted">Ticker</th>
                    <th className="px-2 py-1.5 text-right font-semibold text-muted">Score</th>
                    <th className="px-2 py-1.5 text-right font-semibold text-muted">Delta</th>
                  </tr>
                </thead>
                <tbody>
                  {deepDive.affected_companies.map((c, idx) => (
                    <tr
                      key={`${c.company_id}-${idx}`}
                      data-testid={`company-row-${c.ticker}`}
                      className="border-b border-border-subtle"
                    >
                      <td className="px-2 py-1.5 text-text">{c.name}</td>
                      <td className="px-2 py-1.5 font-semibold text-text">{c.ticker}</td>
                      <td className="px-2 py-1.5 text-right text-text">{c.score.toFixed(1)}</td>
                      <td className={`px-2 py-1.5 text-right ${c.delta >= 0 ? 'text-positive' : 'text-negative'}`}>
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
