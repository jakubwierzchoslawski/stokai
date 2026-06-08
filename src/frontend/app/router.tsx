import React from "react";
import { Routes, Route } from "react-router-dom";

export function AppRouter() {
  return (
    <Routes>
      <Route
        path="*"
        element={
          <div className="flex min-h-screen items-center justify-center bg-surface-0 text-text">
            <div className="text-lg">Shell OK</div>
          </div>
        }
      />
    </Routes>
  );
}
