/**
 * RequireAdmin — route guard that restricts access to admin-role users.
 *
 * Reads the current user's role from auth context.
 * If role !== 'admin': redirects to '/' and renders nothing.
 * If role === 'admin': renders {children}.
 *
 * Usage (React Router v6):
 *   <Route
 *     path="/admin/ai-audit/*"
 *     element={
 *       <RequireAdmin>
 *         <AiAuditConsolePage />
 *       </RequireAdmin>
 *     }
 *   />
 *
 * PLAN-F-029 TASK-012
 */
import React, { useContext } from 'react';

// ── Auth context contract ──────────────────────────────────────────────────────

/**
 * Minimal auth context shape consumed by RequireAdmin.
 * The host application must provide this context via AuthProvider.
 */
export interface AuthContextValue {
  role: string | null;
  isAuthenticated: boolean;
}

export const AuthContext = React.createContext<AuthContextValue>({
  role: null,
  isAuthenticated: false,
});

// ── RequireAdmin component ─────────────────────────────────────────────────────

interface Props {
  children: React.ReactNode;
  redirectTo?: string;
  onRedirect?: (to: string) => void;
}

/**
 * RequireAdmin — renders children only when current user role is 'admin'.
 *
 * When role is not 'admin', calls onRedirect('/') (or window.location.replace
 * as fallback) and renders null.
 */
export function RequireAdmin({
  children,
  redirectTo = '/',
  onRedirect,
}: Props): React.ReactElement | null {
  const { role, isAuthenticated } = useContext(AuthContext);

  if (!isAuthenticated || role !== 'admin') {
    if (onRedirect) {
      onRedirect(redirectTo);
    } else if (typeof window !== 'undefined') {
      window.location.replace(redirectTo);
    }
    return null;
  }

  return <>{children}</>;
}
