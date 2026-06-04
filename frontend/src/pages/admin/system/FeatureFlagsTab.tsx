/**
 * FeatureFlagsTab — feature flag list with toggle switch per row.
 *
 * - Toggle calls PATCH /flags/{flag_id}
 * - Optimistic UI: switch flips immediately, reverts on error
 * - social_twitter row shows "Off by default (D8)" tooltip
 *
 * PLAN-F-030 TASK-010
 */
import React, { useState } from "react";
import { useFeatureFlags, useUpdateFlag, FeatureFlag } from "./hooks/useSystemOps";

const SOCIAL_DEFAULT_OFF_FLAGS = new Set([
  "social_twitter",
  "social_stocktwits",
  "social_reddit",
]);

interface ToggleProps {
  flagId: string;
  enabled: boolean;
  onToggle: (flagId: string, newValue: boolean) => void;
  disabled?: boolean;
}

const Toggle: React.FC<ToggleProps> = ({ flagId, enabled, onToggle, disabled }) => (
  <label
    data-testid={`toggle-label-${flagId}`}
    style={{ display: "inline-flex", alignItems: "center", gap: 6, cursor: disabled ? "not-allowed" : "pointer" }}
  >
    <input
      data-testid={`toggle-${flagId}`}
      type="checkbox"
      checked={enabled}
      onChange={(e) => onToggle(flagId, e.target.checked)}
      disabled={disabled}
    />
    <span>{enabled ? "Enabled" : "Disabled"}</span>
  </label>
);

export const FeatureFlagsTab: React.FC = () => {
  const { data: flags, isLoading, isError } = useFeatureFlags();
  const updateFlag = useUpdateFlag();

  // Local optimistic state: flag_id -> bool override
  const [optimistic, setOptimistic] = useState<Record<string, boolean>>({});

  const getEffectiveEnabled = (flag: FeatureFlag): boolean => {
    if (flag.flag_id in optimistic) return optimistic[flag.flag_id];
    return flag.enabled;
  };

  const handleToggle = async (flagId: string, newValue: boolean) => {
    // Apply optimistic update immediately
    setOptimistic((prev) => ({ ...prev, [flagId]: newValue }));

    try {
      await updateFlag.mutateAsync({ flag_id: flagId, enabled: newValue });
      // On success, clear optimistic — query cache will be refreshed
      setOptimistic((prev) => {
        const next = { ...prev };
        delete next[flagId];
        return next;
      });
    } catch (err: unknown) {
      // Revert on error
      setOptimistic((prev) => {
        const next = { ...prev };
        delete next[flagId];
        return next;
      });
      alert(err instanceof Error ? err.message : "Failed to update flag");
    }
  };

  if (isLoading) return <div data-testid="flags-loading">Loading...</div>;
  if (isError) return <div data-testid="flags-error">Failed to load feature flags</div>;

  return (
    <div data-testid="feature-flags-tab">
      <h2>Feature Flags</h2>
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr>
            <th>Flag</th>
            <th>Environment</th>
            <th>Status</th>
            <th>Updated At</th>
            <th>Notes</th>
          </tr>
        </thead>
        <tbody>
          {(flags ?? []).map((flag) => (
            <tr
              key={`${flag.flag_id}-${flag.environment}`}
              data-testid={`flag-row-${flag.flag_id}`}
            >
              <td>{flag.flag_id}</td>
              <td>
                <span
                  data-testid={`env-badge-${flag.flag_id}`}
                  style={{
                    background: "#e5e7eb",
                    padding: "2px 6px",
                    borderRadius: 4,
                    fontSize: "0.8rem",
                  }}
                >
                  {flag.environment}
                </span>
              </td>
              <td>
                <Toggle
                  flagId={flag.flag_id}
                  enabled={getEffectiveEnabled(flag)}
                  onToggle={handleToggle}
                  disabled={updateFlag.isPending}
                />
              </td>
              <td>
                {flag.updated_at
                  ? new Date(flag.updated_at).toLocaleString()
                  : "—"}
              </td>
              <td>
                {SOCIAL_DEFAULT_OFF_FLAGS.has(flag.flag_id) && (
                  <span
                    data-testid={`social-default-tooltip-${flag.flag_id}`}
                    title="Social source flags are off by default per D8 (data policy)"
                    style={{ color: "#6b7280", fontSize: "0.8rem" }}
                  >
                    Off by default (D8)
                  </span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default FeatureFlagsTab;
