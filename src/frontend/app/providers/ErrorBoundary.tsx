import React from "react";

interface State { error: Error | null; }

export class ErrorBoundary extends React.Component<{ children: React.ReactNode }, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error("[ErrorBoundary]", error, info);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="flex min-h-screen items-center justify-center bg-surface-0 p-6 text-text">
          <div className="max-w-md rounded-lg border border-border bg-surface-1 p-6 shadow-md">
            <h1 className="text-xl font-semibold">Something went wrong</h1>
            <p className="mt-2 text-sm text-muted">
              The application hit an unexpected error. Try reloading the page.
            </p>
            <pre className="mt-3 overflow-auto rounded bg-surface-0 p-2 text-xs text-muted">
              {this.state.error.message}
            </pre>
            <button
              className="mt-4 rounded bg-signal px-3 py-1.5 text-sm font-medium text-signal-fg"
              onClick={() => window.location.reload()}
            >
              Reload
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
