/**
 * SystemOpsPage — top-level page with five tabs for system operations.
 *
 * Tabs:
 *   1. Ingestion Jobs
 *   2. Cost Monitor
 *   3. Company Universe
 *   4. Cache Inspection
 *   5. Feature Flags
 *
 * PLAN-F-030 TASK-009
 */
import React, { useState } from "react";
import { IngestionJobsTab } from "./IngestionJobsTab";
import { CostMonitorTab } from "./CostMonitorTab";
import { CompanyUniverseTab } from "./CompanyUniverseTab";
import { CacheInspectionTab } from "./CacheInspectionTab";
import { FeatureFlagsTab } from "./FeatureFlagsTab";

type Tab =
  | "ingestion"
  | "cost"
  | "companies"
  | "cache"
  | "flags";

const TABS: Array<{ id: Tab; label: string }> = [
  { id: "ingestion", label: "Ingestion Jobs" },
  { id: "cost", label: "Cost Monitor" },
  { id: "companies", label: "Company Universe" },
  { id: "cache", label: "Cache" },
  { id: "flags", label: "Feature Flags" },
];

export const SystemOpsPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState<Tab>("ingestion");

  return (
    <div data-testid="system-ops-page">
      <h1>System Operations</h1>

      {/* Tab bar */}
      <nav
        data-testid="system-ops-tabs"
        style={{ display: "flex", gap: 0, borderBottom: "2px solid #e5e7eb", marginBottom: 24 }}
        role="tablist"
      >
        {TABS.map((tab) => (
          <button
            key={tab.id}
            data-testid={`tab-${tab.id}`}
            role="tab"
            aria-selected={activeTab === tab.id}
            onClick={() => setActiveTab(tab.id)}
            style={{
              padding: "8px 20px",
              border: "none",
              background: "none",
              borderBottom:
                activeTab === tab.id
                  ? "2px solid #3b82f6"
                  : "2px solid transparent",
              color: activeTab === tab.id ? "#3b82f6" : "#374151",
              fontWeight: activeTab === tab.id ? 600 : 400,
              cursor: "pointer",
            }}
          >
            {tab.label}
          </button>
        ))}
      </nav>

      {/* Active tab content */}
      <div data-testid="system-ops-tab-content">
        {activeTab === "ingestion" && <IngestionJobsTab />}
        {activeTab === "cost" && <CostMonitorTab />}
        {activeTab === "companies" && <CompanyUniverseTab />}
        {activeTab === "cache" && <CacheInspectionTab />}
        {activeTab === "flags" && <FeatureFlagsTab />}
      </div>
    </div>
  );
};

export default SystemOpsPage;
