/**
 * useCurrentUser — returns the current authenticated user from session/context.
 *
 * In production this reads from an auth context populated by the JWT token.
 * For the HIL queue route guard the only field needed is role.
 *
 * PLAN-F-013 TASK-008
 */
import { useEffect, useState } from "react";

export interface CurrentUser {
  user_id: string;
  tenant_id: string;
  role: "admin" | "operator" | "end_user";
  email: string;
}

async function fetchCurrentUser(): Promise<CurrentUser | null> {
  try {
    const response = await fetch("/api/v1/auth/me", {
      credentials: "include",
    });
    if (!response.ok) return null;
    const envelope = await response.json();
    return envelope.data as CurrentUser;
  } catch {
    return null;
  }
}

export function useCurrentUser(): { user: CurrentUser | null; isLoading: boolean } {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    fetchCurrentUser()
      .then(setUser)
      .finally(() => setIsLoading(false));
  }, []);

  return { user, isLoading };
}
