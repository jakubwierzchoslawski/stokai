import { describe, it, expect } from 'vitest';
/**
 * ContrarianCallout.test.tsx â€” Tests for ContrarianCallout component.
 *
 * PLAN-F-020 TASK-007
 */

import React from 'react';
import { render, screen } from '@testing-library/react';

import { ContrarianCallout } from './ContrarianCallout';

describe('ContrarianCallout', () => {
  it('renders the passed text', () => {
    render(<ContrarianCallout text="History shows commodity spikes." />);
    expect(screen.getByTestId('contrarian-callout')).toBeInTheDocument();
    expect(screen.getByText('History shows commodity spikes.')).toBeInTheDocument();
  });

  it('shows "History says" label', () => {
    render(<ContrarianCallout text="Some callout" />);
    expect(screen.getByText(/History says/i)).toBeInTheDocument();
  });

  it('has role=note for accessibility', () => {
    render(<ContrarianCallout text="Some callout" />);
    expect(screen.getByRole('note')).toBeInTheDocument();
  });

  it('is visually distinct from low-sample disclaimer (blue border, not amber)', () => {
    const { container } = render(<ContrarianCallout text="Callout" />);
    const element = container.firstChild as HTMLElement;
    // Verify blue left-border via inline style
    expect(element.style.borderLeft).toContain('#2563eb');
  });
});
