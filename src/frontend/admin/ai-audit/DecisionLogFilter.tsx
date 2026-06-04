/**
 * DecisionLogFilter — filter controls for the AI decision log.
 *
 * Renders: date-range picker, model select, agent_role select,
 * confidence range sliders, action_signal select, company ticker input.
 * Applies filters on 'Apply' button click. Resets on 'Clear'.
 *
 * PLAN-F-029 TASK-007
 */
import React, { useState } from 'react';
import { type DecisionLogFilters } from './hooks/useDecisionLog';

interface Props {
  onApply: (filters: DecisionLogFilters) => void;
  onClear: () => void;
}

const AGENT_ROLES = [
  'narrative_writer',
  'recommendation_synthesizer',
  'classifier',
  'scenario_analyst',
];

const MODELS = ['claude-haiku', 'claude-sonnet', 'claude-opus'];

const ACTION_SIGNALS = ['HOLD', 'BUY_OPP', 'AVOID', 'WATCH'];

export function DecisionLogFilter({ onApply, onClear }: Props) {
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [agentRole, setAgentRole] = useState('');
  const [model, setModel] = useState('');
  const [confidenceMin, setConfidenceMin] = useState<string>('');
  const [confidenceMax, setConfidenceMax] = useState<string>('');
  const [actionSignal, setActionSignal] = useState('');
  const [companyTicker, setCompanyTicker] = useState('');

  function handleApply() {
    const filters: DecisionLogFilters = {};
    if (dateFrom) filters.date_from = dateFrom;
    if (dateTo) filters.date_to = dateTo;
    if (agentRole) filters.agent_role = agentRole;
    if (model) filters.model = model;
    if (confidenceMin !== '') filters.confidence_min = Number(confidenceMin);
    if (confidenceMax !== '') filters.confidence_max = Number(confidenceMax);
    if (actionSignal) filters.action_signal = actionSignal;
    if (companyTicker) filters.company_ticker = companyTicker;
    onApply(filters);
  }

  function handleClear() {
    setDateFrom('');
    setDateTo('');
    setAgentRole('');
    setModel('');
    setConfidenceMin('');
    setConfidenceMax('');
    setActionSignal('');
    setCompanyTicker('');
    onClear();
  }

  return (
    <div className="bg-white border rounded-lg p-4 mb-4" data-testid="decision-log-filter">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1">Date from</label>
          <input
            type="datetime-local"
            value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)}
            className="w-full border rounded px-2 py-1 text-sm"
            data-testid="filter-date-from"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1">Date to</label>
          <input
            type="datetime-local"
            value={dateTo}
            onChange={(e) => setDateTo(e.target.value)}
            className="w-full border rounded px-2 py-1 text-sm"
            data-testid="filter-date-to"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1">Agent role</label>
          <select
            value={agentRole}
            onChange={(e) => setAgentRole(e.target.value)}
            className="w-full border rounded px-2 py-1 text-sm"
            data-testid="filter-agent-role"
          >
            <option value="">All</option>
            {AGENT_ROLES.map((r) => (
              <option key={r} value={r}>{r}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1">Model</label>
          <select
            value={model}
            onChange={(e) => setModel(e.target.value)}
            className="w-full border rounded px-2 py-1 text-sm"
            data-testid="filter-model"
          >
            <option value="">All</option>
            {MODELS.map((m) => (
              <option key={m} value={m}>{m}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1">
            Confidence min (0–1)
          </label>
          <input
            type="number"
            min="0"
            max="1"
            step="0.05"
            value={confidenceMin}
            onChange={(e) => setConfidenceMin(e.target.value)}
            className="w-full border rounded px-2 py-1 text-sm"
            data-testid="filter-confidence-min"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1">
            Confidence max (0–1)
          </label>
          <input
            type="number"
            min="0"
            max="1"
            step="0.05"
            value={confidenceMax}
            onChange={(e) => setConfidenceMax(e.target.value)}
            className="w-full border rounded px-2 py-1 text-sm"
            data-testid="filter-confidence-max"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1">Action signal</label>
          <select
            value={actionSignal}
            onChange={(e) => setActionSignal(e.target.value)}
            className="w-full border rounded px-2 py-1 text-sm"
            data-testid="filter-action-signal"
          >
            <option value="">All</option>
            {ACTION_SIGNALS.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1">Company ticker</label>
          <input
            type="text"
            value={companyTicker}
            onChange={(e) => setCompanyTicker(e.target.value)}
            placeholder="e.g. AAPL"
            className="w-full border rounded px-2 py-1 text-sm"
            data-testid="filter-company-ticker"
          />
        </div>
      </div>
      <div className="flex gap-2 mt-4">
        <button
          onClick={handleApply}
          className="px-4 py-2 bg-blue-600 text-white text-sm rounded hover:bg-blue-700"
          data-testid="filter-apply"
        >
          Apply
        </button>
        <button
          onClick={handleClear}
          className="px-4 py-2 bg-gray-200 text-gray-700 text-sm rounded hover:bg-gray-300"
          data-testid="filter-clear"
        >
          Clear
        </button>
      </div>
    </div>
  );
}
