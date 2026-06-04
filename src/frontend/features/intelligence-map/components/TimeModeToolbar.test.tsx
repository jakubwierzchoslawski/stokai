/**
 * TimeModeToolbar.test.tsx — TDD tests for TimeModeToolbar.
 *
 * PLAN-F-021 TASK-007
 */

import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import TimeModeToolbar from './TimeModeToolbar';

describe('TimeModeToolbar', () => {
  it('renders three toggle buttons (Live, Historical, Playback)', () => {
    render(
      <TimeModeToolbar
        timeMode="live"
        dateRange={null}
        onSetTimeMode={vi.fn()}
        onSetDateRange={vi.fn()}
      />,
    );
    expect(screen.getByTestId('time-mode-btn-live')).toBeInTheDocument();
    expect(screen.getByTestId('time-mode-btn-historical')).toBeInTheDocument();
    expect(screen.getByTestId('time-mode-btn-playback')).toBeInTheDocument();
  });

  it('clicking "Historical" calls onSetTimeMode("historical")', () => {
    const onSetTimeMode = vi.fn();
    render(
      <TimeModeToolbar
        timeMode="live"
        dateRange={null}
        onSetTimeMode={onSetTimeMode}
        onSetDateRange={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByTestId('time-mode-btn-historical'));
    expect(onSetTimeMode).toHaveBeenCalledWith('historical');
  });

  it('clicking "Playback" calls onSetTimeMode("playback")', () => {
    const onSetTimeMode = vi.fn();
    render(
      <TimeModeToolbar
        timeMode="live"
        dateRange={null}
        onSetTimeMode={onSetTimeMode}
        onSetDateRange={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByTestId('time-mode-btn-playback'));
    expect(onSetTimeMode).toHaveBeenCalledWith('playback');
  });

  it('timeMode="live" → DateRangeSlider not present in the DOM', () => {
    render(
      <TimeModeToolbar
        timeMode="live"
        dateRange={null}
        onSetTimeMode={vi.fn()}
        onSetDateRange={vi.fn()}
      />,
    );
    expect(screen.queryByTestId('date-range-slider')).not.toBeInTheDocument();
  });

  it('timeMode="historical" → DateRangeSlider is present in the DOM', () => {
    render(
      <TimeModeToolbar
        timeMode="historical"
        dateRange={null}
        onSetTimeMode={vi.fn()}
        onSetDateRange={vi.fn()}
      />,
    );
    expect(screen.getByTestId('date-range-slider')).toBeInTheDocument();
  });

  it('timeMode="playback" → DateRangeSlider is present in the DOM', () => {
    render(
      <TimeModeToolbar
        timeMode="playback"
        dateRange={null}
        onSetTimeMode={vi.fn()}
        onSetDateRange={vi.fn()}
      />,
    );
    expect(screen.getByTestId('date-range-slider')).toBeInTheDocument();
  });

  it('active mode button has aria-pressed="true"', () => {
    render(
      <TimeModeToolbar
        timeMode="historical"
        dateRange={null}
        onSetTimeMode={vi.fn()}
        onSetDateRange={vi.fn()}
      />,
    );
    expect(screen.getByTestId('time-mode-btn-historical')).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByTestId('time-mode-btn-live')).toHaveAttribute('aria-pressed', 'false');
  });
});
