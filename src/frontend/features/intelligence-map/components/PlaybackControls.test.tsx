/**
 * PlaybackControls.test.tsx — TDD tests for PlaybackControls.
 *
 * PLAN-F-021 TASK-008
 */

import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import PlaybackControls from './PlaybackControls';

describe('PlaybackControls', () => {
  it('isPlaying=false, isComplete=false → Play button present, Pause button absent', () => {
    render(
      <PlaybackControls
        isPlaying={false}
        isComplete={false}
        speed="1x"
        visibleCount={0}
        totalCount={10}
        onPlay={vi.fn()}
        onPause={vi.fn()}
        onReset={vi.fn()}
        onSetSpeed={vi.fn()}
      />,
    );
    expect(screen.getByTestId('playback-btn-play')).toBeInTheDocument();
    expect(screen.queryByTestId('playback-btn-pause')).not.toBeInTheDocument();
  });

  it('isPlaying=true → Pause button present, Play button absent', () => {
    render(
      <PlaybackControls
        isPlaying={true}
        isComplete={false}
        speed="1x"
        visibleCount={3}
        totalCount={10}
        onPlay={vi.fn()}
        onPause={vi.fn()}
        onReset={vi.fn()}
        onSetSpeed={vi.fn()}
      />,
    );
    expect(screen.getByTestId('playback-btn-pause')).toBeInTheDocument();
    expect(screen.queryByTestId('playback-btn-play')).not.toBeInTheDocument();
  });

  it('isComplete=true → Play button absent, Pause button absent, "Complete" label visible', () => {
    render(
      <PlaybackControls
        isPlaying={false}
        isComplete={true}
        speed="1x"
        visibleCount={10}
        totalCount={10}
        onPlay={vi.fn()}
        onPause={vi.fn()}
        onReset={vi.fn()}
        onSetSpeed={vi.fn()}
      />,
    );
    expect(screen.queryByTestId('playback-btn-play')).not.toBeInTheDocument();
    expect(screen.queryByTestId('playback-btn-pause')).not.toBeInTheDocument();
    expect(screen.getByTestId('playback-complete-label')).toBeInTheDocument();
  });

  it('clicking Play fires onPlay', () => {
    const onPlay = vi.fn();
    render(
      <PlaybackControls
        isPlaying={false}
        isComplete={false}
        speed="1x"
        visibleCount={0}
        totalCount={10}
        onPlay={onPlay}
        onPause={vi.fn()}
        onReset={vi.fn()}
        onSetSpeed={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByTestId('playback-btn-play'));
    expect(onPlay).toHaveBeenCalledTimes(1);
  });

  it('clicking Pause fires onPause', () => {
    const onPause = vi.fn();
    render(
      <PlaybackControls
        isPlaying={true}
        isComplete={false}
        speed="1x"
        visibleCount={2}
        totalCount={10}
        onPlay={vi.fn()}
        onPause={onPause}
        onReset={vi.fn()}
        onSetSpeed={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByTestId('playback-btn-pause'));
    expect(onPause).toHaveBeenCalledTimes(1);
  });

  it('clicking Reset fires onReset', () => {
    const onReset = vi.fn();
    render(
      <PlaybackControls
        isPlaying={false}
        isComplete={false}
        speed="1x"
        visibleCount={0}
        totalCount={10}
        onPlay={vi.fn()}
        onPause={vi.fn()}
        onReset={onReset}
        onSetSpeed={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByTestId('playback-btn-reset'));
    expect(onReset).toHaveBeenCalledTimes(1);
  });

  it('selecting "16x" from speed selector fires onSetSpeed("16x")', () => {
    const onSetSpeed = vi.fn();
    render(
      <PlaybackControls
        isPlaying={false}
        isComplete={false}
        speed="1x"
        visibleCount={0}
        totalCount={10}
        onPlay={vi.fn()}
        onPause={vi.fn()}
        onReset={vi.fn()}
        onSetSpeed={onSetSpeed}
      />,
    );
    const select = screen.getByTestId('playback-speed-select');
    fireEvent.change(select, { target: { value: '16x' } });
    expect(onSetSpeed).toHaveBeenCalledWith('16x');
  });

  it('visibleCount=3, totalCount=10 → progress bar aria-valuenow ~30', () => {
    render(
      <PlaybackControls
        isPlaying={true}
        isComplete={false}
        speed="1x"
        visibleCount={3}
        totalCount={10}
        onPlay={vi.fn()}
        onPause={vi.fn()}
        onReset={vi.fn()}
        onSetSpeed={vi.fn()}
      />,
    );
    const progressBar = screen.getByTestId('playback-progress');
    const valuenow = progressBar.getAttribute('aria-valuenow');
    expect(Number(valuenow)).toBeCloseTo(30, 0);
  });

  it('Reset button is always visible regardless of play state', () => {
    const { rerender } = render(
      <PlaybackControls
        isPlaying={true}
        isComplete={false}
        speed="4x"
        visibleCount={5}
        totalCount={10}
        onPlay={vi.fn()}
        onPause={vi.fn()}
        onReset={vi.fn()}
        onSetSpeed={vi.fn()}
      />,
    );
    expect(screen.getByTestId('playback-btn-reset')).toBeInTheDocument();
    rerender(
      <PlaybackControls
        isPlaying={false}
        isComplete={true}
        speed="4x"
        visibleCount={10}
        totalCount={10}
        onPlay={vi.fn()}
        onPause={vi.fn()}
        onReset={vi.fn()}
        onSetSpeed={vi.fn()}
      />,
    );
    expect(screen.getByTestId('playback-btn-reset')).toBeInTheDocument();
  });
});
