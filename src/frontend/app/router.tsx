import React from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import { LoginPage } from "@/features/auth/LoginPage";
import { RegisterPage } from "@/features/auth/RegisterPage";
import { RequireAuth } from "./guards/RequireAuth";
import { AppShell } from "@/layout/AppShell";
import { ROUTES } from "./routes";

export function AppRouter() {
  return (
    <Routes>
      <Route path={ROUTES.login} element={<LoginPage />} />
      <Route path={ROUTES.register} element={<RegisterPage />} />
      <Route
        element={
          <RequireAuth>
            <AppShell />
          </RequireAuth>
        }
      >
        <Route path={ROUTES.home} element={<div className="p-6">App home (interim)</div>} />
      </Route>
      <Route path="*" element={<Navigate to={ROUTES.home} replace />} />
    </Routes>
  );
}
