/**
 * ResponsiveLayout.tsx — Context provider for layout strategy.
 *
 * Wraps a subtree with a declared layout strategy ("desktop-first" or
 * "mobile-first") and exposes it via React context. No DOM wrapper is emitted —
 * the component renders its children inside a Fragment.
 *
 * Usage:
 *   // Desktop-first surfaces (Intelligence Map, Admin Panel)
 *   <ResponsiveLayout strategy="desktop-first">
 *     <IntelligenceMap />
 *   </ResponsiveLayout>
 *
 *   // Mobile-first surfaces (Alerts Center, Briefs Reader)
 *   <ResponsiveLayout strategy="mobile-first">
 *     <AlertsCenterPage />
 *   </ResponsiveLayout>
 *
 * Consumers read the active strategy via useLayoutStrategy():
 *   const strategy = useLayoutStrategy(); // "desktop-first" | "mobile-first"
 *
 * Route wiring: wrap each route subtree in routes.tsx with the correct strategy.
 *   "/" (IntelligenceMap) → strategy="desktop-first"
 *   "/admin*"             → strategy="desktop-first"
 *   "/alerts*"            → strategy="mobile-first"
 *   "/briefs*"            → strategy="mobile-first"
 *
 * PLAN-N-014 TASK-004
 */

import React, { createContext, useContext } from "react";

// ── Types ─────────────────────────────────────────────────────────────────────

export type LayoutStrategy = "desktop-first" | "mobile-first";

export interface ResponsiveLayoutProps {
  strategy: LayoutStrategy;
  children: React.ReactNode;
}

// ── Context ───────────────────────────────────────────────────────────────────

const LayoutStrategyContext = createContext<LayoutStrategy>("desktop-first");

// ── Component ─────────────────────────────────────────────────────────────────

/**
 * Provides the layout strategy to all descendant components.
 * Emits no DOM wrapper — renders children inside a React.Fragment.
 */
export function ResponsiveLayout({
  strategy,
  children,
}: ResponsiveLayoutProps): React.ReactElement {
  return (
    <LayoutStrategyContext.Provider value={strategy}>
      <>{children}</>
    </LayoutStrategyContext.Provider>
  );
}

// ── Consumer hook ─────────────────────────────────────────────────────────────

/**
 * Returns the active layout strategy from the nearest ResponsiveLayout ancestor.
 * Falls back to "desktop-first" if used outside a ResponsiveLayout.
 */
export function useLayoutStrategy(): LayoutStrategy {
  return useContext(LayoutStrategyContext);
}

export default ResponsiveLayout;
