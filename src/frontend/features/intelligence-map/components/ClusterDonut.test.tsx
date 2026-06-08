import { describe, it, expect } from 'vitest';
/**
 * ClusterDonut.test.tsx â€” TDD tests for the ClusterDonut component.
 *
 * PLAN-F-019 TASK-005
 */

import React from 'react';
import { render, screen } from '@testing-library/react';
import { ClusterDonut } from './ClusterDonut';
import { CATEGORY_COLORS } from '../lib/color-palette';

describe('ClusterDonut', () => {
  it('renders 2 arc path elements for 2 categories', () => {
    render(
      <ClusterDonut
        categories={{ CONFLICT: 3, ECONOMIC: 1 }}
        colors={CATEGORY_COLORS}
      />,
    );
    expect(screen.getByTestId('arc-CONFLICT')).toBeTruthy();
    expect(screen.getByTestId('arc-ECONOMIC')).toBeTruthy();
  });

  it('arc aria-labels reflect category and count', () => {
    render(
      <ClusterDonut
        categories={{ CONFLICT: 3, ECONOMIC: 1 }}
        colors={CATEGORY_COLORS}
      />,
    );
    expect(screen.getByLabelText('CONFLICT: 3')).toBeTruthy();
    expect(screen.getByLabelText('ECONOMIC: 1')).toBeTruthy();
  });

  it('CONFLICT arc has proportionally larger angle span than ECONOMIC (3:1 ratio)', () => {
    render(
      <ClusterDonut
        categories={{ CONFLICT: 3, ECONOMIC: 1 }}
        colors={CATEGORY_COLORS}
      />,
    );
    const conflictArc = screen.getByTestId('arc-CONFLICT');
    const economicArc = screen.getByTestId('arc-ECONOMIC');

    const conflictSpan =
      parseFloat(conflictArc.getAttribute('data-end') ?? '0') -
      parseFloat(conflictArc.getAttribute('data-start') ?? '0');
    const economicSpan =
      parseFloat(economicArc.getAttribute('data-end') ?? '0') -
      parseFloat(economicArc.getAttribute('data-start') ?? '0');

    expect(conflictSpan / economicSpan).toBeCloseTo(3, 1);
  });

  it('renders nothing (no arcs) when all category counts are 0', () => {
    render(
      <ClusterDonut
        categories={{ CONFLICT: 0, ECONOMIC: 0 }}
        colors={CATEGORY_COLORS}
      />,
    );
    expect(screen.queryByTestId('arc-CONFLICT')).toBeNull();
    expect(screen.queryByTestId('arc-ECONOMIC')).toBeNull();
  });

  it('renders the svg container', () => {
    render(
      <ClusterDonut categories={{ CONFLICT: 1 }} colors={CATEGORY_COLORS} />,
    );
    expect(screen.getByTestId('cluster-donut')).toBeTruthy();
  });
});
