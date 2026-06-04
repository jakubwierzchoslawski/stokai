/**
 * app/routes.tsx — Application routing configuration with onboarding route guard.
 *
 * Route guard: On authenticated route load, GET /api/v1/onboarding/state.
 * If is_onboarding_required=true → redirect to /onboarding.
 * Otherwise → render the requested route.
 *
 * PLAN-F-024 TASK-009
 */
import React, { useEffect, useState } from 'react';

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
