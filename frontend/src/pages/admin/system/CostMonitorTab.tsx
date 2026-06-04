/**
 * CostMonitorTab — cost monitor with budget gauge, breakdown tables, and threshold edit.
 *
 * - Gauge: green < 80%, amber 80-99%, red >= 100%
 * - Hard-stop banner when hard_stop_active=true
 * - Breakdown tables: by source, by model, by workflow
 * - Budget threshold edit: number input + Save button
 *
 * PLAN-F-030 TASK-009
 */
import React, { useState } from "react";
import { useCostSummary, useUpdateThreshold } from "./hooks/useSystemOps";

const GaugeColor = (pct: number): string => {
  if (pct >= 100) return "#ef4444";
  if (pct >= 80) return "#f59e0b";
  return "#22c55e";
};

export const CostMonitorTab: React.FC = () => {
  const { data: cost, isLoading, isError } = useCostSummary();
  const updateThreshold = useUpdateThreshold();
  const [thresholdInput, setThresholdInput] = useState<string>("");

  const handleSaveThreshold = async () => {
    const val = parseFloat(thresholdInput);
    if (isNaN(val) || val <= 0) {
      alert("Enter a positive number for the budget threshold.");
      return;
    }
    try {
      await updateThreshold.mutateAsync(val);
      alert(`Threshold updated to $${val}`);
      setThresholdInput("");
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to update threshold");
    }
  };

  if (isLoading) return <div data-testid="cost-loading">Loading...</div>;
  if (isError) return <div data-testid="cost-error">Failed to load cost data</div>;
  if (!cost) return null;

  const pct = cost.pct_used;

  return (
    <div data-testid="cost-monitor-tab">
      <h2>Cost Monitor</h2>

      {/* Hard-stop banner */}
      {cost.hard_stop_active && (
        <div
          data-testid="hard-stop-banner"
          style={{
            background: "#ef4444",
            color: "#fff",
            padding: "12px 16px",
            borderRadius: 4,
            marginBottom: 16,
          }}
        >
          HARD STOP ACTIVE — Monthly budget exhausted. No further AI workflows
          will be dispatched.
        </div>
      )}

      {/* Budget gauge */}
      <div data-testid="budget-gauge" style={{ marginBottom: 24 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <span>Budget Used:</span>
          <span
            data-testid="budget-pct"
            style={{ color: GaugeColor(pct), fontWeight: 700, fontSize: "1.5rem" }}
          >
            {pct.toFixed(1)}%
          </span>
          <span style={{ color: "#6b7280" }}>
            (${cost.spend_usd.toFixed(2)} / ${cost.threshold_usd.toFixed(2)})
          </span>
        </div>
        <div
          style={{
            background: "#e5e7eb",
            height: 16,
            borderRadius: 8,
            marginTop: 8,
            overflow: "hidden",
          }}
        >
          <div
            data-testid="gauge-bar"
            style={{
              width: `${Math.min(pct, 100)}%`,
              height: "100%",
              background: GaugeColor(pct),
              transition: "width 0.3s",
            }}
          />
        </div>
        {cost.warning_active && !cost.hard_stop_active && (
          <div
            data-testid="warning-banner"
            style={{ color: "#f59e0b", marginTop: 8, fontWeight: 600 }}
          >
            Warning: spending approaching budget limit.
          </div>
        )}
      </div>

      {/* Breakdown: by source */}
      <h3>By Source</h3>
      <table style={{ borderCollapse: "collapse", marginBottom: 16 }}>
        <thead>
          <tr>
            <th>Source</th>
            <th>Cost (USD)</th>
          </tr>
        </thead>
        <tbody>
          {cost.by_source.map((row) => (
            <tr key={row.source}>
              <td>{row.source}</td>
              <td>${row.total_cost_usd.toFixed(4)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {/* Breakdown: by model */}
      <h3>By Model</h3>
      <table style={{ borderCollapse: "collapse", marginBottom: 16 }}>
        <thead>
          <tr>
            <th>Model</th>
            <th>Cost (USD)</th>
          </tr>
        </thead>
        <tbody>
          {cost.by_model.map((row) => (
            <tr key={row.model}>
              <td>{row.model}</td>
              <td>${row.total_cost_usd.toFixed(4)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {/* Breakdown: by workflow */}
      <h3>By Workflow</h3>
      <table style={{ borderCollapse: "collapse", marginBottom: 16 }}>
        <thead>
          <tr>
            <th>Workflow</th>
            <th>Cost (USD)</th>
          </tr>
        </thead>
        <tbody>
          {cost.by_workflow.map((row) => (
            <tr key={row.workflow_type}>
              <td>{row.workflow_type}</td>
              <td>${row.total_cost_usd.toFixed(4)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {/* Budget threshold edit */}
      <div data-testid="threshold-editor" style={{ display: "flex", gap: 8, alignItems: "center" }}>
        <label htmlFor="threshold-input">Budget Threshold (USD):</label>
        <input
          id="threshold-input"
          data-testid="threshold-input"
          type="number"
          min="0.01"
          step="0.01"
          value={thresholdInput}
          onChange={(e) => setThresholdInput(e.target.value)}
          placeholder={String(cost.threshold_usd)}
          style={{ width: 100 }}
        />
        <button
          data-testid="save-threshold-btn"
          onClick={handleSaveThreshold}
          disabled={updateThreshold.isPending}
        >
          {updateThreshold.isPending ? "Saving..." : "Save"}
        </button>
      </div>
    </div>
  );
};

export default CostMonitorTab;
