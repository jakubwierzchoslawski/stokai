/**
 * hooks/useCalibration — parallel TanStack Query hooks for calibration dashboard.
 *
 * Fetches both time-series and summary in parallel.
 *
 * PLAN-F-029 TASK-010
 */
import { useQueries } from '@tanstack/react-query';

export interface CalibrationResult {
  result_id: string;
  action_signal: string;
  window_days: number;
  corr_confidence_actual: number;
  direction_correct_pct: number;
  mean_confidence: number;
  total_recommendations: number;
  computed_at: string;
  below_threshold: boolean;
}

export interface PerSignalAccuracy {
  action_signal: string;
  direction_correct_pct: number;
  mean_confidence: number;
  total_recommendations: number;
}

export interface CalibrationSummary {
  window_days: number;
  below_threshold: boolean;
  threshold: number;
  per_signal_accuracy: PerSignalAccuracy[];
  computed_at: string;
}

async function fetchCalibrationTimeSeries(
  days: number,
  actionSignal?: string
): Promise<CalibrationResult[]> {
  const params = new URLSearchParams({ days: String(days) });
  if (actionSignal) params.set('action_signal', actionSignal);
  const res = await fetch(`/api/v1/admin/audit/calibration?${params.toString()}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const json = await res.json();
  return json.data;
}

async function fetchCalibrationSummary(days: number): Promise<CalibrationSummary> {
  const res = await fetch(`/api/v1/admin/audit/calibration/summary?days=${days}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const json = await res.json();
  return json.data;
}

export function useCalibration(days: number, actionSignal?: string) {
  const results = useQueries({
    queries: [
      {
        queryKey: ['admin', 'audit', 'calibration', 'series', days, actionSignal] as const,
        queryFn: () => fetchCalibrationTimeSeries(days, actionSignal),
      },
      {
        queryKey: ['admin', 'audit', 'calibration', 'summary', days] as const,
        queryFn: () => fetchCalibrationSummary(days),
      },
    ],
  });

  return {
    timeSeries: results[0].data ?? [],
    summary: results[1].data ?? null,
    isLoading: results.some((r) => r.isLoading),
    isError: results.some((r) => r.isError),
  };
}
