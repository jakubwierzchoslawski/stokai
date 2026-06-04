/**
 * ProgressiveDisclosureProvider.tsx — Context provider for the three-level UI state machine.
 *
 * PLAN-F-020 TASK-012
 *
 * Manages open/close state for popup, side panel, and audit trail.
 * Renders overlay components as siblings to children.
 * Exposes onExpandEvent(event: EventPulse) as the injectable prop for IntelligenceMap.
 *
 * State machine:
 *   openPopup       → popupOpen=true, selectedEventId=<id>
 *   expandToSidePanel → sidePanelOpen=true (popup stays open)
 *   openAuditTrail  → auditTrailOpen=true (requires sidePanelOpen=true)
 *   closePopup      → resets all state
 *   closeSidePanel  → sidePanelOpen=false, auditTrailOpen=false
 *   closeAuditTrail → auditTrailOpen=false
 *
 * AC-001, AC-002, AC-003
 */

import React, { createContext, useCallback, useContext, useMemo, useReducer } from 'react';
import { useNavigate } from 'react-router-dom';

import type { EventPulse } from '../intelligence-map/types/map.types';
import { AuditTrailView } from './components/AuditTrailView';
import { EventPopup } from './components/EventPopup';
import { SidePanel } from './components/SidePanel';

// ── State ─────────────────────────────────────────────────────────────────────

export interface DisclosureState {
  selectedEventId: string | null;
  popupOpen: boolean;
  sidePanelOpen: boolean;
  auditTrailOpen: boolean;
}

const INITIAL_STATE: DisclosureState = {
  selectedEventId: null,
  popupOpen: false,
  sidePanelOpen: false,
  auditTrailOpen: false,
};

// ── Actions ───────────────────────────────────────────────────────────────────

type Action =
  | { type: 'OPEN_POPUP'; eventId: string }
  | { type: 'EXPAND_TO_SIDE_PANEL' }
  | { type: 'OPEN_AUDIT_TRAIL' }
  | { type: 'CLOSE_POPUP' }
  | { type: 'CLOSE_SIDE_PANEL' }
  | { type: 'CLOSE_AUDIT_TRAIL' };

function reducer(state: DisclosureState, action: Action): DisclosureState {
  switch (action.type) {
    case 'OPEN_POPUP':
      return {
        ...state,
        selectedEventId: action.eventId,
        popupOpen: true,
      };
    case 'EXPAND_TO_SIDE_PANEL':
      return { ...state, sidePanelOpen: true };
    case 'OPEN_AUDIT_TRAIL':
      // Guard: audit trail only opens when side panel is open
      if (!state.sidePanelOpen) return state;
      return { ...state, auditTrailOpen: true };
    case 'CLOSE_POPUP':
      return INITIAL_STATE;
    case 'CLOSE_SIDE_PANEL':
      return { ...state, sidePanelOpen: false, auditTrailOpen: false };
    case 'CLOSE_AUDIT_TRAIL':
      return { ...state, auditTrailOpen: false };
    default:
      return state;
  }
}

// ── Context ───────────────────────────────────────────────────────────────────

export interface DisclosureContextValue {
  state: DisclosureState;
  openPopup: (eventId: string) => void;
  expandToSidePanel: () => void;
  openAuditTrail: () => void;
  closePopup: () => void;
  closeSidePanel: () => void;
  closeAuditTrail: () => void;
  /** Injectable prop for IntelligenceMap.onExpandEvent */
  onExpandEvent: (event: EventPulse) => void;
}

export const DisclosureContext = createContext<DisclosureContextValue | null>(null);

export function useDisclosure(): DisclosureContextValue {
  const ctx = useContext(DisclosureContext);
  if (!ctx) {
    throw new Error('useDisclosure must be used within ProgressiveDisclosureProvider');
  }
  return ctx;
}

// ── Provider ──────────────────────────────────────────────────────────────────

export interface ProgressiveDisclosureProviderProps {
  children: React.ReactNode;
}

export function ProgressiveDisclosureProvider({
  children,
}: ProgressiveDisclosureProviderProps) {
  const [state, dispatch] = useReducer(reducer, INITIAL_STATE);
  const navigate = useNavigate();

  const openPopup = useCallback((eventId: string) => {
    dispatch({ type: 'OPEN_POPUP', eventId });
  }, []);

  const expandToSidePanel = useCallback(() => {
    dispatch({ type: 'EXPAND_TO_SIDE_PANEL' });
  }, []);

  const openAuditTrail = useCallback(() => {
    dispatch({ type: 'OPEN_AUDIT_TRAIL' });
  }, []);

  const closePopup = useCallback(() => {
    dispatch({ type: 'CLOSE_POPUP' });
  }, []);

  const closeSidePanel = useCallback(() => {
    dispatch({ type: 'CLOSE_SIDE_PANEL' });
  }, []);

  const closeAuditTrail = useCallback(() => {
    dispatch({ type: 'CLOSE_AUDIT_TRAIL' });
  }, []);

  const onExpandEvent = useCallback(
    (event: EventPulse) => {
      openPopup(event.event_id);
    },
    [openPopup],
  );

  const handleOpenDeepDive = useCallback(() => {
    if (state.selectedEventId) {
      navigate(`/events/${state.selectedEventId}/deep-dive`);
    }
  }, [state.selectedEventId, navigate]);

  const contextValue = useMemo<DisclosureContextValue>(
    () => ({
      state,
      openPopup,
      expandToSidePanel,
      openAuditTrail,
      closePopup,
      closeSidePanel,
      closeAuditTrail,
      onExpandEvent,
    }),
    [
      state,
      openPopup,
      expandToSidePanel,
      openAuditTrail,
      closePopup,
      closeSidePanel,
      closeAuditTrail,
      onExpandEvent,
    ],
  );

  return (
    <DisclosureContext.Provider value={contextValue}>
      {children}

      {/* Level 1 — popup overlay */}
      {state.popupOpen && state.selectedEventId && (
        <EventPopup
          eventId={state.selectedEventId}
          onExpand={expandToSidePanel}
          onClose={closePopup}
        />
      )}

      {/* Level 2 — side panel overlay */}
      <SidePanel
        eventId={state.selectedEventId}
        isOpen={state.sidePanelOpen}
        onClose={closeSidePanel}
        onOpenAuditTrail={openAuditTrail}
        onOpenDeepDive={handleOpenDeepDive}
      />

      {/* Audit trail overlay */}
      <AuditTrailView
        eventId={state.selectedEventId}
        isOpen={state.auditTrailOpen}
        onClose={closeAuditTrail}
      />
    </DisclosureContext.Provider>
  );
}

export default ProgressiveDisclosureProvider;
