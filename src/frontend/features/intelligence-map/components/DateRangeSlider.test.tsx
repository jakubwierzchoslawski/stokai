/**
 * DateRangeSlider.test.tsx — TDD tests for DateRangeSlider.
 *
 * PLAN-F-021 TASK-007
 */

import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import DateRangeSlider from './DateRangeSlider';

describe('DateRangeSlider', () => {
  it('with from_date > to_date → Load button disabled and error message visible', () => {
    const onSetRange = vi.fn();
    render(
      <DateRangeSlider
        from_date="2025-01-31"
        to_date="2025-01-01"
        onSetRange={onSetRange}
      />,
    );
    const loadBtn = screen.getByTestId('date-range-load');
    expect(loadBtn).toBeDisabled();
    expect(screen.getByTestId('date-range-error')).toBeInTheDocument();
  });

  it('with valid range → Load button enabled; clicking it calls onSetRange', () => {
    const onSetRange = vi.fn();
    render(
      <DateRangeSlider
        from_date="2025-01-01"
        to_date="2025-01-31"
        onSetRange={onSetRange}
      />,
    );
    const loadBtn = screen.getByTestId('date-range-load');
    expect(loadBtn).not.toBeDisabled();
    fireEvent.click(loadBtn);
    expect(onSetRange).toHaveBeenCalledWith({
      from_date: '2025-01-01',
      to_date: '2025-01-31',
    });
  });

  it('with range > 365 days → Load button disabled with "range exceeds 1 year" message', () => {
    const onSetRange = vi.fn();
    render(
      <DateRangeSlider
        from_date="2024-01-01"
        to_date="2025-12-31"
        onSetRange={onSetRange}
      />,
    );
    const loadBtn = screen.getByTestId('date-range-load');
    expect(loadBtn).toBeDisabled();
    const error = screen.getByTestId('date-range-error');
    expect(error.textContent?.toLowerCase()).toContain('1 year');
  });

  it('allows user to type a new from_date and then load', () => {
    const onSetRange = vi.fn();
    render(
      <DateRangeSlider
        from_date="2025-01-01"
        to_date="2025-01-31"
        onSetRange={onSetRange}
      />,
    );
    const fromInput = screen.getByTestId('date-range-from');
    fireEvent.change(fromInput, { target: { value: '2025-01-05' } });
    const loadBtn = screen.getByTestId('date-range-load');
    expect(loadBtn).not.toBeDisabled();
    fireEvent.click(loadBtn);
    expect(onSetRange).toHaveBeenCalledWith({
      from_date: '2025-01-05',
      to_date: '2025-01-31',
    });
  });

  it('from_date equal to to_date → Load button disabled', () => {
    const onSetRange = vi.fn();
    render(
      <DateRangeSlider
        from_date="2025-01-15"
        to_date="2025-01-15"
        onSetRange={onSetRange}
      />,
    );
    expect(screen.getByTestId('date-range-load')).toBeDisabled();
  });
});
