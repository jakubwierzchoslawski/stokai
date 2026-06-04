/**
 * Tests for ActiveEventsPanel component.
 *
 * Tests:
 * - Clicking an event navigates to /?eventId={event_id}
 * - Shows empty state when no events
 * - Renders event titles
 *
 * PLAN-F-023 TASK-005
 */
import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { ActiveEventsPanel } from '../../../src/frontend/pages/CompanyDetail/ActiveEventsPanel';
import type { ActiveEventSummary } from '../../../src/frontend/pages/CompanyDetail/types';

function makeEvent(id: string, overrides: Partial<ActiveEventSummary> = {}): ActiveEventSummary {
  return {
    event_id: id,
    title: `Event ${id}`,
    occurred_at: '2024-02-01T00:00:00Z',
    intensity: 5,
    category: ['trade'],
    exposure_magnitude: 0.6,
    ...overrides,
  };
}

describe('ActiveEventsPanel', () => {
  it('shows empty state when no events', () => {
    render(<ActiveEventsPanel events={[]} />);
    expect(screen.getByTestId('active-events-empty')).toBeInTheDocument();
  });

  it('renders event titles', () => {
    const events = [makeEvent('evt-001'), makeEvent('evt-002')];
    render(<ActiveEventsPanel events={events} />);
    expect(screen.getByText('Event evt-001')).toBeInTheDocument();
    expect(screen.getByText('Event evt-002')).toBeInTheDocument();
  });

  it('clicking an event calls onNavigate with /?eventId={event_id}', () => {
    const onNavigate = jest.fn();
    const events = [makeEvent('event-abc-123')];
    render(<ActiveEventsPanel events={events} onNavigate={onNavigate} />);

    const btn = screen.getByTestId('event-btn-event-abc-123');
    fireEvent.click(btn);

    expect(onNavigate).toHaveBeenCalledWith('/?eventId=event-abc-123');
  });

  it('encodes special characters in event_id in the navigation URL', () => {
    const onNavigate = jest.fn();
    const events = [makeEvent('event with spaces')];
    render(<ActiveEventsPanel events={events} onNavigate={onNavigate} />);

    const btn = screen.getByTestId('event-btn-event with spaces');
    fireEvent.click(btn);

    // URL should encode spaces
    const calledUrl = (onNavigate as jest.Mock).mock.calls[0][0] as string;
    expect(calledUrl).toContain('eventId=');
    expect(calledUrl).not.toContain(' ');
  });

  it('renders multiple events as list items', () => {
    const events = [makeEvent('e1'), makeEvent('e2'), makeEvent('e3')];
    render(<ActiveEventsPanel events={events} />);

    const items = screen.getAllByRole('listitem');
    expect(items).toHaveLength(3);
  });
});
