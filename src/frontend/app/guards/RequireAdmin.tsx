import React from "react";
import { useAuth } from "../providers/AuthProvider";

export function RequireAdmin({ children }: { children: React.ReactNode }) {
  const { state } = useAuth();
  if (state.status !== "authenticated" || state.user.role !== "admin") {
    return (
      <div data-testid="access-denied" className="flex min-h-[60vh] items-center justify-center p-6">
        <div className="max-w-md rounded-lg border border-border bg-surface-1 p-6 text-center">
          <h2 className="text-lg font-semibold">Access denied</h2>
          <p className="mt-2 text-sm text-muted">You need administrator permissions to view this page.</p>
        </div>
      </div>
    );
  }
  return <>{children}</>;
}
