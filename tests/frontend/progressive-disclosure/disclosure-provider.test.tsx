/**
 * disclosure-provider.test.tsx — Tests for ProgressiveDisclosureProvider state machine.
 *
 * PLAN-F-020 TASK-012 (TDD)
 *
 * Tests the state machine actions and transitions via useDisclosure hook.
 */

import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';

import {
  ProgressiveDisclosureProvider,
  useDisclosure,
} from '../../../src/frontend/features/progressive-disclosure/ProgressiveDisclosureProvider';
import type { EventPulse } from '../../../src/frontend/features/intelligence-map/types/map.types';

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
  it('initial state: popupOpen=false, sidePanelOpen=false, auditTrailOpen=false, selectedEventId=null', () => {
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

  it('expandToSidePanel after openPopup: sidePanelOpen=true, popupOpen remains true', () => {
    render(<TestConsumer />, { wrapper: makeWrapper() });

    fireEvent.click(screen.getByTestId('btn-open-popup'));
    fireEvent.click(screen.getByTestId('btn-expand'));

    expect(screen.getByTestId('side-panel-open')).toHaveTextContent('true');
    expect(screen.getByTestId('popup-open')).toHaveTextContent('true');
  });

  it('openAuditTrail after expandToSidePanel: auditTrailOpen=true', () => {
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
    expect(screen.getByTestId('popup-open')).toHaveTextContent('true');
  });

  it('onExpandEvent({ event_id: "evt-1" }) is equivalent to openPopup("evt-1")', () => {
    render(<TestConsumer />, { wrapper: makeWrapper() });

    fireEvent.click(screen.getByTestId('btn-on-expand-event'));

    expect(screen.getByTestId('popup-open')).toHaveTextContent('true');
    expect(screen.getByTestId('selected-event-id')).toHaveTextContent('evt-1');
  });
});
