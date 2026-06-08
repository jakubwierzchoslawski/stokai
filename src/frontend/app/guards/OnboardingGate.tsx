import React from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../providers/AuthProvider";
import { ROUTES } from "../routes";

export function OnboardingGate() {
  const { state } = useAuth();
  const location = useLocation();
  if (state.status !== "authenticated") return <Outlet />;
  if (!state.user.onboardingComplete && location.pathname !== ROUTES.onboarding) {
    return <Navigate to={ROUTES.onboarding} replace />;
  }
  return <Outlet />;
}
