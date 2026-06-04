/**
 * app/routes.tsx — Application routing configuration with onboarding route guard.
 *
 * Route guard: On authenticated route load, GET /api/v1/onboarding/state.
 * If is_onboarding_required=true → redirect to /onboarding.
 * Otherwise → render the requested route.
 *
 * PLAN-F-024 TASK-009
 * PLAN-F-026 TASK-008 — /briefs and /briefs/:brief_id routes added.
 * PLAN-F-019 TASK-011 — root route "/" wired to IntelligenceMap.
 *
 * Root route usage (React Router v6):
 *
 *   import { IntelligenceMap } from '../features/intelligence-map/IntelligenceMap';
 *
 *   <Route path="/" element={<IntelligenceMap />} />
 *
 * The root route renders IntelligenceMap directly with no intermediate landing page
 * or dashboard redirect (AC-001).
 */
import React, { useEffect, useState } from 'react';

// ── Root route path ───────────────────────────────────────────────────────────

/**
 * The root route path that renders <IntelligenceMap />.
 * Import this constant in the application router to keep the path a single source
 * of truth. No intermediate dashboard — IntelligenceMap is the application root.
 *
 * Example:
 *   import { ROOT_ROUTE_PATH } from './routes';
 *   import { IntelligenceMap } from '../features/intelligence-map/IntelligenceMap';
 *
 *   <Route path={ROOT_ROUTE_PATH} element={<IntelligenceMap />} />
 */
export const ROOT_ROUTE_PATH = '/' as const;

// ── Types ──────────────────────────────────────────────────────────────────────

interface OnboardingStateResponse {
  is_onboarding_required?: boolean;
  is_complete?: boolean;
  skipped?: boolean;
  has_holding?: boolean;
}

async function fetchOnboardingRequired(): Promise<boolean> {
  try {
    const resp = await fetch('/api/v1/onboarding/state', {
      credentials: 'include',
    });
    if (!resp.ok) return false;
    const body = await resp.json();
    const state: OnboardingStateResponse = body.data;
    // is_onboarding_required: not complete AND not skipped AND no holding
    return !state.is_complete && !state.skipped && !state.has_holding;
  } catch {
    return false;
  }
}

// ── Route guard hook ───────────────────────────────────────────────────────────

interface RouteGuardState {
  loading: boolean;
  redirectToOnboarding: boolean;
}

export function useRouteGuard(): RouteGuardState {
  const [state, setState] = useState<RouteGuardState>({
    loading: true,
    redirectToOnboarding: false,
  });

  useEffect(() => {
    fetchOnboardingRequired().then((required) => {
      setState({ loading: false, redirectToOnboarding: required });
    });
  }, []);

  return state;
}

// ── Protected route wrapper ────────────────────────────────────────────────────

export interface ProtectedRouteProps {
  children: React.ReactNode;
  onRedirectToOnboarding?: () => void;
  onRedirectToMap?: () => void;
}

export function ProtectedRoute({
  children,
  onRedirectToOnboarding,
  onRedirectToMap,
}: ProtectedRouteProps): React.ReactElement {
  const { loading, redirectToOnboarding } = useRouteGuard();

  useEffect(() => {
    if (!loading && redirectToOnboarding && onRedirectToOnboarding) {
      onRedirectToOnboarding();
    }
  }, [loading, redirectToOnboarding, onRedirectToOnboarding]);

  if (loading) {
    return <div data-testid="route-guard-loading">Loading...</div>;
  }

  if (redirectToOnboarding) {
    return <div data-testid="route-guard-redirect-onboarding">Redirecting to onboarding...</div>;
  }

  return <>{children}</>;
}

// ── Briefs routes (PLAN-F-026 TASK-008) ─────────────────────────────────────
//
// Both routes are auth-guarded (wrap in ProtectedRoute in the host App).
//
//   /briefs            → BriefsPage
//   /briefs/:brief_id  → BriefDetailPage
//
// To wire in the host application (example React Router v6 usage):
//
//   import { BriefsPage } from '../features/briefs/BriefsPage';
//   import { BriefDetailPage } from '../features/briefs/BriefDetailPage';
//
//   <Route path="/briefs" element={<ProtectedRoute><BriefsPage /></ProtectedRoute>} />
//   <Route path="/briefs/:brief_id" element={<ProtectedRoute><BriefDetailPage /></ProtectedRoute>} />
//
export const BRIEFS_ROUTE_PATHS = {
  list: '/briefs',
  detail: '/briefs/:brief_id',
} as const;

// ── Admin AI Audit Console routes (PLAN-F-029 TASK-012) ───────────────────────
//
// The /admin/ai-audit route must be wrapped in <RequireAdmin> so that
// non-admin users cannot access any sub-path.
//
// Example React Router v6 wiring:
//
//   import { RequireAdmin } from '../admin/RequireAdmin';
//   import { AiAuditConsolePage } from '../admin/ai-audit/AiAuditConsolePage';
//
//   <Route
//     path="/admin/ai-audit"
//     element={
//       <RequireAdmin>
//         <AiAuditConsolePage />
//       </RequireAdmin>
//     }
//   />
//
export const ADMIN_AI_AUDIT_ROUTE_PATH = '/admin/ai-audit' as const;

// ── Progressive Disclosure routes (PLAN-F-020 TASK-012) ─────────────────────
//
// The root "/" route element must be wrapped with <ProgressiveDisclosureProvider>
// so that popup/side-panel state is co-located with the map route.
// The onExpandEvent callback is passed to <IntelligenceMap> via the provider's
// context (or directly as a prop from the parent that reads useDisclosure()).
//
// Example React Router v6 wiring:
//
//   import { ProgressiveDisclosureProvider } from
//     '../features/progressive-disclosure/ProgressiveDisclosureProvider';
//   import { DeepDivePage } from
//     '../features/progressive-disclosure/components/DeepDivePage';
//   import { IntelligenceMap } from
//     '../features/intelligence-map/IntelligenceMap';
//
//   <Route
//     path="/"
//     element={
//       <ProtectedRoute>
//         <ProgressiveDisclosureProvider>
//           <IntelligenceMap onExpandEvent={...} />
//         </ProgressiveDisclosureProvider>
//       </ProtectedRoute>
//     }
//   />
//   <Route
//     path={DEEP_DIVE_ROUTE_PATH}
//     element={<ProtectedRoute><DeepDivePage /></ProtectedRoute>}
//   />
//
export const DEEP_DIVE_ROUTE_PATH = '/events/:eventId/deep-dive' as const;
