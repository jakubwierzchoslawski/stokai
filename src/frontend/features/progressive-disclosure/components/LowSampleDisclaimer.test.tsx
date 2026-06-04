/**
 * LowSampleDisclaimer.test.tsx — Tests for LowSampleDisclaimer component.
 *
 * PLAN-F-020 TASK-007
 */

import React from 'react';
import { render, screen } from '@testing-library/react';

import { LowSampleDisclaimer } from './LowSampleDisclaimer';

describe('LowSampleDisclaimer', () => {
  it('renders the disclaimer text', () => {
    render(<LowSampleDisclaimer />);
    expect(screen.getByTestId('low-sample-disclaimer')).toBeInTheDocument();
    expect(screen.getByText(/Low sample/)).toBeInTheDocument();
    expect(screen.getByText(/fewer than 5 historical analogies/)).toBeInTheDocument();
  });

  it('has role=alert for accessibility', () => {
    render(<LowSampleDisclaimer />);
    expect(screen.getByRole('alert')).toBeInTheDocument();
  });
});
