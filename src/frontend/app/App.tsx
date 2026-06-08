import React from "react";
import { BrowserRouter } from "react-router-dom";
import { ErrorBoundary } from "./providers/ErrorBoundary";
import { ThemeProvider } from "./providers/ThemeProvider";
import { QueryProvider } from "./providers/QueryProvider";
import { AuthProvider } from "./providers/AuthProvider";
import { AppRouter } from "./router";

export function App() {
  return (
    <ErrorBoundary>
      <ThemeProvider>
        <QueryProvider>
          <AuthProvider>
            <BrowserRouter>
              <AppRouter />
            </BrowserRouter>
          </AuthProvider>
        </QueryProvider>
      </ThemeProvider>
    </ErrorBoundary>
  );
}
