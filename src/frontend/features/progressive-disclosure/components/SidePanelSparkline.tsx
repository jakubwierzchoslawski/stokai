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
    return ohlcv_7d[ohlcv_7d.length - 1]!.close >= ohlcv_7d[0]!.close;
  }, [ohlcv_7d]);

  const dotColor = isPositive ? 'var(--positive)' : 'var(--negative)';
  const lineColor = isPositive ? 'var(--positive)' : 'var(--negative)';

  if (ohlcv_7d.length === 0) {
    return (
      <div
        data-testid={`sparkline-${ticker}`}
        className="flex h-12 w-[160px] items-center justify-center rounded border border-dashed border-border text-[11px] text-muted"
      >
        No price data
      </div>
    );
  }

  const lastPoint = ohlcv_7d[ohlcv_7d.length - 1]!;

  return (
    <div
      data-testid={`sparkline-${ticker}`}
      className="w-[160px]"
      role="img"
      aria-label={`${ticker} price sparkline`}
    >
      <div className="mb-0.5 text-[11px] font-semibold text-text">{ticker}</div>
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
