/**
 * ClusterDonut.tsx — SVG donut chart showing category proportions for a cluster.
 *
 * Renders a D3-arc pie chart. Has no MapLibre dependency; pure SVG.
 *
 * PLAN-F-019 TASK-005
 */

import React, { useMemo } from 'react';

// ── Props ─────────────────────────────────────────────────────────────────────

export interface ClusterDonutProps {
  categories: Record<string, number>;
  colors: Record<string, string>;
  /** Outer radius in px. Default 40. */
  outerRadius?: number;
  /** Inner radius in px. Default 20 (donut hole). */
  innerRadius?: number;
}

// ── Minimal D3-style arc computation (no d3 import required here) ─────────────

interface ArcSlice {
  category: string;
  count: number;
  startAngle: number;
  endAngle: number;
  color: string;
}

function computeArcs(
  categories: Record<string, number>,
  colors: Record<string, string>,
): ArcSlice[] {
  const entries = Object.entries(categories).filter(([, v]) => v > 0);
  const total = entries.reduce((s, [, v]) => s + v, 0);
  if (total === 0) return [];

  let cursor = 0;
  return entries.map(([cat, count]) => {
    const fraction = count / total;
    const startAngle = cursor;
    cursor += fraction * 2 * Math.PI;
    return {
      category: cat,
      count,
      startAngle,
      endAngle: cursor,
      color: colors[cat] ?? '#CC79A7',
    };
  });
}

function arcPathD(
  startAngle: number,
  endAngle: number,
  outerR: number,
  innerR: number,
): string {
  const cos = Math.cos;
  const sin = Math.sin;
  // Adjust so 0 is top (subtract PI/2).
  const sa = startAngle - Math.PI / 2;
  const ea = endAngle - Math.PI / 2;

  const x1 = outerR * cos(sa);
  const y1 = outerR * sin(sa);
  const x2 = outerR * cos(ea);
  const y2 = outerR * sin(ea);
  const ix1 = innerR * cos(ea);
  const iy1 = innerR * sin(ea);
  const ix2 = innerR * cos(sa);
  const iy2 = innerR * sin(sa);

  const largeArc = endAngle - startAngle > Math.PI ? 1 : 0;

  return [
    `M ${x1} ${y1}`,
    `A ${outerR} ${outerR} 0 ${largeArc} 1 ${x2} ${y2}`,
    `L ${ix1} ${iy1}`,
    `A ${innerR} ${innerR} 0 ${largeArc} 0 ${ix2} ${iy2}`,
    'Z',
  ].join(' ');
}

// ── Component ─────────────────────────────────────────────────────────────────

export const ClusterDonut: React.FC<ClusterDonutProps> = ({
  categories,
  colors,
  outerRadius = 40,
  innerRadius = 20,
}) => {
  const arcs = useMemo(
    () => computeArcs(categories, colors),
    [categories, colors],
  );

  const size = outerRadius * 2 + 4;

  return (
    <svg
      width={size}
      height={size}
      viewBox={`${-outerRadius - 2} ${-outerRadius - 2} ${size} ${size}`}
      data-testid="cluster-donut"
    >
      {arcs.map((arc) => (
        <path
          key={arc.category}
          d={arcPathD(arc.startAngle, arc.endAngle, outerRadius, innerRadius)}
          fill={arc.color}
          aria-label={`${arc.category}: ${arc.count}`}
          data-testid={`arc-${arc.category}`}
          data-start={arc.startAngle}
          data-end={arc.endAngle}
        />
      ))}
    </svg>
  );
};

export default ClusterDonut;
