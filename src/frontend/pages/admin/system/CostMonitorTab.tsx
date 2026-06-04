/**
 * pages/admin/system/CostMonitorTab — Monthly AI + infrastructure budget monitor.
 *
 * Displays:
 *   - Progress bar showing pct_of_budget (green <80%, amber 80-99%, red >=100%)
 *   - Combined total prominently (e.g. "June 2026 total: $47.32 / $100.00")
 *   - Two tables side by side:
 *       "AI Costs by Model"   (Model, Cost USD, Call Count)
 *       "Infrastructure Costs" (Category, Description, Cost USD)
 *   - Reminder to update infrastructure costs by the 5th of each month.
 *
 * Fetches via TanStack Query with a 5-minute stale time.
 * Requires no additional auth — admin layout already enforces role="admin".
 *
 * PLAN-N-005 TASK-007
 */
import React from 'react';
import { useQuery } from '@tanstack/react-query';

// ── Types ───────────────────────────────────────────────────────────────────────

export interface AiModelCostLine {
  model_id: string;
  cost_usd: number;
  call_count: number;
}

export interface InfraCostLine {
  category: string;
  description: string;
  cost_usd: number;
}

export interface MonthlyBudgetSummary {
  billing_month: string;       // ISO date string, e.g. "2026-06-01"
  ai_costs: AiModelCostLine[];
  ai_total_usd: number;
  infra_costs: InfraCostLine[];
  infra_total_usd: number;
  combined_total_usd: number;
  budget_usd: number;
  pct_of_budget: number;
  alert_threshold_usd: number;
  over_alert_threshold: boolean;
  over_budget: boolean;
}

// ── Query key ────────────────────────────────────────────────────────────────────

export const COST_MONITOR_KEY = ['admin', 'cost-monitor'] as const;

// ── API helper ────────────────────────────────────────────────────────────────────

async function fetchCostMonitor(): Promise<MonthlyBudgetSummary> {
  const resp = await fetch('/api/v1/admin/cost-monitor', {
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err?.error?.message ?? `HTTP ${resp.status}`);
  }
  const body = await resp.json();
  return body.data as MonthlyBudgetSummary;
}

// ── Budget progress bar ───────────────────────────────────────────────────────────

function BudgetProgressBar({ pct }: { pct: number }) {
  const clamped = Math.min(pct, 100);

  let barColor: string;
  let labelColor: string;
  if (pct >= 100) {
    barColor = 'bg-red-600';
    labelColor = 'text-red-700';
  } else if (pct >= 80) {
    barColor = 'bg-amber-500';
    labelColor = 'text-amber-700';
  } else {
    barColor = 'bg-green-500';
    labelColor = 'text-green-700';
  }

  return (
    <div data-testid="budget-progress-bar">
      <div className="flex justify-between mb-1">
        <span className={`text-sm font-medium ${labelColor}`}>
          {pct.toFixed(1)}% of ${100} monthly budget
        </span>
        {pct >= 100 && (
          <span className="text-sm font-bold text-red-700" data-testid="over-budget-badge">
            OVER BUDGET
          </span>
        )}
        {pct >= 80 && pct < 100 && (
          <span className="text-sm font-bold text-amber-700" data-testid="alert-threshold-badge">
            ALERT: 80% threshold reached
          </span>
        )}
      </div>
      <div className="w-full bg-gray-200 rounded-full h-4 overflow-hidden">
        <div
          className={`h-4 rounded-full transition-all ${barColor}`}
          style={{ width: `${clamped}%` }}
          data-testid="budget-bar-fill"
          aria-valuenow={pct}
          aria-valuemin={0}
          aria-valuemax={100}
          role="progressbar"
        />
      </div>
    </div>
  );
}

// ── Helper: format billing month label ────────────────────────────────────────────

function formatBillingMonth(isoDate: string): string {
  const d = new Date(isoDate + 'T00:00:00Z');
  return d.toLocaleDateString('en-US', { month: 'long', year: 'numeric', timeZone: 'UTC' });
}

// ── AI costs table ────────────────────────────────────────────────────────────────

