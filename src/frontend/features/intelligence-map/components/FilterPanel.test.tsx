/**
 * FilterPanel.test.tsx — TDD tests for FilterPanel component.
 *
 * PLAN-F-019 TASK-007
 */

import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { FilterPanel } from './FilterPanel';
import { INITIAL_FILTERS } from '../hooks/useMapFilters';
import { KNOWN_CATEGORIES } from '../lib/cluster-properties';

describe('FilterPanel', () => {
  it('renders a checkbox for every known category', () => {
    const toggleCat = jest.fn();
    const toggleInt = jest.fn();
    render(
      <FilterPanel
        filters={INITIAL_FILTERS}
        onToggleCategory={toggleCat}
        onToggleIntensity={toggleInt}
      />,
    );
    for (const cat of KNOWN_CATEGORIES) {
      expect(screen.getByTestId(`checkbox-category-${cat}`)).toBeTruthy();
    }
  });

  it('renders checkboxes for all 5 intensity levels', () => {
    render(
      <FilterPanel
        filters={INITIAL_FILTERS}
        onToggleCategory={jest.fn()}
        onToggleIntensity={jest.fn()}
      />,
    );
    for (let i = 1; i <= 5; i++) {
      expect(screen.getByTestId(`checkbox-intensity-${i}`)).toBeTruthy();
    }
  });

  it('calls onToggleCategory with the correct category string when checkbox is clicked', () => {
    const toggleCat = jest.fn();
    render(
      <FilterPanel
        filters={INITIAL_FILTERS}
        onToggleCategory={toggleCat}
        onToggleIntensity={jest.fn()}
      />,
    );
    fireEvent.click(screen.getByTestId('checkbox-category-CONFLICT'));
    expect(toggleCat).toHaveBeenCalledTimes(1);
    expect(toggleCat).toHaveBeenCalledWith('CONFLICT');
  });

  it('calls onToggleIntensity with the correct level when intensity checkbox is clicked', () => {
    const toggleInt = jest.fn();
    render(
      <FilterPanel
        filters={INITIAL_FILTERS}
        onToggleCategory={jest.fn()}
        onToggleIntensity={toggleInt}
      />,
    );
    fireEvent.click(screen.getByTestId('checkbox-intensity-3'));
    expect(toggleInt).toHaveBeenCalledTimes(1);
    expect(toggleInt).toHaveBeenCalledWith(3);
  });

  it('inactive category checkbox is unchecked', () => {
    const filters = { ...INITIAL_FILTERS, categories: ['ECONOMIC'] };
    render(
      <FilterPanel
        filters={filters}
        onToggleCategory={jest.fn()}
        onToggleIntensity={jest.fn()}
      />,
    );
    const conflictCheckbox = screen.getByTestId('checkbox-category-CONFLICT') as HTMLInputElement;
    expect(conflictCheckbox.checked).toBe(false);
  });

  it('active category checkbox is checked', () => {
    render(
      <FilterPanel
        filters={INITIAL_FILTERS}
        onToggleCategory={jest.fn()}
        onToggleIntensity={jest.fn()}
      />,
    );
    const conflictCheckbox = screen.getByTestId('checkbox-category-CONFLICT') as HTMLInputElement;
    expect(conflictCheckbox.checked).toBe(true);
  });
});
