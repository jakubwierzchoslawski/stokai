/**
 * MapContextSwitcher.test.tsx — Tests for MapContextSwitcher component.
 *
 * PLAN-F-019 TASK-009
 */

import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { MapContextSwitcher } from './MapContextSwitcher';

describe('MapContextSwitcher', () => {
  it('renders three mode buttons', () => {
    render(
      <MapContextSwitcher
        mode="global"
        sector={null}
        onSetMode={jest.fn()}
      />,
    );
    expect(screen.getByTestId('mode-button-global')).toBeTruthy();
    expect(screen.getByTestId('mode-button-portfolio')).toBeTruthy();
    expect(screen.getByTestId('mode-button-sector')).toBeTruthy();
  });

  it('active button has aria-pressed=true', () => {
    render(
      <MapContextSwitcher
        mode="portfolio"
        sector={null}
        onSetMode={jest.fn()}
      />,
    );
    const portfolioBtn = screen.getByTestId('mode-button-portfolio');
    expect(portfolioBtn.getAttribute('aria-pressed')).toBe('true');
    const globalBtn = screen.getByTestId('mode-button-global');
    expect(globalBtn.getAttribute('aria-pressed')).toBe('false');
  });

  it('clicking a mode button calls onSetMode with the correct mode', () => {
    const onSetMode = jest.fn();
    render(
      <MapContextSwitcher
        mode="global"
        sector={null}
        onSetMode={onSetMode}
      />,
    );
    fireEvent.click(screen.getByTestId('mode-button-portfolio'));
    expect(onSetMode).toHaveBeenCalledWith('portfolio');
  });

  it('sector select is not shown when mode is not sector', () => {
    render(
      <MapContextSwitcher
        mode="global"
        sector={null}
        onSetMode={jest.fn()}
      />,
    );
    expect(screen.queryByTestId('sector-select')).toBeNull();
  });

  it('sector select appears when mode is sector', () => {
    render(
      <MapContextSwitcher
        mode="sector"
        sector={null}
        onSetMode={jest.fn()}
        onSetSector={jest.fn()}
      />,
    );
    expect(screen.getByTestId('sector-select')).toBeTruthy();
  });

  it('changing sector select calls onSetSector with the selected value', () => {
    const onSetSector = jest.fn();
    render(
      <MapContextSwitcher
        mode="sector"
        sector={null}
        onSetMode={jest.fn()}
        onSetSector={onSetSector}
      />,
    );
    fireEvent.change(screen.getByTestId('sector-select'), {
      target: { value: 'Energy' },
    });
    expect(onSetSector).toHaveBeenCalledWith('Energy');
  });
});
