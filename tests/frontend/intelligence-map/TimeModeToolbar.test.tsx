/**
 * TimeModeToolbar.test.tsx — TDD tests for TimeModeToolbar + DateRangeSlider.
 *
 * PLAN-F-021 TASK-007
 */

import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import TimeModeToolbar from '../../../src/frontend/features/intelligence-map/components/TimeModeToolbar';
import DateRangeSlider from '../../../src/frontend/features/intelligence-map/components/DateRangeSlider';

describe('TimeModeToolbar', () => {
  it('renders three toggle buttons (Live, Historical, Playback)', () => {
    render(
      <TimeModeToolbar
        timeMode="live"
        dateRange={null}
        onSetTimeMode={jest.fn()}
        onSetDateRange={jest.fn()}
      />,
    );
    expect(screen.getByTestId('time-mode-btn-live')).toBeTruthy();
    expect(screen.getByTestId('time-mode-btn-historical')).toBeTruthy();
    expect(screen.getByTestId('time-mode-btn-playback')).toBeTruthy();
  });

  it('clicking "Historical" calls onSetTimeMode("historical")', () => {
    const onSetTimeMode = jest.fn();
    render(
      <TimeModeToolbar
        timeMode="live"
        dateRange={null}
        onSetTimeMode={onSetTimeMode}
        onSetDateRange={jest.fn()}
      />,
    );
    fireEvent.click(screen.getByTestId('time-mode-btn-historical'));
    expect(onSetTimeMode).toHaveBeenCalledWith('historical');
  });

  it('timeMode="live" → DateRangeSlider not present in the DOM', () => {
    render(
      <TimeModeToolbar
        timeMode="live"
        dateRange={null}
        onSetTimeMode={jest.fn()}
        onSetDateRange={jest.fn()}
      />,
    );
    expect(screen.queryByTestId('date-range-slider')).toBeNull();
  });

  it('timeMode="historical" → DateRangeSlider is present in the DOM', () => {
    render(
      <TimeModeToolbar
        timeMode="historical"
        dateRange={null}
        onSetTimeMode={jest.fn()}
        onSetDateRange={jest.fn()}
      />,
    );
    expect(screen.getByTestId('date-range-slider')).toBeTruthy();
  });

  it('active mode button has aria-pressed="true"', () => {
    render(
      <TimeModeToolbar
        timeMode="historical"
        dateRange={null}
        onSetTimeMode={jest.fn()}
        onSetDateRange={jest.fn()}
      />,
    );
    expect(screen.getByTestId('time-mode-btn-historical').getAttribute('aria-pressed')).toBe('true');
    expect(screen.getByTestId('time-mode-btn-live').getAttribute('aria-pressed')).toBe('false');
  });
});

describe('DateRangeSlider', () => {
  it('with from_date > to_date → Load button disabled and error visible', () => {
    const onSetRange = jest.fn();
    render(
      <DateRangeSlider
        from_date="2025-01-31"
        to_date="2025-01-01"
        onSetRange={onSetRange}
      />,
    );
    expect(screen.getByTestId('date-range-load')).toBeDisabled();
    expect(screen.getByTestId('date-range-error')).toBeTruthy();
  });

  it('with valid range → Load enabled; clicking calls onSetRange', () => {
    const onSetRange = jest.fn();
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
    expect(onSetRange).toHaveBeenCalledWith({ from_date: '2025-01-01', to_date: '2025-01-31' });
  });

  it('with range > 365 days → Load disabled with "1 year" message', () => {
    render(
      <DateRangeSlider
        from_date="2024-01-01"
        to_date="2025-12-31"
        onSetRange={jest.fn()}
      />,
    );
    expect(screen.getByTestId('date-range-load')).toBeDisabled();
    expect(screen.getByTestId('date-range-error').textContent!.toLowerCase()).toContain('1 year');
  });
});
