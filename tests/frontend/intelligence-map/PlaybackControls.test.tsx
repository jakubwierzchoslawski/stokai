import { describe, it, expect, vi } from 'vitest';
/**
 * PlaybackControls.test.tsx â€” TDD tests for PlaybackControls.
 *
 * PLAN-F-021 TASK-008
 */

import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import PlaybackControls from '../../../src/frontend/features/intelligence-map/components/PlaybackControls';

describe('PlaybackControls', () => {
  it('isPlaying=false, isComplete=false â†’ Play present, Pause absent', () => {
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
    expect(screen.getByTestId('playback-btn-play')).toBeTruthy();
    expect(screen.queryByTestId('playback-btn-pause')).toBeNull();
  });

  it('isPlaying=true â†’ Pause present, Play absent', () => {
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
    expect(screen.getByTestId('playback-btn-pause')).toBeTruthy();
    expect(screen.queryByTestId('playback-btn-play')).toBeNull();
  });

  it('isComplete=true â†’ no Play or Pause; "Complete" label visible', () => {
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
    expect(screen.queryByTestId('playback-btn-play')).toBeNull();
    expect(screen.queryByTestId('playback-btn-pause')).toBeNull();
    expect(screen.getByTestId('playback-complete-label')).toBeTruthy();
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

  it('selecting "16x" fires onSetSpeed("16x")', () => {
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
    fireEvent.change(screen.getByTestId('playback-speed-select'), { target: { value: '16x' } });
    expect(onSetSpeed).toHaveBeenCalledWith('16x');
  });

  it('visibleCount=3, totalCount=10 â†’ progress bar aria-valuenow ~30', () => {
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
    const valuenow = Number(progressBar.getAttribute('aria-valuenow'));
    expect(Math.abs(valuenow - 30)).toBeLessThanOrEqual(1);
  });

  it('Reset button always visible', () => {
    render(
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
    expect(screen.getByTestId('playback-btn-reset')).toBeTruthy();
  });
});
