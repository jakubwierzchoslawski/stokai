/**
 * SocialSourcesPanel — filtered SourceList for interface_type=SocialProvider.
 *
 * Twitter/X row displays a tooltip indicating that it is off by default
 * (architecture decision D8) and requires explicit admin action to enable.
 * Reuses useSources data passed in from the SourcesPage container.
 *
 * PLAN-F-028 TASK-009 (no TDD)
 */
import React from "react";
import { SourceConfig, useToggleSource } from "./hooks/useSources";

const TWITTER_DISPLAY_NAME = "Twitter/X";
const TWITTER_D8_TOOLTIP =
  "Off by default (D8) — explicit admin action required to enable.";

interface SocialSourceRowProps {
  source: SourceConfig;
  onToggle: (sourceId: string, current: boolean) => void;
  isPending: boolean;
}

function SocialSourceRow({ source, onToggle, isPending }: SocialSourceRowProps) {
  const isTwitter = source.display_name === TWITTER_DISPLAY_NAME;
  const health = source.health;
  const ratePct = health?.rate_limit_pct_used ?? 0;

  let badgeClass: string;
  let badgeLabel: string;
  if (ratePct >= 80) {
    badgeClass = "health-badge--red";
    badgeLabel = "Critical";
  } else if (ratePct >= 70) {
    badgeClass = "health-badge--amber";
    badgeLabel = "Warning";
  } else {
    badgeClass = "health-badge--green";
    badgeLabel = "OK";
  }

  return (
    <tr
      key={source.source_id}
      data-testid={`social-row-${source.source_id}`}
    >
      <td>
        {isTwitter ? (
          <span title={TWITTER_D8_TOOLTIP} data-testid="twitter-tooltip-cell">
            {source.display_name}
            <span className="tooltip-icon" aria-label={TWITTER_D8_TOOLTIP}>
              {" "}&#x24D8;
            </span>
          </span>
        ) : (
          source.display_name
        )}
      </td>
      <td>{source.interface_type}</td>
      <td>
        <button
          type="button"
          className={`enable-toggle ${source.enabled ? "enable-toggle--on" : "enable-toggle--off"}`}
          aria-pressed={source.enabled}
          aria-label={`${source.enabled ? "Disable" : "Enable"} ${source.display_name}`}
          data-testid={`social-toggle-${source.source_id}`}
          onClick={() => onToggle(source.source_id, source.enabled)}
          disabled={isPending}
        >
          {source.enabled ? "Enabled" : "Disabled"}
        </button>
      </td>
      <td>
        <span className={`health-badge ${badgeClass}`}>{badgeLabel}</span>
      </td>
      <td>{source.cost_tier}</td>
      <td>{health?.calls_today ?? 0}</td>
      <td>{ratePct.toFixed(1)}%</td>
      <td>{health?.errors_today ?? 0}</td>
      <td>${(health?.estimated_cost_today ?? 0).toFixed(4)}</td>
    </tr>
  );
}

export interface SocialSourcesPanelProps {
  sources: SourceConfig[];
}

export const SocialSourcesPanel: React.FC<SocialSourcesPanelProps> = ({ sources }) => {
  const socialSources = sources.filter((s) => s.interface_type === "SocialProvider");
  const toggle = useToggleSource();

  const handleToggle = (sourceId: string, current: boolean) => {
    toggle.mutate({ sourceId, enabled: !current });
  };

  if (socialSources.length === 0) {
    return (
      <div className="social-empty" data-testid="social-empty">
        No social provider sources configured.
      </div>
    );
  }

  return (
    <div className="social-sources-panel" data-testid="social-sources-panel">
      <h2>Social Sources</h2>
      <p className="social-sources-panel__note">
        All social providers are disabled by default. Twitter/X requires explicit admin
        action to enable (architecture decision D8).
      </p>
      <table className="social-source-table">
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
          {socialSources.map((source) => (
            <SocialSourceRow
              key={source.source_id}
              source={source}
              onToggle={handleToggle}
              isPending={toggle.isPending}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default SocialSourcesPanel;
