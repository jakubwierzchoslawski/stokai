/**
 * PriceChartPanel — OHLCV candlestick/line chart using Recharts ComposedChart.
 *
 * Renders close price line and volume bar chart for the selected interval.
 * Displays a placeholder when data is empty or loading.
 *
 * PLAN-F-023 TASK-005
 */
import React from 'react';
import {
  ComposedChart,
  Line,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts';
import type { PriceBar } from './types';

export interface PriceChartPanelProps {
  bars: PriceBar[];
  isLoading?: boolean;
}

function formatDate(ts: string): string {
  return new Date(ts).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

export function PriceChartPanel({ bars, isLoading = false }: PriceChartPanelProps): React.ReactElement {
  if (isLoading) {
    return (
      <div className="price-chart-panel price-chart-panel--loading" data-testid="price-chart-loading">
        <p>Loading price data...</p>
      </div>
    );
  }

  if (bars.length === 0) {
    return (
      <div className="price-chart-panel price-chart-panel--empty" data-testid="price-chart-empty">
        <p>No price data available.</p>
      </div>
    );
  }

  const chartData = bars.map((bar) => ({
    date: formatDate(bar.ts),
    close: bar.close,
    volume: bar.volume,
    open: bar.open,
    high: bar.high,
    low: bar.low,
  }));

  return (
    <div className="price-chart-panel" data-testid="price-chart-panel">
      <ResponsiveContainer width="100%" height={320}>
        <ComposedChart data={chartData} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="date" tick={{ fontSize: 11 }} />
          <YAxis yAxisId="price" orientation="left" tick={{ fontSize: 11 }} />
          <YAxis yAxisId="volume" orientation="right" tick={{ fontSize: 11 }} />
          <Tooltip />
          <Legend />
          <Bar yAxisId="volume" dataKey="volume" fill="#d1d5db" opacity={0.5} name="Volume" />
          <Line
            yAxisId="price"
            type="monotone"
            dataKey="close"
            stroke="#2563eb"
            dot={false}
            name="Close"
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
