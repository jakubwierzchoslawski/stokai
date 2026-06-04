/**
 * SidePanelSparkline.tsx — T±7d close-price sparkline for one ticker.
 *
 * PLAN-F-020 TASK-008
 *
 * Uses Recharts LineChart in sparkline style (no axes).
 * Final-point dot is green if last.close >= first.close, red otherwise.
 * Width: 160px, Height: 48px (compact sparkline).
 *
 * AC-002
 */

import React, { useMemo } from 'react';
import {
  LineChart,
  Line,
  Tooltip,
  ReferenceDot,
  ResponsiveContainer,
} from 'recharts';

import type { SparklinePoint } from '../types/disclosure.types';

export interface SidePanelSparklineProps {
  ticker: string;
  ohlcv_7d: SparklinePoint[];
}

export function SidePanelSparkline({ ticker, ohlcv_7d }: SidePanelSparklineProps) {
  const isPositive = useMemo(() => {
    if (ohlcv_7d.length === 0) return true;
    return ohlcv_7d[ohlcv_7d.length - 1].close >= ohlcv_7d[0].close;
  }, [ohlcv_7d]);

  const dotColor = isPositive ? '#16a34a' : '#dc2626';
  const lineColor = isPositive ? '#16a34a' : '#dc2626';

  if (ohlcv_7d.length === 0) {
    return (
      <div
        data-testid={`sparkline-${ticker}`}
        style={{
          width: '160px',
          height: '48px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: '11px',
          color: '#9ca3af',
          border: '1px dashed #e5e7eb',
          borderRadius: '4px',
        }}
      >
        No price data
      </div>
    );
  }

  const lastPoint = ohlcv_7d[ohlcv_7d.length - 1];

  return (
    <div
      data-testid={`sparkline-${ticker}`}
      style={{ width: '160px' }}
      role="img"
      aria-label={`${ticker} price sparkline`}
    >
      <div style={{ fontSize: '11px', fontWeight: 600, color: '#374151', marginBottom: '2px' }}>
        {ticker}
      </div>
      <ResponsiveContainer width={160} height={48}>
        <LineChart data={ohlcv_7d} margin={{ top: 4, right: 4, bottom: 4, left: 4 }}>
          <Line
            type="monotone"
            dataKey="close"
            stroke={lineColor}
            strokeWidth={1.5}
            dot={false}
            isAnimationActive={false}
          />
          <ReferenceDot
            x={lastPoint.ts}
            y={lastPoint.close}
            r={3}
            fill={dotColor}
            stroke="none"
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export default SidePanelSparkline;
