import React from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../providers/AuthProvider";
import { ROUTES } from "../routes";

export function RequireAuth({ children }: { children: React.ReactNode }) {
  const { state } = useAuth();
  const location = useLocation();
  if (state.status === "loading") {
    return <div data-testid="auth-loading" className="flex min-h-screen items-center justify-center text-muted">Loading…</div>;
  }
  if (state.status === "anonymous") {
    return <Navigate to={ROUTES.login} replace state={{ from: location }} />;
  }
  return <>{children}</>;
}
