/**
 * SourcesPage — /admin/sources container page.
 *
 * Tabs: All Sources | Social Sources | Bindings
 * Route is admin-only. Non-admin users are redirected to /.
 *
 * PLAN-F-028 TASK-007
 */
import React, { useState } from "react";
import { Navigate } from "react-router-dom";
import { useCurrentUser } from "@/app/providers/AuthProvider";
import { useSources } from "./hooks/useSources";
import { SourceList } from "./SourceList";
import { SocialSourcesPanel } from "./SocialSourcesPanel";
import { BindingsPanel } from "./BindingsPanel";

type Tab = "all" | "social" | "bindings";

export const SourcesPage: React.FC = () => {
  const user = useCurrentUser();
  const [activeTab, setActiveTab] = useState<Tab>("all");
  const { data: sources, isLoading, error } = useSources();

  // Route guard: admin only
  if (user.role !== "admin") {
    return <Navigate to="/" replace />;
  }

  return (
    <div className="sources-page" data-testid="sources-page">
      <header className="sources-page__header">
        <h1>Data Source Management</h1>
      </header>

      <nav className="sources-page__tabs" aria-label="Data source tabs" role="tablist">
        <button
          role="tab"
          aria-selected={activeTab === "all"}
          className={`tab-btn ${activeTab === "all" ? "tab-btn--active" : ""}`}
          onClick={() => setActiveTab("all")}
          data-testid="tab-all"
        >
          All Sources
        </button>
        <button
          role="tab"
          aria-selected={activeTab === "social"}
          className={`tab-btn ${activeTab === "social" ? "tab-btn--active" : ""}`}
          onClick={() => setActiveTab("social")}
          data-testid="tab-social"
        >
          Social Sources
        </button>
        <button
          role="tab"
          aria-selected={activeTab === "bindings"}
          className={`tab-btn ${activeTab === "bindings" ? "tab-btn--active" : ""}`}
          onClick={() => setActiveTab("bindings")}
          data-testid="tab-bindings"
        >
          Bindings
        </button>
      </nav>

      <main className="sources-page__content">
        {isLoading && (
          <div className="sources-loading" aria-busy="true" data-testid="sources-loading">
            Loading sources…
          </div>
        )}

        {error && (
          <div className="sources-error" role="alert" data-testid="sources-error">
            Failed to load sources: {error.message}
          </div>
        )}

        {!isLoading && !error && (
          <>
            {activeTab === "all" && (
              <SourceList sources={sources ?? []} />
            )}
            {activeTab === "social" && (
              <SocialSourcesPanel sources={sources ?? []} />
            )}
            {activeTab === "bindings" && (
              <BindingsPanel />
            )}
          </>
        )}
      </main>
    </div>
  );
};

export default SourcesPage;
