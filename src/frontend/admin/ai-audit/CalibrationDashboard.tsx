/**
 * CalibrationDashboard — Tier 3 calibration dashboard.
 *
 * Elements:
 *   1. Warning banner when below_threshold=true
 *   2. CORR time-series chart (Recharts)
 *   3. Per-signal accuracy table
 *   4. Lookback selector (30, 60, 90 days)
 *
 * PLAN-F-029 TASK-010
 */
import React, { useState } from 'react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ReferenceLine,
} from 'recharts';
import { useCalibration } from './hooks/useCalibration';

const LOOKBACK_OPTIONS = [30, 60, 90] as const;
type LookbackDays = (typeof LOOKBACK_OPTIONS)[number];

const SIGNAL_COLORS: Record<string, string> = {
  HOLD: '#6366f1',
  BUY_OPP: '#22c55e',
  AVOID: '#ef4444',
  WATCH: '#f59e0b',
};

function getColor(signal: string, index: number): string {
  return SIGNAL_COLORS[signal] ?? `hsl(${(index * 60) % 360}, 70%, 50%)`;
}

export function CalibrationDashboard() {
  const [days, setDays] = useState<LookbackDays>(30);

  const { timeSeries, summary, isLoading, isError } = useCalibration(days);

  // Build chart data: group by date, one key per action_signal
  const signalSet = Array.from(new Set(timeSeries.map((r) => r.action_signal)));
  const dateMap: Record<string, Record<string, number>> = {};
  for (const row of timeSeries) {
    const dateKey = row.computed_at.slice(0, 10);
    if (!dateMap[dateKey]) dateMap[dateKey] = {};
    dateMap[dateKey][row.action_signal] = row.corr_confidence_actual;
  }
  const chartData = Object.entries(dateMap)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([date, signals]) => ({ date, ...signals }));

  return (
    <div className="space-y-6" data-testid="calibration-dashboard">
      {/* Lookback selector */}
      <div className="flex items-center gap-2">
        <span className="text-sm font-medium text-gray-700">Lookback:</span>
        {LOOKBACK_OPTIONS.map((d) => (
          <button
            key={d}
            onClick={() => setDays(d)}
            className={`px-3 py-1 text-sm rounded ${
              days === d
                ? 'bg-blue-600 text-white'
                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            }`}
            data-testid={`lookback-${d}`}
          >
            {d} days
          </button>
        ))}
      </div>

      {/* Warning banner */}
      {summary?.below_threshold && (
        <div
          className="bg-amber-100 border border-amber-400 rounded p-4"
          data-testid="below-threshold-banner"
          role="alert"
        >
          <p className="font-bold text-amber-900">
            Warning: CORR(confidence, actual_t1d &times; direction_sign) has dropped below the
            threshold ({summary.threshold}). Review and trigger improvement loop.
          </p>
        </div>
      )}

      {isLoading && <p className="text-gray-500 text-sm">Loading calibration data...</p>}
      {isError && <p className="text-red-600 text-sm">Failed to load calibration data.</p>}

      {/* CORR time-series chart */}
      {chartData.length > 0 && (
        <div data-testid="calibration-chart">
          <h3 className="text-sm font-medium text-gray-700 mb-2">
            CORR(confidence, actual_t1d &times; direction_sign) — {days}-day window
          </h3>
          <LineChart
            width={700}
            height={300}
            data={chartData}
            margin={{ top: 10, right: 20, bottom: 0, left: 0 }}
          >
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="date" tick={{ fontSize: 11 }} />
            <YAxis domain={[-1, 1]} tick={{ fontSize: 11 }} />
            <Tooltip />
            <Legend />
            <ReferenceLine
              y={0.3}
              stroke="#f59e0b"
              strokeDasharray="4 2"
              label={{ value: 'Threshold 0.3', position: 'right', fontSize: 10 }}
            />
            {signalSet.map((signal, i) => (
              <Line
                key={signal}
                type="monotone"
                dataKey={signal}
                stroke={getColor(signal, i)}
                dot={false}
                name={signal}
              />
            ))}
          </LineChart>
        </div>
      )}

      {/* Per-signal accuracy table */}
      {summary && summary.per_signal_accuracy.length > 0 && (
        <div data-testid="per-signal-table">
          <h3 className="text-sm font-medium text-gray-700 mb-2">Per-signal accuracy</h3>
          <table className="min-w-full divide-y divide-gray-200 text-sm">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                  Signal
                </th>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                  Direction correct %
                </th>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                  Mean confidence
                </th>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                  Total recs
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {summary.per_signal_accuracy.map((row) => (
                <tr key={row.action_signal} data-testid={`signal-row-${row.action_signal}`}>
                  <td className="px-4 py-2 font-medium">{row.action_signal}</td>
                  <td className="px-4 py-2">
                    {(row.direction_correct_pct * 100).toFixed(1)}%
                  </td>
                  <td className="px-4 py-2">{row.mean_confidence.toFixed(3)}</td>
                  <td className="px-4 py-2">{row.total_recommendations}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