function AiCostsTable({ lines, total }: { lines: AiModelCostLine[]; total: number }) {
  return (
    <div data-testid="ai-costs-table-container">
      <h3 className="text-base font-semibold mb-2">AI Costs by Model</h3>
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-gray-200 text-sm" data-testid="ai-costs-table">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                Model
              </th>
              <th className="px-3 py-2 text-right text-xs font-medium text-gray-500 uppercase">
                Cost USD
              </th>
              <th className="px-3 py-2 text-right text-xs font-medium text-gray-500 uppercase">
                Calls
              </th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-100">
            {lines.length === 0 ? (
              <tr>
                <td colSpan={3} className="px-3 py-3 text-gray-400 italic text-center">
                  No AI cost records this month
                </td>
              </tr>
            ) : (
              lines.map((line) => (
                <tr key={line.model_id} data-testid={`ai-row-${line.model_id}`}>
                  <td className="px-3 py-2 font-mono text-gray-800">{line.model_id}</td>
                  <td className="px-3 py-2 text-right text-gray-700">
                    ${line.cost_usd.toFixed(4)}
                  </td>
                  <td className="px-3 py-2 text-right text-gray-600">{line.call_count}</td>
                </tr>
              ))
            )}
            <tr className="bg-gray-50 font-semibold">
              <td className="px-3 py-2 text-gray-800">AI Total</td>
              <td className="px-3 py-2 text-right text-gray-800" data-testid="ai-total">
                ${total.toFixed(4)}
              </td>
              <td />
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Infrastructure costs table ────────────────────────────────────────────────────

function InfraCostsTable({ lines, total }: { lines: InfraCostLine[]; total: number }) {
  return (
    <div data-testid="infra-costs-table-container">
      <h3 className="text-base font-semibold mb-2">Infrastructure Costs</h3>
      <div className="overflow-x-auto">
        <table
          className="min-w-full divide-y divide-gray-200 text-sm"
          data-testid="infra-costs-table"
        >
          <thead className="bg-gray-50">
            <tr>
              <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                Category
              </th>
              <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                Description
              </th>
              <th className="px-3 py-2 text-right text-xs font-medium text-gray-500 uppercase">
                Cost USD
              </th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-100">
            {lines.length === 0 ? (
              <tr>
                <td colSpan={3} className="px-3 py-3 text-gray-400 italic text-center">
                  No infrastructure cost records this month
                </td>
              </tr>
            ) : (
              lines.map((line, idx) => (
                <tr
                  key={`${line.category}-${idx}`}
                  data-testid={`infra-row-${line.category}-${idx}`}
                >
                  <td className="px-3 py-2 capitalize text-gray-700">{line.category}</td>
                  <td className="px-3 py-2 text-gray-800">{line.description}</td>
                  <td className="px-3 py-2 text-right text-gray-700">
                    ${line.cost_usd.toFixed(4)}
                  </td>
                </tr>
              ))
            )}
            <tr className="bg-gray-50 font-semibold">
              <td colSpan={2} className="px-3 py-2 text-gray-800">
                Infrastructure Total
              </td>
              <td className="px-3 py-2 text-right text-gray-800" data-testid="infra-total">
                ${total.toFixed(4)}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Main component ─────────────────────────────────────────────────────────────────

export function CostMonitorTab() {
  const { data: summary, isLoading, error } = useQuery<MonthlyBudgetSummary>({
    queryKey: COST_MONITOR_KEY,
    queryFn: fetchCostMonitor,
    staleTime: 5 * 60 * 1000,  // 5 minutes — cost data does not need real-time updates
  });

  if (isLoading) {
    return <div data-testid="cost-monitor-loading">Loading cost monitor...</div>;
  }

  if (error) {
    return (
      <div data-testid="cost-monitor-error" className="text-red-600">
        Failed to load cost monitor: {(error as Error).message}
      </div>
    );
  }

  if (!summary) {
    return null;
  }

  const monthLabel = formatBillingMonth(summary.billing_month);

  return (
    <div data-testid="cost-monitor-tab" className="space-y-6">
      {/* ── Header ── */}
      <div>
        <h2 className="text-lg font-semibold mb-1">Monthly Budget Monitor</h2>
        <p
          className="text-2xl font-bold text-gray-900"
          data-testid="combined-total-label"
        >
          {monthLabel} total: ${summary.combined_total_usd.toFixed(2)} /{' '}
          ${summary.budget_usd.toFixed(2)}
        </p>
      </div>

      {/* ── Progress bar ── */}
      <BudgetProgressBar pct={summary.pct_of_budget} />

      {/* ── Cost breakdown tables ── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <AiCostsTable lines={summary.ai_costs} total={summary.ai_total_usd} />
        <InfraCostsTable lines={summary.infra_costs} total={summary.infra_total_usd} />
      </div>

      {/* ── Admin reminder ── */}
      <div
        className="rounded border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800"
        data-testid="infra-reminder"
      >
        <strong>Reminder:</strong> Infrastructure costs must be entered manually into the{' '}
        <code className="font-mono">infrastructure_cost</code> table by the 5th of each
        month. Missing entries will cause the combined total to understate real spend.
      </div>
    </div>
  );
}

export default CostMonitorTab;
