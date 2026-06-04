/**
 * EmptyState.test.tsx — TDD tests for EmptyState component.
 *
 * PLAN-F-019 TASK-010
 */

import React from 'react';
import { render, screen } from '@testing-library/react';
import { EmptyState } from './EmptyState';

describe('EmptyState', () => {
  it('renders the provided message text', () => {
    const msg = 'No events to display right now. Markets are quiet.';
    render(<EmptyState message={msg} />);
    expect(screen.getByText(msg)).toBeTruthy();
  });

  it('renders data-testid="empty-state"', () => {
    render(<EmptyState message="test" />);
    expect(screen.getByTestId('empty-state')).toBeTruthy();
  });

  it('renders data-testid="empty-state-message" containing the message', () => {
    const msg = 'Quiet session. No events near your holdings right now.';
    render(<EmptyState message={msg} />);
    const el = screen.getByTestId('empty-state-message');
    expect(el.textContent).toBe(msg);
  });

  it('has role="status" for accessibility', () => {
    render(<EmptyState message="test" />);
    expect(screen.getByRole('status')).toBeTruthy();
  });

  it('different messages render correctly', () => {
    const { rerender } = render(<EmptyState message="first message" />);
    expect(screen.getByText('first message')).toBeTruthy();
    rerender(<EmptyState message="second message" />);
    expect(screen.getByText('second message')).toBeTruthy();
    expect(screen.queryByText('first message')).toBeNull();
  });
});
