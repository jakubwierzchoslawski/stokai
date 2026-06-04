/**
 * SourceList — table of data sources with health badges and enable toggles.
 *
 * Columns: display_name, interface_type, enabled toggle, health badge
 * (green <70%, amber 70-80%, red >80%), cost_tier, calls_today,
 * rate_limit_pct, errors_today, est_cost.
 *
 * PLAN-F-028 TASK-007
 */
import React from "react";
import { SourceConfig, useToggleSource } from "./hooks/useSources";

interface HealthBadgeProps {
  rateLimitPct: number;
}

function HealthBadge({ rateLimitPct }: HealthBadgeProps) {
  let colour: string;
  let label: string;

  if (rateLimitPct >= 80) {
    colour = "health-badge--red";
    label = "Critical";
  } else if (rateLimitPct >= 70) {
    colour = "health-badge--amber";
    label = "Warning";
  } else {
    colour = "health-badge--green";
    label = "OK";
  }

  return (
    <span
      className={`health-badge ${colour}`}
      data-testid="health-badge"
      aria-label={`Health: ${label} (${rateLimitPct.toFixed(1)}%)`}
    >
      {label}
    </span>
  );
}

export interface SourceListProps {
  sources: SourceConfig[];
  onToggleError?: (err: Error) => void;
}

export const SourceList: React.FC<SourceListProps> = ({ sources, onToggleError }) => {
  const toggle = useToggleSource({ onError: onToggleError });

  const handleToggle = (sourceId: string, current: boolean) => {
    toggle.mutate({ sourceId, enabled: !current });
  };

  return (
    <table className="source-list-table" data-testid="source-list">
      <thead>
        <tr>
          <th>Name</th>
          <th>Interface</th>
          <th>Enabled</th>
          <th>Health</th>
          <th>Cost Tier</th>
          <th>Calls Today</th>
          <th>Rate Limit %</th>
          <th>Errors Today</th>
          <th>Est. Cost</th>
        </tr>
      </thead>
      <tbody>
        {sources.map((source) => {
          const health = source.health;
          const ratePct = health?.rate_limit_pct_used ?? 0;

          return (
            <tr key={source.source_id} data-testid={`source-row-${source.source_id}`}>
              <td>{source.display_name}</td>
              <td>{source.interface_type}</td>
              <td>
                <button
                  type="button"
                  className={`enable-toggle ${source.enabled ? "enable-toggle--on" : "enable-toggle--off"}`}
                  aria-pressed={source.enabled}
                  aria-label={`${source.enabled ? "Disable" : "Enable"} ${source.display_name}`}
                  data-testid={`toggle-${source.source_id}`}
                  onClick={() => handleToggle(source.source_id, source.enabled)}
                  disabled={toggle.isPending}
                >
                  {source.enabled ? "Enabled" : "Disabled"}
                </button>
              </td>
              <td>
                <HealthBadge rateLimitPct={ratePct} />
              </td>
              <td>{source.cost_tier}</td>
              <td>{health?.calls_today ?? 0}</td>
              <td>{ratePct.toFixed(1)}%</td>
              <td>{health?.errors_today ?? 0}</td>
              <td>${(health?.estimated_cost_today ?? 0).toFixed(4)}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
};

export default SourceList;
