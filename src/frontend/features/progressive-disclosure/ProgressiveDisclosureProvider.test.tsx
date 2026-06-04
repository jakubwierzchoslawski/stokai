/**
 * ProgressiveDisclosureProvider.test.tsx — TDD tests for state machine.
 *
 * PLAN-F-020 TASK-012
 */

import React from 'react';
import { render, screen, act, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';

import {
  ProgressiveDisclosureProvider,
  useDisclosure,
} from './ProgressiveDisclosureProvider';
import type { EventPulse } from '../intelligence-map/types/map.types';

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Wrapper = ({ children }: { children: React.ReactNode }) =>
    React.createElement(
      QueryClientProvider,
      { client: qc },
      React.createElement(
        MemoryRouter,
        null,
        React.createElement(ProgressiveDisclosureProvider, null, children),
      ),
    );
  return Wrapper;
}

// Test consumer that exposes state and actions via data-testid
function TestConsumer() {
  const {
    state,
    openPopup,
    expandToSidePanel,
    openAuditTrail,
    closePopup,
    closeSidePanel,
    closeAuditTrail,
    onExpandEvent,
  } = useDisclosure();

  return (
    <div>
      <div data-testid="selected-event-id">{state.selectedEventId ?? 'null'}</div>
      <div data-testid="popup-open">{String(state.popupOpen)}</div>
      <div data-testid="side-panel-open">{String(state.sidePanelOpen)}</div>
      <div data-testid="audit-trail-open">{String(state.auditTrailOpen)}</div>

      <button data-testid="btn-open-popup" onClick={() => openPopup('evt-1')}>openPopup</button>
      <button data-testid="btn-expand" onClick={expandToSidePanel}>expand</button>
      <button data-testid="btn-open-audit" onClick={openAuditTrail}>openAuditTrail</button>
      <button data-testid="btn-close-popup" onClick={closePopup}>closePopup</button>
      <button data-testid="btn-close-side-panel" onClick={closeSidePanel}>closeSidePanel</button>
      <button data-testid="btn-close-audit" onClick={closeAuditTrail}>closeAuditTrail</button>
      <button
        data-testid="btn-on-expand-event"
        onClick={() => onExpandEvent({ event_id: 'evt-1' } as EventPulse)}
      >
        onExpandEvent
      </button>
    </div>
  );
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('ProgressiveDisclosureProvider', () => {
  it('initialises with all state false and selectedEventId null', () => {
    render(<TestConsumer />, { wrapper: makeWrapper() });

    expect(screen.getByTestId('selected-event-id')).toHaveTextContent('null');
    expect(screen.getByTestId('popup-open')).toHaveTextContent('false');
    expect(screen.getByTestId('side-panel-open')).toHaveTextContent('false');
    expect(screen.getByTestId('audit-trail-open')).toHaveTextContent('false');
  });

  it('openPopup sets popupOpen=true and selectedEventId', () => {
    render(<TestConsumer />, { wrapper: makeWrapper() });

    fireEvent.click(screen.getByTestId('btn-open-popup'));

    expect(screen.getByTestId('popup-open')).toHaveTextContent('true');
    expect(screen.getByTestId('selected-event-id')).toHaveTextContent('evt-1');
  });

  it('expandToSidePanel after openPopup sets sidePanelOpen=true; popup remains open', () => {
    render(<TestConsumer />, { wrapper: makeWrapper() });

    fireEvent.click(screen.getByTestId('btn-open-popup'));
    fireEvent.click(screen.getByTestId('btn-expand'));

    expect(screen.getByTestId('side-panel-open')).toHaveTextContent('true');
    expect(screen.getByTestId('popup-open')).toHaveTextContent('true');
  });

  it('openAuditTrail after expandToSidePanel sets auditTrailOpen=true', () => {
    render(<TestConsumer />, { wrapper: makeWrapper() });

    fireEvent.click(screen.getByTestId('btn-open-popup'));
    fireEvent.click(screen.getByTestId('btn-expand'));
    fireEvent.click(screen.getByTestId('btn-open-audit'));

    expect(screen.getByTestId('audit-trail-open')).toHaveTextContent('true');
  });

  it('closePopup resets all state to initial values', () => {
    render(<TestConsumer />, { wrapper: makeWrapper() });

    fireEvent.click(screen.getByTestId('btn-open-popup'));
    fireEvent.click(screen.getByTestId('btn-expand'));
    fireEvent.click(screen.getByTestId('btn-open-audit'));
    fireEvent.click(screen.getByTestId('btn-close-popup'));

    expect(screen.getByTestId('selected-event-id')).toHaveTextContent('null');
    expect(screen.getByTestId('popup-open')).toHaveTextContent('false');
    expect(screen.getByTestId('side-panel-open')).toHaveTextContent('false');
    expect(screen.getByTestId('audit-trail-open')).toHaveTextContent('false');
  });

  it('closeSidePanel sets sidePanelOpen=false and auditTrailOpen=false without changing popupOpen', () => {
    render(<TestConsumer />, { wrapper: makeWrapper() });

    fireEvent.click(screen.getByTestId('btn-open-popup'));
    fireEvent.click(screen.getByTestId('btn-expand'));
    fireEvent.click(screen.getByTestId('btn-open-audit'));
    fireEvent.click(screen.getByTestId('btn-close-side-panel'));

    expect(screen.getByTestId('side-panel-open')).toHaveTextContent('false');
    expect(screen.getByTestId('audit-trail-open')).toHaveTextContent('false');
    // popup was open before closeSidePanel — it should remain open
    expect(screen.getByTestId('popup-open')).toHaveTextContent('true');
  });

  it('onExpandEvent is equivalent to calling openPopup with event.event_id', () => {
    render(<TestConsumer />, { wrapper: makeWrapper() });

    fireEvent.click(screen.getByTestId('btn-on-expand-event'));

    expect(screen.getByTestId('popup-open')).toHaveTextContent('true');
    expect(screen.getByTestId('selected-event-id')).toHaveTextContent('evt-1');
  });
});
